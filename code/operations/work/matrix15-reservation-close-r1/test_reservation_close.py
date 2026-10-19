"""NEUTRAL transaction fixtures only. Never call reconcile or collect real CIM."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import reservation_close as close


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


@pytest.fixture(scope='module')
def capacity():
    return load('neutral_close_capacity', close.CAPACITY)


@pytest.fixture
def graph(tmp_path, monkeypatch, capacity):
    root = tmp_path / 'registry'
    root.mkdir()
    monkeypatch.setattr(close, 'REGISTRY', root)
    monkeypatch.setattr(close, 'LOCK', tmp_path / 'registry.lock')
    example = close.BASE / 'outputs/HPC-Forest-Matrice15-Execution-root-01/admission-windows-r2/slot-reservation.json'
    value = close.parse(example.read_bytes())
    target = root / (value['reservation_id'] + '.reservation.json')
    before = close.encode(value)
    target.write_bytes(before)
    sealed = tmp_path / 'sealed.FALSE.json'
    sealed.write_bytes(before)
    audit = root / 'private'
    audit.mkdir()
    return root, target, before, sealed, audit


def test_only_consumed_and_sealed_false_bytes_preserved(graph, capacity):
    root, target, before, sealed, audit = graph
    other = root / ('c' * 32 + '.reservation.json')
    other_value = {**close.parse(before), 'session_id': 'd' * 32, 'reservation_id': 'c' * 32}
    other.write_bytes(close.encode(other_value))
    snapshot = {path: path.read_bytes() for path in (target, other)}
    checks = []
    before_ref, after_ref, intent = close.commit_transition(target, before, snapshot, [close.ref(sealed)], audit, capacity,
        lambda: checks.append(True))
    after = close.parse(target.read_bytes())
    assert after == {**close.parse(before), 'consumed': True}
    assert sealed.read_bytes() == before == Path(before_ref['path']).read_bytes()
    assert Path(after_ref['path']).read_bytes() == target.read_bytes()
    assert other.read_bytes() == snapshot[other]
    assert close.read(intent)['transition'] == 'consumed:false->true'
    assert len(checks) == 3
    # Closing capacity never authorizes this session to reserve again.
    binding = close.binding_of(after, capacity.CELL_FIELDS)
    with pytest.raises(ValueError, match='no replay'):
        capacity.pending_reservations(root, binding, {'session_ids': []}, fixture=False)
    new_binding = {**binding, 'session_id': 'e' * 32}
    assert capacity.pending_reservations(root, new_binding, {'session_ids': []}, fixture=False) == {'d' * 32}


def test_reconcile_again_refused_before_archive(graph, capacity):
    _, target, before, sealed, audit = graph
    target.write_bytes(close.encode({**close.parse(before), 'consumed': True}))
    with pytest.raises(ValueError, match='Already consumed'):
        close.commit_transition(target, before, {target: before}, [close.ref(sealed)], audit, capacity, lambda: None)
    assert list(audit.iterdir()) == []


def test_already_true_input_also_refused(graph, capacity):
    _, target, before, _, audit = graph
    after = close.encode({**close.parse(before), 'consumed': True})
    target.write_bytes(after)
    with pytest.raises(ValueError, match='Already consumed'):
        close.commit_transition(target, after, {target: after}, [], audit, capacity, lambda: None)


def test_mutated_other_entry_refuses_transition(graph, capacity):
    root, target, before, sealed, audit = graph
    other = root / ('f' * 32 + '.reservation.json')
    other.write_bytes(b'old')
    snapshot = {target: before, other: b'old'}
    other.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Registry changed'):
        close.commit_transition(target, before, snapshot, [close.ref(sealed)], audit, capacity, lambda: None)
    assert target.read_bytes() == sealed.read_bytes() == before


def test_changed_admission_copy_refuses_transition(graph, capacity):
    _, target, before, sealed, audit = graph
    sealed_ref = close.ref(sealed)
    sealed.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Evidence bytes'):
        close.commit_transition(target, before, {target: before}, [sealed_ref], audit, capacity, lambda: None)
    assert target.read_bytes() == before


def test_archive_collision_never_overwrites(graph, capacity):
    _, target, before, sealed, audit = graph
    archive = audit / 'reservation-before.FALSE.json'
    archive.write_bytes(b'KEEP')
    with pytest.raises(FileExistsError):
        close.commit_transition(target, before, {target: before}, [close.ref(sealed)], audit, capacity, lambda: None)
    assert archive.read_bytes() == b'KEEP' and target.read_bytes() == before


def test_lost_lock_refuses_before_transition(graph, capacity):
    _, target, before, sealed, audit = graph
    def lost():
        raise ValueError('lost lock')
    with pytest.raises(ValueError, match='lost lock'):
        close.commit_transition(target, before, {target: before}, [close.ref(sealed)], audit, capacity, lost)
    assert target.read_bytes() == before


def test_exclusive_lock_collision_preserved(graph, capacity):
    close.LOCK.write_bytes(b'FOREIGN')
    with pytest.raises(FileExistsError), close.exclusive_lock(capacity):
        pass
    assert close.LOCK.read_bytes() == b'FOREIGN'


def test_exclusive_lock_cleanup_only_owned_token(graph, capacity):
    with close.exclusive_lock(capacity) as check:
        assert close.LOCK.is_file()
        check()
    assert not close.LOCK.exists()
    assert graph[1].read_bytes() == graph[2]


def test_lost_lock_is_preserved(graph, capacity):
    with pytest.raises(ValueError, match='ownership changed'):
        with close.exclusive_lock(capacity):
            close.LOCK.write_bytes(b'FOREIGN-REPLACEMENT')
    assert close.LOCK.read_bytes() == b'FOREIGN-REPLACEMENT'


def absent_analysis():
    return {'session_ids': [], 'native_workers_count': 0, 'private_native_groups': []}


@pytest.mark.parametrize('process', [
    {'ProcessId': 12, 'ParentProcessId': 1},  # same old PID, even reused
    {'ProcessId': 44, 'ParentProcessId': 12},  # direct worker descendant
    {'ProcessId': 44, 'ParentProcessId': 33},  # known historical descendant's child
])
def test_present_reused_or_descendant_refused(process, capacity):
    owned = {'processes': [{'ProcessId': 12}, {'ProcessId': 13}]}
    with pytest.raises(ValueError, match='PID present/reused'):
        close.no_activity([process], absent_analysis(), owned, {'session_id': 'a' * 32}, [], capacity,
                          original_pids={12, 13, 33})


def test_active_session_refused(capacity):
    analysis = {**absent_analysis(), 'session_ids': ['a' * 32], 'native_workers_count': 1}
    with pytest.raises(ValueError, match='session active'):
        close.no_activity([], analysis, {'processes': []}, {'session_id': 'a' * 32}, [], capacity)


def test_other_worker_missing_ownership_refused(capacity):
    analysis = {**absent_analysis(), 'native_workers_count': 1, 'private_native_groups': [[{}]]}
    with pytest.raises(ValueError, match='Every other'):
        close.no_activity([], analysis, {'processes': []}, {'session_id': 'a' * 32}, [], capacity)


def test_no_activity_does_not_require_empty_machine(capacity):
    close.no_activity([{'ProcessId': 111, 'ParentProcessId': 1}], absent_analysis(),
                      {'processes': [{'ProcessId': 12}]}, {'session_id': 'a' * 32}, [], capacity)


@pytest.mark.parametrize('stamp', [True, None, -1, 1001, 399])
def test_fresh_review_refusals(stamp):
    with pytest.raises(ValueError, match='Fresh'):
        close.fresh(stamp, 1000)


def test_fresh_boundary():
    close.fresh(400, 1000)
    close.fresh(1000, 1000)


def test_prepare_no_runtime_cim_or_registry_mutation(tmp_path, monkeypatch):
    output = tmp_path / 'output'
    output.mkdir()
    monkeypatch.setattr(close, 'OUTPUT', output)
    def forbidden(*args, **kwargs):
        raise AssertionError('No collection, runtime or registry path in preparation')
    monkeypatch.setattr(close, 'runtime', forbidden)
    monkeypatch.setattr(close, 'reconcile', forbidden)
    result = close.prepare(output / 'new')
    value = close.read(result)
    assert value['verified'] is False and value['registry_modified'] is False
    assert value['census_collected'] is False and value['commands_to_execute'] == []
    template = close.parse((output / 'new/INPUT-TEMPLATE.json').read_bytes())
    assert set(template) == close.FIELDS and template['mode'] == 'PREPARE'
    assert template['terminal_closure'] is None
    with pytest.raises(ValueError, match='never overwrite'):
        close.prepare(output / 'new')


def test_missing_input_rejected_without_runtime(tmp_path, monkeypatch):
    path = tmp_path / 'input.json'
    path.write_bytes(close.encode({'schema': close.SCHEMA, 'mode': 'PREPARE'}))
    monkeypatch.setattr(close, 'runtime', lambda: pytest.fail('runtime must not be reached'))
    with pytest.raises(ValueError, match='Complete explicit'):
        close.reconcile(close.ref(path))


def test_bad_hash_and_duplicate_json_refused(tmp_path):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match='Duplicate'):
        close.read(close.ref(path))
    bad = {**close.ref(path), 'sha256': '0' * 64}
    with pytest.raises(ValueError, match='Evidence bytes'):
        close.checked(bad)


def test_historical_graph_uses_separate_false_copy(graph, capacity):
    upstream = close.load_text('close_neutral_source', close.BUILDER, close.BUILDER_SHA)
    upstream.reader_runtime()
    from hpc_forest import matrix15_lane_contract as lane
    root, target, before, sealed, _ = graph
    binding = close.binding_of(close.parse(before), capacity.CELL_FIELDS)
    example = close.BASE / 'outputs/HPC-Forest-Matrice15-Execution-root-01/admission-windows-r2'
    admitted_lane = close.parse((example / 'worker-lane-admission.json').read_bytes())
    projection = close.parse((example / 'owned-lane-projection.json').read_bytes())
    projection['evidence_sha256']['global_slot_reservation'] = close.ref(sealed)['sha256']
    proj_path = root.parent / 'projection.json'
    proj_path.write_bytes(close.encode(projection))
    admitted_lane['minimal_owned_observations'] = close.ref(proj_path)
    admitted_lane['slot_reservation'] = close.ref(sealed)
    lane_path = root.parent / 'lane.json'
    lane_path.write_bytes(close.encode(admitted_lane))
    auth = close.parse((example / 'authorization.json').read_bytes())
    auth['artifacts']['worker_lane_admission'] = close.ref(lane_path)
    auth_path = root.parent / 'auth.json'
    auth_path.write_bytes(close.encode(auth))
    inputs = {'binding': binding, 'authorization': close.ref(auth_path), 'reservation_before': close.ref(target)}
    original, actual_target, refs = close.historical_graph(inputs, capacity, lane)
    assert actual_target == target and original['consumed'] is False
    assert all(Path(item['path']) != target for item in refs)
    target.write_bytes(close.encode({**close.parse(before), 'consumed': True}))
    # Unchanged source127 still validates historical admission with the sealed False copy.
    lane.validate_lane(admitted_lane, binding, close.checked, initial=False)
    for item in refs:
        close.checked(item)
    with pytest.raises(ValueError):
        close.historical_graph(inputs, capacity, lane)
    assert sealed.read_bytes() == before


def test_original_descendant_ids_transitive(graph, capacity):
    binding = {'session_id': 'a' * 32, 'job_id': '1'}
    row = {'ProcessId': 12, 'ParentProcessId': 1, 'CommandLine': 'known', 'ExecutablePath': 'known.exe',
           'CreationDate': '2026-01-01T00:00:00+00:00'}
    child = {**row, 'ProcessId': 13, 'ParentProcessId': 12}
    grandchild = {**row, 'ProcessId': 14, 'ParentProcessId': 13}
    observation = {'schema': 'hpc-forest-root-owned-worker-process-observation-v1', 'observed_at': 1780000000,
                   **binding, 'launch_receipt': 'primary', 'processes': [row, child, grandchild]}
    path = graph[0].parent / 'original.json'
    path.write_bytes(close.encode(observation))
    inputs = {'binding': binding, 'owned_process_observation': close.ref(path)}
    assert close.original_process_ids(inputs, {'processes': [row, child]}, capacity) == {12, 13, 14}
    observation['processes'].append({**row, 'ProcessId': 99, 'ParentProcessId': 1})
    path.write_bytes(close.encode(observation))
    inputs['owned_process_observation'] = close.ref(path)
    with pytest.raises(ValueError, match='unrelated'):
        close.original_process_ids(inputs, {'processes': [row, child]}, capacity)


def test_exact_cache_hashes_not_only_equal_tokens(tmp_path):
    nonce = 'b' * 32
    channel = '/gpfs/scratch/native/results-1/mailbox'
    call = {'request': {'path': channel + '/requests/' + nonce + '.request.json', 'sha256': 'a' * 64},
            'response': {'sha256': 'c' * 64}, 'ready': {'sha256': 'd' * 64}, 'delivered': {'sha256': 'e' * 64},
            'error_and_usage_log': {'sha256': 'f' * 64},
            'private_cli_records': {'invocation_sha256': '1' * 64, 'process_sha256': '2' * 64}}
    names = {'downloaded-request.json': 'a', 'response.json': 'c', 'response-ready.json': 'd',
             'delivered.json': 'e', 'codex.jsonl': 'f', 'invocation.json': '1', 'codex.jsonl.json': '2'}
    inventory = [{'path': nonce + '/' + name, 'sha256': value * 64, 'bytes': 4} for name, value in names.items()]
    audit = {'named_private_inventory': {item['path']: {key: item[key] for key in ('sha256', 'bytes')} for item in inventory}}
    final_path, audit_path = tmp_path / 'final.json', tmp_path / 'audit.json'
    final_path.write_bytes(close.encode({'all_started_calls_reconciled': [call]}))
    audit_path.write_bytes(close.encode(audit))
    cold = {'closed_calls': [{'nonce': nonce}], 'terminal_artifacts': {'final_reconciliation': {'local_ref': close.ref(final_path)}},
            'first_batch_private_audit': close.ref(audit_path)}
    inputs = {'binding': {'remote_root': '/gpfs/scratch/native', 'job_id': '1'}}
    cache = {'inventory': inventory, 'nonces': [nonce]}
    close.exact_cache_binding(inputs, cold, cache)
    inventory[1]['sha256'] = '9' * 64
    with pytest.raises(ValueError, match='previously audited private bytes'):
        close.exact_cache_binding(inputs, cold, cache)
    # Even a changed local audit cannot bypass the received terminal raw hashes.
    audit['named_private_inventory'][nonce + '/response.json']['sha256'] = '9' * 64
    audit_path.write_bytes(close.encode(audit))
    cold['first_batch_private_audit'] = close.ref(audit_path)
    with pytest.raises(ValueError, match='received terminal hash'):
        close.exact_cache_binding(inputs, cold, cache)


@pytest.fixture
def cli_guard_inputs(tmp_path, graph):
    binding = close.binding_of(close.parse(graph[2]), load('cli_guard_capacity_fields', close.CAPACITY).CELL_FIELDS)
    files = {}
    for name in ('codex.exe', 'codex-code-mode-host.exe', 'codex-command-runner.exe', 'codex-windows-sandbox-setup.exe'):
        file = tmp_path / name
        file.write_bytes(b'NEUTRAL')
        files[name] = close.ref(file)
    cli = tmp_path / 'identity.json'
    cli.write_bytes(close.encode({**binding, 'verified': True, 'files': files}))
    auth = tmp_path / 'auth.json'
    auth.write_bytes(close.encode({'artifacts': {'cli_identity': close.ref(cli)}}))
    owned = {'processes': [{'CreationDate': '2026-01-01T00:00:01+00:00', 'CommandLine': 'python --output C:\\neutral\\cache'}]}
    return {'binding': binding, 'authorization': close.ref(auth)}, owned, str(tmp_path / 'codex.exe')


def cli_row(pid, parent, executable, *, created='2026-01-01T00:00:02+00:00'):
    return {'ProcessId': pid, 'ParentProcessId': parent, 'ExecutablePath': executable,
            'CommandLine': 'NEUTRAL CLI', 'CreationDate': created}


def test_cli_orphan_after_original_worker_refused(cli_guard_inputs, capacity):
    inputs, owned, executable = cli_guard_inputs
    with pytest.raises(ValueError, match='Orphan/ambiguous CLI'):
        close.cli_process_absence([cli_row(77, 66, executable)], absent_analysis(), owned, inputs, capacity)


def test_cli_predating_original_worker_allowed(cli_guard_inputs, capacity):
    inputs, owned, executable = cli_guard_inputs
    close.cli_process_absence([cli_row(77, 66, executable, created='2026-01-01T00:00:00+00:00')],
                             absent_analysis(), owned, inputs, capacity)


def test_cli_complete_chain_to_other_exact_owned_worker(cli_guard_inputs, capacity):
    inputs, owned, executable = cli_guard_inputs
    root = cli_row(10, 1, 'C:\\neutral\\python.exe', created='2026-01-01T00:00:01+00:00')
    root['session_id'], root['channel'], root['role'] = 'e' * 32, '/mailbox/other', 'worker'
    child = cli_row(77, 10, executable)
    analysis = {**absent_analysis(), 'private_native_groups': [[root]]}
    close.cli_process_absence([{key: root[key] for key in capacity.PROCESS_FIELDS}, child], analysis, owned, inputs, capacity)
    root['CreationDate'] = '2026-01-01T00:00:03+00:00'
    with pytest.raises(ValueError, match='parent PID reused'):
        close.cli_process_absence([{key: root[key] for key in capacity.PROCESS_FIELDS}, child], analysis, owned, inputs, capacity)


def test_cli_unknown_system_path_allowed_but_named_missing_path_refused(cli_guard_inputs, capacity):
    inputs, owned, _ = cli_guard_inputs
    row = cli_row(0, 0, None)
    row['CommandLine'] = None
    close.cli_process_absence([row], absent_analysis(), owned, inputs, capacity)
    row['CommandLine'] = 'codex.exe NEUTRAL'
    with pytest.raises(ValueError, match='Unreadable potentially owned CLI'):
        close.cli_process_absence([row], absent_analysis(), owned, inputs, capacity)


def test_any_closing_session_command_refused(cli_guard_inputs, capacity):
    inputs, owned, _ = cli_guard_inputs
    row = cli_row(77, 66, 'C:\\neutral\\unrelated.exe')
    row['CommandLine'] = 'python ' + inputs['binding']['session_id']
    with pytest.raises(ValueError, match='closing session/auth/cache'):
        close.cli_process_absence([row], absent_analysis(), owned, inputs, capacity)


def test_transition_guard_checks_after_slow_journal(graph, capacity, monkeypatch):
    _, target, before, sealed, audit = graph
    clock = [1000]
    original = capacity.exclusive_bytes
    def slow(path, raw):
        result = original(path, raw)
        if path.name == 'replacement.tmp':
            clock[0] = 1601
        return result
    monkeypatch.setattr(capacity, 'exclusive_bytes', slow)
    def guard():
        close.transition_guard(lambda: None, [1000, 1000], 1000, now=clock[0])
    with pytest.raises(ValueError, match='Fresh'):
        close.commit_transition(target, before, {target: before}, [close.ref(sealed)], audit, capacity, guard)
    assert target.read_bytes() == before


@pytest.mark.parametrize('census_times,review', [([399, 999], 999), ([999, 999], 399), ([999], 999)])
def test_last_guard_refuses_stale_census_or_review(census_times, review):
    with pytest.raises(ValueError):
        close.transition_guard(lambda: None, census_times, review, now=1000)


@pytest.mark.parametrize("flag", ["fixture", "neutral", "test_only", "prepared", "prepared_only", "synthetic"])
def test_terminal_preparation_metadata_cannot_be_cleaned(flag):
    with pytest.raises(ValueError, match="cannot be promoted"):
        close.terminal_metadata({"verified": True, flag: True})


def test_terminal_negative_verdict_and_origin_refused():
    for value in ({"verified": False}, {"verified": True, "evidence_origin": "NEUTRAL"}):
        with pytest.raises(ValueError, match="cannot be promoted"):
            close.terminal_metadata(value)
    # Scientific negatives and names are outside the TOP metadata guard.
    close.terminal_metadata({"verified": True, "response": {"verified": False}, "model": "gpt-neutral-model"})


def test_terminal_marked_private_audit_rejected_before_validator(tmp_path):
    proof = tmp_path / "private.json"
    proof.write_bytes(close.encode({"verified": True, "fixture": True}))
    value = {"first_batch_private_audit": close.ref(proof)}
    with pytest.raises(ValueError, match="cannot be promoted"):
        close.terminal_origin_checked(value)
