"""Close one terminal private reservation. Default preparation never collects CIM.

Only explicit --reconcile may collect two private complete censuses and change the
persistent entry. Admission copies, cache files, budgets and sessions stay sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
WORK = BASE / 'work/matrix15-reservation-close-r1'
OUTPUT = BASE / 'outputs/HPC-Forest-Matrice15-Reservation-Cloture-Preparation-r1'
REGISTRY = BASE / 'work/matrix15-global-capacity-production-r1'
LOCK = REGISTRY.with_name(REGISTRY.name + '.lock')
CAPACITY = BASE / 'outputs/HPC-Forest-Matrice15-Admission-Extension-Preparation-r3/capacity.py'
CAPACITY_SHA = 'a4f9121ef769ae98524f179a92b2ea27ea2a139e3ccc8c8982280f26c74b1a1d'
RUNTIME_SHA = '049c5c1602814ec3541fcaa414f9c70dec4ecebbee9017414fbca9510be72f88'
BUILDER = BASE / 'work/matrix15-first-operation-inputs-r1/build_inputs.py'
BUILDER_SHA = 'e7295bb03e956dc343c70eaabcfca98f240c3b3643963c3381f2013edb6a4124'
TERMINAL = BASE / 'work/matrix15-terminal-audit-r1/terminal_audit.py'
TERMINAL_SHA = 'c03cfd1e138515393e8c1b34ccd3f73a807df607fc63d19e6f0048f25a147e57'
CACHE_SHA = '15f07080c3c84727dc317357d6e1d99c2b02f412e4624fa3a4b1a5be0176e1e7'
SCHEMA = 'hpc-forest-matrix15-reservation-close-input-v1'
FIELDS = {'schema', 'mode', 'binding', 'reservation_before', 'authorization', 'worker_argv',
          'owned_worker', 'owned_process_observation', 'other_owned_workers', 'terminal_input', 'terminal_closure',
          'cache_inventory', 'root_review', 'output_directory'}
REF_FIELDS = FIELDS - {'schema', 'mode', 'binding', 'other_owned_workers', 'output_directory'}
COLD_SCOPE = 'terminal-bookkeeping-and-unchanged-audited-call-set-only'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda _: need(False, 'Nonfinite JSON'))


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8')


def ordinary(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'Absolute physical path required')
    for candidate in (path, *path.parents):
        need(not candidate.is_symlink() and not candidate.is_junction(), 'Redirected evidence path refused')
        if candidate.exists():
            need(not getattr(candidate.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400,
                 'Reparse path refused')
    need(path.is_dir() if directory else path.is_file(), 'Required evidence absent')
    return path.resolve(strict=True)


def ref(path):
    path = ordinary(path)
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def checked(item):
    need(isinstance(item, dict) and set(item) == {'path', 'sha256'} and isinstance(item['sha256'], str)
         and len(item['sha256']) == 64 and all(c in '0123456789abcdef' for c in item['sha256']), 'Exact SHA reference required')
    path = ordinary(item['path'])
    need(ref(path) == item, 'Evidence bytes or physical path changed')
    return path


def read(item):
    raw = checked(item).read_bytes()
    need(len(raw) <= 16 * 1024 * 1024, 'Object evidence exceeds bounded reader limit')
    value = parse(raw)
    need(isinstance(value, dict), 'Object evidence required')
    return value


def load_text(name, path, checksum):
    raw = ordinary(path).read_bytes()
    need(isinstance(checksum, str) and digest(raw) == checksum, 'Unsealed producer dependency: ' + Path(path).name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def runtime():
    upstream = load_text('close_source_checker', BUILDER, BUILDER_SHA)
    upstream.reader_runtime()  # Verify all127 source files/ZIP before importing lane API.
    from hpc_forest import matrix15_lane_contract as lane
    capacity = load_text('close_capacity', CAPACITY, CAPACITY_SHA)
    need(ref(CAPACITY.with_name('VENV-RUNTIME-IDENTITY.json'))['sha256'] == RUNTIME_SHA, 'Runtime sidecar changed')
    cache = load_text('close_cache', Path(__file__).with_name('cache_check.py'), CACHE_SHA)
    terminal = load_text('close_terminal', TERMINAL, TERMINAL_SHA)
    return capacity, lane, cache, terminal


def positive(value):
    need(isinstance(value, dict) and value.get('verified') is True
         and not any(value.get(key) is True for key in ('fixture', 'neutral', 'test_only', 'prepared', 'synthetic')),
         'Actual positive mechanical evidence required')


def fresh(value, now, *, limit=600):
    need(type(value) in (int, float) and 0 <= now - value <= limit, 'Fresh nonfuture ROOT observation/review required')


def binding_of(value, fields):
    return {key: value.get(key) for key in fields}


def historical_graph(inputs, capacity, lane):
    """Historical graph deliberately keeps the original False copy, never registry."""
    binding = inputs['binding']
    capacity.validate_binding(binding)
    auth = read(inputs['authorization'])
    positive(auth)
    from hpc_forest import native_matrix15 as native
    need(auth.get('schema') == 'hpc-forest-matrix15-authorization-v1'
         and native.cell_binding(auth) == binding, 'Historical authorization binding mismatch')
    for item in auth['artifacts'].values():
        checked(item)
    lane_ref = auth.get('artifacts', {}).get('worker_lane_admission')
    admitted_lane = read(lane_ref)
    lane.validate_lane(admitted_lane, binding, checked, initial=False)
    original_ref = admitted_lane['slot_reservation']
    original = read(original_ref)
    need(original_ref['sha256'] == inputs['reservation_before']['sha256'], 'Registry/admission initial digests differ')
    target = checked(inputs['reservation_before'])
    need(target == ordinary(REGISTRY, directory=True) / (original['reservation_id'] + '.reservation.json')
         and target != checked(original_ref), 'Only separate persistent registry entry may change')
    need(target.read_bytes() == checked(original_ref).read_bytes(), 'Persistent entry no longer equals initial False copy')
    sealed = [inputs['authorization'], lane_ref, original_ref, admitted_lane['minimal_owned_observations']]
    need(all(checked(item) != target for item in sealed), 'Mutable entry is referenced as historical evidence')
    return original, target, sealed


def owned_identity(item, binding, capacity, identity, now):
    value = read(item)
    positive(value)
    need(set(value) == {'schema', 'verified', 'ownership_established', 'session_id', 'channel', 'processes'}
         and value['schema'] == 'hpc-forest-native-owned-worker-identity-v1'
         and value['ownership_established'] is True and value['session_id'] == binding['session_id']
         and value['channel'] == binding['remote_root'] + '/results-' + binding['job_id'] + '/mailbox',
         'Exact original owned worker identity required')
    analysis = capacity.classify_processes(value['processes'], now, venv_identity=identity)
    need(analysis['native_workers_count'] == analysis['private_windows_venv_pairs_count'] == 1
         and len(value['processes']) == 2 and analysis['session_ids'] == [binding['session_id']]
         and value['processes'] == [{key: p[key] for key in capacity.PROCESS_FIELDS}
                                    for p in analysis['private_native_groups'][0]], 'Exact pinned venv/base identities required')
    return value


def cache_path(inputs, owned, capacity):
    argv = read(inputs['worker_argv'])
    need(set(argv) == {'argv', 'cwd', 'environment', 'persistent'} and argv['persistent'] is True
         and isinstance(argv['argv'], list) and argv['argv'] and all(isinstance(x, str) for x in argv['argv'])
         and '--once' not in argv['argv'], 'Original persistent worker argv required')
    args = argv['argv']
    command = owned['processes'][0]['CommandLine']
    renderings = {subprocess.list2cmdline(args), '"' + args[0] + '" ' + subprocess.list2cmdline(args[1:])}
    need(command in renderings, 'Owned command line differs from exact original argv')
    need(capacity.argument(command, '--dependency-receipt') == inputs['authorization']['path']
         and capacity.argument(command, '--session-id') == inputs['binding']['session_id']
         and capacity.argument(command, '--channel') == owned['channel'], 'Original worker auth/session/channel mismatch')
    cache = ordinary(capacity.argument(command, '--output'), directory=True)
    need(cache.is_relative_to(BASE / 'work') and not cache.is_relative_to(REGISTRY), 'Private original worker cache required')
    return cache


def terminal_metadata(value, *, required_positive=False):
    need(isinstance(value, dict) and value.get('verified') is not False
         and not any(value.get(key) is True for key in ('fixture', 'neutral', 'test_only', 'prepared', 'prepared_only', 'synthetic'))
         and str(value.get('evidence_origin', '')).casefold() not in {'fixture', 'neutral', 'prepared', 'synthetic', 'test_only'},
         'Prepared/fixture/failed terminal evidence cannot be promoted')
    if required_positive:
        positive(value)


def terminal_origin_checked(value):
    # c03 closes bookkeeping, but does not itself reject every preparation marker.
    # Check typed evidence at its TOP only, never lexical strings/model negatives.
    for key in ('first_batch_private_audit', 'first_batch_root_review'):
        item = value[key]
        terminal_metadata(read({key: item[key] for key in ('path', 'sha256')}), required_positive=True)
    wrappers = [value['status_ref'], value['efficiency_ref']]
    for packet in value['artifacts'].values():
        item = packet['local_ref']
        terminal_metadata(read({key: item[key] for key in ('path', 'sha256')}))
        wrappers.append(packet['transfer_receipt'])
    for item in wrappers:
        wrapper = read({key: item[key] for key in ('path', 'sha256')})
        terminal_metadata(wrapper)
        terminal_metadata(wrapper.get('response'))
        terminal_metadata(wrapper.get('response', {}).get('structuredContent'))


def terminal_checked(inputs, terminal):
    terminal_input = read(inputs['terminal_input'])
    terminal_origin_checked(terminal_input)
    actual = terminal.validate(terminal_input)
    received = read(inputs['terminal_closure'])
    positive(received)
    need(received == actual and received.get('schema') == 'hpc-forest-matrix15-terminal-cold-receipt-v1'
         and received.get('verified_scope') == COLD_SCOPE and received.get('binding') == inputs['binding']
         and received.get('source_terminal_reconciliation_verified') is True
         and received.get('scheduler_completed') is True and received.get('no_replay') is True
         and received.get('budget_or_chronology_reset') is False, 'Exact independently recomputed cold terminal closure required')
    calls = received.get('closed_calls')
    need(isinstance(calls, list) and calls and len({c['nonce'] for c in calls}) == len(calls), 'Closed call set required')
    return received


def exact_cache_binding(inputs, cold, cache):
    # The cold scope closes the same privately audited calls; retain byte identity,
    # not just coincidentally equal nonce/token aggregates.
    final_ref = cold['terminal_artifacts']['final_reconciliation']['local_ref']
    final = read({key: final_ref[key] for key in ('path', 'sha256')})
    audit_ref = cold['first_batch_private_audit']
    audit = read({key: audit_ref[key] for key in ('path', 'sha256')})
    inventory = {item['path']: {key: item[key] for key in ('sha256', 'bytes')} for item in cache['inventory']}
    original = audit.get('named_private_inventory')
    need(isinstance(original, dict) and original and all(inventory.get(name) == item for name, item in original.items()),
         'Current cache differs from exact previously audited private bytes')
    paths = {'downloaded-request.json': 'request', 'response.json': 'response', 'response-ready.json': 'ready',
             'delivered.json': 'delivered', 'codex.jsonl': 'error_and_usage_log'}
    calls = final.get('all_started_calls_reconciled')
    need(isinstance(calls, list) and len(calls) == len(cold['closed_calls']), 'Final cache call set changed')
    channel = inputs['binding']['remote_root'] + '/results-' + inputs['binding']['job_id'] + '/mailbox'
    seen = set()
    for call in calls:
        request = call.get('request', {}).get('path', '')
        prefix = channel + '/requests/'
        need(request.startswith(prefix) and request.endswith('.request.json'), 'Exact original request mailbox required')
        nonce = request[len(prefix):-len('.request.json')]
        need(nonce in cache['nonces'] and nonce not in seen, 'Unknown/repeated terminal cache nonce')
        seen.add(nonce)
        for filename, role in paths.items():
            item = inventory.get(nonce + '/' + filename)
            need(item is not None and item['sha256'] == call.get(role, {}).get('sha256'),
                 'Cache raw request/response/ready/delivered/log differs from received terminal hash')
        for filename, role in (('invocation.json', 'invocation_sha256'), ('codex.jsonl.json', 'process_sha256')):
            need(inventory.get(nonce + '/' + filename, {}).get('sha256') == call.get('private_cli_records', {}).get(role),
                 'Cache private invocation/process differs from received terminal digest')
    need(seen == set(cache['nonces']), 'Cache contains a call outside received terminal closure')


def review_checked(inputs, cold, cache, now):
    review = read(inputs['root_review'])
    positive(review)
    required = {'schema', 'verified', 'reviewer', 'reviewed_at', 'decision', 'binding', 'sources', 'evidence',
                'no_budget_or_chronology_reset', 'session_permanently_excluded', 'no_worker_termination', 'cache_inventory_sha256'}
    need(set(review) == required and review['schema'] == 'hpc-forest-matrix15-reservation-close-root-review-v1'
         and review['reviewer'] == 'ROOT' and review['decision'] == 'close-consumed-only'
         and review['binding'] == inputs['binding'] and review['sources'] == source_pins()
         and review['evidence'] == {key: inputs[key] for key in (REF_FIELDS - {'root_review'}) | {'other_owned_workers'}}
         and all(review[key] is True for key in ('no_budget_or_chronology_reset', 'session_permanently_excluded', 'no_worker_termination'))
         and review['cache_inventory_sha256'] == cache['inventory_sha256'], 'ROOT review must bind exact producer/evidence/cache and consumed-only scope')
    fresh(review['reviewed_at'], now)
    inventory = read(inputs['cache_inventory'])
    positive(inventory)
    need(set(inventory) == {'schema', 'verified', 'binding', 'observed_at', 'cache_inventory'}
         and inventory['schema'] == 'hpc-forest-matrix15-terminal-cache-inventory-v1'
         and inventory['binding'] == inputs['binding'] and inventory['cache_inventory'] == cache,
         'ROOT private inventory differs from current closed cache')
    fresh(inventory['observed_at'], now)
    need(cache['nonces'] == sorted(c['nonce'] for c in cold['closed_calls'])
         and cache['exact_tokens'] == cold['exact_tokens_all_calls'], 'Cache and terminal closed call totals differ')
    exact_cache_binding(inputs, cold, cache)
    return review


def source_pins():
    return {'reservation_close.py': ref(Path(__file__)).get('sha256'), 'capacity.py': CAPACITY_SHA,
            'VENV-RUNTIME-IDENTITY.json': RUNTIME_SHA, 'cache_check.py': CACHE_SHA, 'terminal_audit.py': TERMINAL_SHA}


def original_process_ids(inputs, owned, capacity):
    observation = read(inputs['owned_process_observation'])
    need(set(observation) == {'schema', 'observed_at', 'session_id', 'job_id', 'launch_receipt', 'processes'}
         and observation['schema'] == 'hpc-forest-root-owned-worker-process-observation-v1'
         and observation['session_id'] == inputs['binding']['session_id']
         and observation['job_id'] == inputs['binding']['job_id']
         and type(observation['observed_at']) in (int, float) and 0 < observation['observed_at'] <= time.time(),
         'Original dated process observation required')
    rows = observation['processes']
    need(isinstance(rows, list) and all(isinstance(p, dict) and set(p) == capacity.PROCESS_FIELDS for p in rows)
         and len({p['ProcessId'] for p in rows}) == len(rows), 'Exact original process observation rows required')
    by_pid = {p['ProcessId']: p for p in rows}
    need(all(by_pid.get(p['ProcessId']) == p for p in owned['processes']), 'Original process identities changed')
    pids = {p['ProcessId'] for p in owned['processes']}
    previous = None
    while previous != pids:
        previous = set(pids)
        pids.update(p['ProcessId'] for p in rows if p['ParentProcessId'] in pids)
    need(set(by_pid) == pids, 'Original observation contains unrelated unidentified processes')
    for process in rows:
        need(type(process['ProcessId']) is int and process['ProcessId'] > 0
             and type(process['ParentProcessId']) is int and process['ParentProcessId'] >= 0
             and process['ExecutablePath'] and process['CommandLine']
             and 0 <= capacity.creation_time(process['CreationDate']) <= observation['observed_at'],
             'Original descendants require complete nonfuture identities')
    return pids


def no_activity(processes, analysis, owned, binding, other_refs, capacity, *, original_pids=None):
    pids = {p['ProcessId'] for p in owned['processes']} if original_pids is None else original_pids
    need(not any(p['ProcessId'] in pids or p['ParentProcessId'] in pids for p in processes),
         'Old worker PID present/reused or remaining descendant: wait and reconcile identity')
    need(binding['session_id'] not in analysis['session_ids'] and analysis['native_workers_count'] <= 4,
         'Closing session active or global count exceeds cap4')
    need(isinstance(other_refs, list) and len(other_refs) == len(analysis['private_native_groups']),
         'Every other active native group requires ownership reconciliation')
    for item, group in zip(other_refs, analysis['private_native_groups'], strict=True):
        value = read(item)
        positive(value)
        need(set(value) == {'schema', 'verified', 'ownership_established', 'session_id', 'channel', 'processes'}
             and value['schema'] == 'hpc-forest-native-owned-worker-identity-v1'
             and value['ownership_established'] is True and value['session_id'] == group[0]['session_id']
             and value['channel'] == group[0]['channel']
             and value['processes'] == [{key: p[key] for key in capacity.PROCESS_FIELDS} for p in group],
             'Unknown or incompletely reconciled other worker')


def cli_process_absence(processes, analysis, owned, inputs, capacity):
    auth = read(inputs['authorization'])
    cli = read(auth['artifacts']['cli_identity'])
    positive(cli)
    need(binding_of(cli, capacity.CELL_FIELDS) == inputs['binding'] and isinstance(cli.get('files'), dict)
         and set(cli['files']) == {'codex.exe', 'codex-code-mode-host.exe', 'codex-command-runner.exe',
                                  'codex-windows-sandbox-setup.exe'}, 'Exact four-binary original CLI identity required')
    executable_paths = set()
    for item in cli['files'].values():
        checked(item)
        executable_paths.add(capacity.windows_path(item['path']))
    earliest = min(capacity.creation_time(p['CreationDate']) for p in owned['processes'])
    by_pid = {p['ProcessId']: p for p in processes}
    other_roots = {p['ProcessId']: {key: p[key] for key in capacity.PROCESS_FIELDS}
                   for group in analysis['private_native_groups'] for p in group}
    protected = (inputs['binding']['session_id'].casefold(), inputs['authorization']['path'].casefold(),
                 capacity.argument(owned['processes'][0]['CommandLine'], '--output').casefold())
    for process in processes:
        command = (process['CommandLine'] or '').casefold()
        need(not any(text in command for text in protected), 'Remaining process mentions closing session/auth/cache')
        executable = process['ExecutablePath']
        if not executable:
            need(not any(Path(item['path']).name.casefold() in command for item in cli['files'].values()),
                 'Unreadable potentially owned CLI executable path')
            continue
        if capacity.windows_path(executable) not in executable_paths:
            continue
        need(process['CommandLine'] and process['CreationDate'], 'Unreadable potentially owned CLI identity')
        created = capacity.creation_time(process['CreationDate'])
        if created < earliest:
            continue  # A child cannot predate the original worker.
        # An unrecorded/orphan CLI from the worker lifetime is ambiguous. The only
        # exception is a complete, chronological chain to another exact owned group.
        current, visited = process, set()
        while current['ProcessId'] not in other_roots:
            need(current['ProcessId'] not in visited, 'Ambiguous cyclic CLI ancestry')
            visited.add(current['ProcessId'])
            parent = by_pid.get(current['ParentProcessId'])
            need(parent is not None and parent['CreationDate'] and current['CreationDate']
                 and capacity.creation_time(parent['CreationDate']) <= capacity.creation_time(current['CreationDate']),
                 'Orphan/ambiguous CLI or parent PID reused: refuse closure')
            current = parent
        need(current == other_roots[current['ProcessId']], 'CLI ancestor differs from exact other owned identity')


def registry_snapshot(capacity, lane):
    result, sessions = {}, set()
    for path in sorted(ordinary(REGISTRY, directory=True).glob('*.reservation.json')):
        ordinary(path)
        raw = path.read_bytes()
        value = parse(raw)
        need(isinstance(value, dict) and set(value) == lane.RESERVATION_FIELDS
             and value.get('schema') == lane.RESERVATION_SCHEMA and value.get('verified') is True
             and type(value.get('consumed')) is bool and path.name == value['reservation_id'] + '.reservation.json'
             and value['session_id'] not in sessions and value['maximum_native_workers_total'] == 4
             and type(value['active_native_workers_before_start']) is int
             and 0 <= value['active_native_workers_before_start'] < 4
             and all(value[key] is True for key in ('exclusive_global_lock_held_at_census', 'all_native_workers_known',
                 'launcher_python_pairs_count_as_one', 'one_cell_only', 'one_submission_only')),
             'Unknown/duplicate global persistent reservation')
        capacity.validate_binding(binding_of(value, capacity.CELL_FIELDS))
        sessions.add(value['session_id'])
        result[path] = raw
    return result


@contextmanager
def exclusive_lock(capacity):
    capacity.no_redirects(REGISTRY)
    capacity.no_redirects(LOCK)
    need(REGISTRY.is_dir() and LOCK.parent.is_dir(), 'Existing global registry required')
    token = (uuid.uuid4().hex + '\n').encode()
    capacity.exclusive_bytes(LOCK, token)
    stat = LOCK.stat()
    identity = stat.st_dev, stat.st_ino
    def check():
        capacity.no_redirects(LOCK)
        current = LOCK.stat()
        need((current.st_dev, current.st_ino) == identity and LOCK.read_bytes() == token, 'Global lock ownership changed; preserve it')
    try:
        yield check
    finally:
        check()
        LOCK.unlink()  # Release only our O_EXCL token, never a reservation or cache.


def private_directory(capacity):
    private = REGISTRY / 'private'
    capacity.no_redirects(private)
    private.mkdir(exist_ok=True)
    need(ordinary(private, directory=True).parent == ordinary(REGISTRY, directory=True), 'Private journal escaped registry')
    audit = private / ('close-' + uuid.uuid4().hex)
    audit.mkdir()
    ordinary(audit, directory=True)
    return audit


def commit_transition(target, before, snapshot, sealed, audit, capacity, check_lock):
    """Single narrowly owned replacement; caller holds lock and validated evidence."""
    need(target.read_bytes() == before and parse(before).get('consumed') is False, 'Already consumed or changed; no idempotent replay')
    after_value = {**parse(before), 'consumed': True}
    after = encode(after_value)
    need({k: v for k, v in parse(after).items() if k != 'consumed'}
         == {k: v for k, v in parse(before).items() if k != 'consumed'}, 'Only consumed may change')
    before_ref = capacity.exclusive_bytes(audit / 'reservation-before.FALSE.json', before)
    after_ref = capacity.exclusive_bytes(audit / 'reservation-after.TRUE.json', after)
    intent_ref = capacity.exclusive_json(audit / 'TRANSITION-INTENT.json', {
        'schema': 'hpc-forest-matrix15-reservation-close-intent-v1', 'before': before_ref, 'after': after_ref,
        'target': str(target), 'sealed_admission_refs': sealed, 'transition': 'consumed:false->true'})
    need(all(path.read_bytes() == raw for path, raw in snapshot.items())
         and set(REGISTRY.glob('*.reservation.json')) == set(snapshot), 'Registry changed while lock held')
    for item in sealed:
        checked(item)
    capacity.no_redirects(target)
    capacity.no_redirects(audit)
    check_lock()
    # Temp file is inside private journal; atomic replacement stays on the same volume.
    temporary = audit / 'replacement.tmp'
    capacity.exclusive_bytes(temporary, after)
    check_lock()  # Recheck clocks after every potentially slow journal/hash/fsync operation.
    os.replace(temporary, target)
    need(target.read_bytes() == after, 'Persistent transition readback failed; inspect private journal')
    need(all(path.read_bytes() == (after if path == target else raw) for path, raw in snapshot.items())
         and set(REGISTRY.glob('*.reservation.json')) == set(snapshot), 'Unexpected registry mutation; inspect private journal')
    for item in sealed:
        checked(item)
    check_lock()
    return before_ref, after_ref, intent_ref


def transition_guard(check_lock, census_times, reviewed_at, *, now=None):
    check_lock()
    instant = time.time() if now is None else now
    need(isinstance(census_times, list) and len(census_times) == 2, 'Two private census clocks required')
    for stamp in census_times:
        fresh(stamp, instant)
    fresh(reviewed_at, instant)


def output_path(value):
    path = Path(value)
    need(path.is_absolute() and '..' not in path.parts, 'Absolute new output required')
    for candidate in (path, *path.parents):
        need(not candidate.is_symlink() and not candidate.is_junction(), 'Redirected output refused')
    path = path.resolve()
    need(path != OUTPUT.resolve() and path.is_relative_to(OUTPUT.resolve()) and not path.exists(), 'New owned output only; never overwrite')
    return path


def reconcile(input_ref):
    """Production only. There is no injected collector, registry override or force flag."""
    inputs = read(input_ref)
    need(set(inputs) == FIELDS and inputs['schema'] == SCHEMA and inputs['mode'] == 'RECONCILE'
         and all(inputs[key] is not None for key in FIELDS), 'Complete explicit RECONCILE input required')
    capacity, lane, cache_module, terminal = runtime()
    cold = terminal_checked(inputs, terminal)
    output = output_path(inputs['output_directory'])
    with exclusive_lock(capacity) as check_lock:
        identity = capacity.load_venv_identity()  # all3 actual binary/cfg pins under lock
        original, target, sealed = historical_graph(inputs, capacity, lane)
        owned = owned_identity(inputs['owned_worker'], inputs['binding'], capacity, identity, time.time())
        cache_root = cache_path(inputs, owned, capacity)
        original_pids = original_process_ids(inputs, owned, capacity)
        before = target.read_bytes()
        snapshot = registry_snapshot(capacity, lane)
        audit = private_directory(capacity)
        census_refs = []
        census_times = []
        reviewed = None
        cache_inventory = None
        for _ in range(2):
            observed_at = time.time()
            census_times.append(observed_at)
            raw = capacity.collect_windows()  # explicit ROOT --reconcile only; never default preparation
            need(isinstance(raw, bytes) and raw, 'Complete raw CIM bytes required')
            fresh(observed_at, time.time())
            census_refs.append(capacity.exclusive_bytes(audit / ('census-' + str(len(census_refs) + 1) + '.json'), raw))
            processes = parse(raw)
            analysis = capacity.classify_processes(processes, observed_at, venv_identity=identity)
            no_activity(processes, analysis, owned, inputs['binding'], inputs['other_owned_workers'], capacity, original_pids=original_pids)
            pending = {parse(raw)['session_id'] for raw in snapshot.values() if not parse(raw)['consumed']}
            need(analysis['native_workers_count'] + len(pending - set(analysis['session_ids'])) <= 4,
                 'Global cap4 including nonexpired pending reservations contradicted')
            cli_process_absence(processes, analysis, owned, inputs, capacity)
            current = cache_module.validate_cache(cache_root, inputs['binding'],
                [c['nonce'] for c in cold['closed_calls']], no_redirects=capacity.no_redirects)
            if cache_inventory is not None:
                need(current == cache_inventory, 'Cache changed after terminal absence census')
            cache_inventory = current
            reviewed = review_checked(inputs, cold, current, time.time())
        need(capacity.load_venv_identity() == identity, 'Runtime binary identity changed')
        for key in REF_FIELDS:
            checked(inputs[key])
        for item in inputs['other_owned_workers']:
            checked(item)
        checked(input_ref)
        terminal_checked(inputs, terminal)
        def ready_to_commit():
            transition_guard(check_lock, census_times, reviewed['reviewed_at'])
        ready_to_commit()
        before_ref, after_ref, intent_ref = commit_transition(target, before, snapshot, sealed, audit, capacity, ready_to_commit)
        audit_ref = capacity.exclusive_json(audit / 'CLOTURE-PRIVEE.json', {
            'schema': 'hpc-forest-matrix15-reservation-close-private-receipt-v1', 'verified': True,
            'binding': inputs['binding'], 'input': input_ref, 'before': before_ref, 'after': after_ref,
            'intent': intent_ref, 'censuses': census_refs, 'cache_inventory': cache_inventory,
            'root_review': inputs['root_review'], 'closed_at': time.time(), 'only_consumed_changed': True,
            'session_permanently_excluded': True, 'budget_or_chronology_reset': False})
        output.mkdir(parents=True, exist_ok=False)
        receipt = capacity.exclusive_json(output / 'CLOTURE-PROJECTION.json', {
            'schema': 'hpc-forest-matrix15-reservation-close-projection-v1', 'verified': True,
            'binding': inputs['binding'], 'before_sha256': before_ref['sha256'], 'after_sha256': after_ref['sha256'],
            'private_audit_sha256': audit_ref['sha256'], 'private_census_sha256': [r['sha256'] for r in census_refs],
            'consumed': True, 'only_consumed_changed': True, 'sealed_admission_copies_unchanged': True,
            'session_permanently_excluded': True, 'budget_or_chronology_reset': False,
            'full_census_exported': False, 'foreign_configuration_or_credentials_exported': False,
            'native_model_calls': 0, 'jobs_submitted': 0, 'workers_stopped': 0})
        return receipt


def prepare(output):
    output = output_path(output)
    output.mkdir(parents=True, exist_ok=False)
    template = {key: None for key in FIELDS}
    template.update(schema=SCHEMA, mode='PREPARE', output_directory=str(output.parent / (output.name + '-received')))
    for name, value in {'INPUT-TEMPLATE.json': template, 'PREPARATION.json': {
        'schema': SCHEMA, 'mode': 'PREPARE', 'verified': False, 'registry_modified': False,
        'census_collected': False, 'commands_to_execute': [], 'native_model_calls': 0, 'jobs_submitted': 0,
        'workers_stopped': 0, 'authorization_created': False}}.items():
        path = output / name
        with path.open('xb') as stream:
            stream.write(encode(value))
    return ref(output / 'PREPARATION.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--reconcile', action='store_true')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--input-sha256')
    args = parser.parse_args(argv)
    need(not (args.prepare and args.reconcile), 'Choose preparation or explicit reconciliation')
    if not args.reconcile:
        need(args.input is None and args.input_sha256 is None, 'Input requires explicit --reconcile')
        result = prepare(args.prepare or OUTPUT / ('prepare-' + uuid.uuid4().hex))
    else:
        need(args.input is not None and args.input_sha256 is not None, 'Explicit hash-bound input required')
        result = reconcile({'path': str(args.input.absolute()), 'sha256': args.input_sha256})
    print(json.dumps(result))


if __name__ == '__main__':
    main()
