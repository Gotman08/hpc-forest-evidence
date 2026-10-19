"""NEUTRAL temporary cache fixtures only; no census, workers, or network."""
from __future__ import annotations

import hashlib
import json

import pytest
from cache_check import BINDING_FIELDS, PROTOCOL, CacheError, validate_cache

NONCE = "b" * 32
BINDING = {"scope_id": "NEUTRAL-scope", "cell_key": "NEUTRAL/cell", "subject_id": "NEUTRAL-subject",
           "model": "NEUTRAL-model", "effort": "max", "session_id": "a" * 32, "job_id": "NEUTRAL-job",
           "remote_root": "/NEUTRAL/root", "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
           "preparation_manifest_sha256": "3" * 64, "r1_contract_sha256": "4" * 64}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_redirects(path):
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise CacheError("Redirect refused")
    return path


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "NEUTRAL-cache"
    root.mkdir()
    write(root / "CELL-BINDING.json", BINDING)
    owner = {**BINDING, "protocol": PROTOCOL, "owner": BINDING["job_id"], "reasoning_effort": "max"}
    write(root / "OWNER.json", owner)
    write(root / "worker-ready.json", {**owner, "mode": "codex", "pid": 123, "started_at": 1,
          "local_python": "C:/NEUTRAL/python.exe", "codex_executable": "C:/NEUTRAL/codex.exe",
          "codex_cli_version": "NEUTRAL-version", "codex_executable_sha256": "5" * 64,
          "authentication": "existing-local-ChatGPT", "weight_digest_available": False, "model_weights_on_romeo": False,
          "task_cli_policy_sha256": "6" * 64, "task_cli_policy_candidate_count": 0, "local_skill_paths_exported": False})
    (root / "worker.lock").write_bytes(b"0")
    add_nonce(root, NONCE)
    return root


def add_nonce(root, nonce):
    local = root / nonce
    local.mkdir()
    identity = {"protocol": PROTOCOL, "session_id": BINDING["session_id"], "nonce": nonce,
                "model": BINDING["model"], "reasoning_effort": "max"}
    request = {**identity, "kind": "source-proposal", "mission_id": "NEUTRAL-mission"}
    write(local / "downloaded-request.json", request)
    write(local / "request.json", request)
    request_sha = sha(local / "downloaded-request.json")
    write(local / "generation-claimed.json", {"request_sha256": request_sha, "claimed_at": 2})
    events = [{"input_tokens": 10, "output_tokens": 3}]
    write(local / "codex.jsonl", {"type": "turn.completed", "usage": events[0]})
    argv = ["C:/NEUTRAL/codex.exe", "exec", "--model", BINDING["model"]]
    write(local / "invocation.json", {"argv": argv, "request_sha256": request_sha,
          "model": BINDING["model"], "reasoning_effort": "max", "source_execution_allowed": False})
    write(local / "codex.jsonl.json", {"argv": argv, "returncode": 0, "timed_out": False, "seconds": 1, "log": "NEUTRAL-log"})
    write(local / "cli-diagnostics.json", {"schema": "hpc-forest-completed-cli-diagnostics-v1", "clean": True, "findings": [],
          "counts": {}, "nonempty_lines_examined": 1, "raw_bytes": (local / "codex.jsonl").stat().st_size,
          "codex_jsonl_sha256": sha(local / "codex.jsonl"), "raw_log_preserved": True,
          "diagnostic_allowlist_or_suppression": False, "process_interrupted_by_this_check": False})
    usage = {"tokens": 13, "token_accounting": "exact", "llm_calls": 1, "events": events,
             "usage_parse_ambiguity": False, "tool_events": [], "codex_jsonl_sha256": sha(local / "codex.jsonl"),
             "cli_diagnostics_sha256": sha(local / "cli-diagnostics.json"), "cli_diagnostic_count": 0}
    write(local / "response.json", {**identity, "request_sha256": request_sha, "infrastructure_error": False,
          "data": None, "error": "NEUTRAL algorithmic negative is preserved", "usage": usage})
    write(local / "response-ready.json", {"sha256": sha(local / "response.json"), "bytes": (local / "response.json").stat().st_size})
    write(local / "delivered.json", {**BINDING, "request_sha256": request_sha,
          "response_sha256": sha(local / "response.json"), "delivered_at": 3})


def mutate(path, transform):
    value = json.loads(path.read_text(encoding="utf-8"))
    transform(value)
    write(path, value)


def check(cache, nonces=None, callback=no_redirects):
    return validate_cache(cache, BINDING, [NONCE] if nonces is None else nonces, no_redirects=callback)


def test_negative_is_accounted_and_inventory_is_stable_without_writes(cache):
    before = {str(path.relative_to(cache)): (sha(path), path.stat().st_mtime_ns)
              for path in cache.rglob("*") if path.is_file()}
    result = check(cache)
    assert result["claims_count"] == 1 and result["exact_tokens"] == 13
    assert result["nonces"] == [NONCE]
    assert len(result["inventory_sha256"]) == 64
    assert result == check(cache)
    assert before == {str(path.relative_to(cache)): (sha(path), path.stat().st_mtime_ns)
                      for path in cache.rglob("*") if path.is_file()}
    assert "argv" not in json.dumps(result)


def test_every_expected_nonce_is_required_and_every_claim_must_be_accounted(cache):
    with pytest.raises(CacheError, match="nonce set"):
        check(cache, [])
    with pytest.raises(CacheError, match="nonce set"):
        check(cache, [NONCE, "c" * 32])
    add_nonce(cache, "c" * 32)
    assert check(cache, [NONCE, "c" * 32])["exact_tokens"] == 26


@pytest.mark.parametrize("name", ["cli-technical-hold.json", "worker-ready.json.tmp", "foreign.json", "mailbox"])
def test_unknown_root_entries_hold_and_temporaries_are_refused(cache, name):
    (cache / name).write_bytes(b"NEUTRAL")
    with pytest.raises(CacheError, match="Unknown cache root"):
        check(cache)


@pytest.mark.parametrize("name", ["response.json.tmp", "cli-technical-hold.json", "foreign.json"])
def test_unknown_nonce_entries_are_refused(cache, name):
    (cache / NONCE / name).write_bytes(b"NEUTRAL")
    with pytest.raises(CacheError, match="Unknown nonce"):
        check(cache)


def test_nested_directory_and_missing_receipt_are_refused(cache):
    (cache / NONCE / "agent-result.json").mkdir()
    with pytest.raises(CacheError, match="Nonregular"):
        check(cache)
    (cache / NONCE / "agent-result.json").rmdir()
    (cache / NONCE / "delivered.json").unlink()
    with pytest.raises(CacheError, match="Incomplete claimed"):
        check(cache)


@pytest.mark.parametrize("filename,key,value", [
    ("generation-claimed.json", "request_sha256", "0" * 64),
    ("response-ready.json", "sha256", "0" * 64),
    ("response-ready.json", "bytes", True),
    ("delivered.json", "session_id", "d" * 32),
    ("delivered.json", "response_sha256", "0" * 64),
    ("delivered.json", "delivered_at", 1),
    ("downloaded-request.json", "model", "NEUTRAL-foreign"),
    ("codex.jsonl.json", "timed_out", True),
    ("codex.jsonl.json", "returncode", True),
    ("cli-diagnostics.json", "clean", False),
])
def test_claim_delivery_and_process_corruption_refused(cache, filename, key, value):
    mutate(cache / NONCE / filename, lambda item: item.update({key: value}))
    with pytest.raises(CacheError):
        check(cache)


@pytest.mark.parametrize("key,value", [("token_accounting", "upper_bound"), ("tokens", 14),
                                      ("llm_calls", True), ("tool_events", ["command_execution"]),
                                      ("usage_parse_ambiguity", True), ("codex_jsonl_sha256", "0" * 64)])
def test_unknown_or_forged_response_usage_refused(cache, key, value):
    local = cache / NONCE
    mutate(local / "response.json", lambda item: item["usage"].update({key: value}))
    write(local / "response-ready.json", {"sha256": sha(local / "response.json"), "bytes": (local / "response.json").stat().st_size})
    mutate(local / "delivered.json", lambda item: item.update(response_sha256=sha(local / "response.json")))
    with pytest.raises(CacheError, match="usage"):
        check(cache)


@pytest.mark.parametrize("extra", [b'NEUTRAL non-JSON warning\n', b'{"type":"warning","message":"NEUTRAL"}\n',
                                   b'{"type":"unknown"}\n', b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'])
def test_raw_diagnostic_unknown_and_duplicate_usage_refused_independently(cache, extra):
    local = cache / NONCE
    log = local / "codex.jsonl"
    log.write_bytes(log.read_bytes() + extra)
    with pytest.raises(CacheError):
        check(cache)


def test_missing_claim_is_not_treated_as_unstarted(cache):
    (cache / NONCE / "generation-claimed.json").unlink()
    with pytest.raises(CacheError, match="Incomplete claimed"):
        check(cache)


def test_infrastructure_failure_is_refused_even_with_hashes_updated(cache):
    local = cache / NONCE
    mutate(local / "response.json", lambda item: item.update(infrastructure_error=True))
    write(local / "response-ready.json", {"sha256": sha(local / "response.json"), "bytes": (local / "response.json").stat().st_size})
    mutate(local / "delivered.json", lambda item: item.update(response_sha256=sha(local / "response.json")))
    with pytest.raises(CacheError, match="technical response"):
        check(cache)


def test_nonce_as_a_root_file_is_refused(cache):
    (cache / ("c" * 32)).write_bytes(b"NEUTRAL")
    with pytest.raises(CacheError, match="Nonregular"):
        check(cache)


def test_duplicate_json_field_and_duplicate_expected_nonce_refused(cache):
    (cache / NONCE / "generation-claimed.json").write_bytes(b'{"request_sha256":"NEUTRAL","request_sha256":"NEUTRAL","claimed_at":2}')
    with pytest.raises(CacheError, match="Duplicate cache JSON"):
        check(cache)
    with pytest.raises(CacheError, match="unique expected"):
        check(cache, [NONCE, NONCE])


def test_root_binding_and_ready_identity_refused(cache):
    mutate(cache / "worker-ready.json", lambda item: item.update(session_id="d" * 32))
    with pytest.raises(CacheError, match="ready identity"):
        check(cache)


def test_redirect_callback_runs_for_every_entry(cache):
    seen = set()

    def track(path):
        seen.add(path)
        return no_redirects(path)

    result = check(cache, callback=track)
    assert cache in seen and cache / NONCE in seen
    assert all(cache / item["path"] in seen for item in result["inventory"])


def test_hardlink_is_refused_without_reading_foreign_target(cache, tmp_path):
    target = tmp_path / "NEUTRAL-target"
    target.write_bytes(b"NEUTRAL")
    (cache / NONCE / "agent-result.json").hardlink_to(target)
    with pytest.raises(CacheError, match="Hard-linked"):
        check(cache)


def test_changed_file_during_validation_is_refused(cache):
    count = 0

    def change(path):
        nonlocal count
        if path == cache:
            count += 1
            if count == 2:
                (cache / "worker.lock").write_bytes(b"00")
        return no_redirects(path)

    with pytest.raises(CacheError, match="changed during validation"):
        check(cache, callback=change)


def test_symlink_is_refused_if_platform_allows_creation(cache, tmp_path):
    target = tmp_path / "NEUTRAL-target"
    target.write_bytes(b"NEUTRAL")
    try:
        (cache / NONCE / "agent-result.json").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is unavailable for this Windows account")
    with pytest.raises(CacheError):
        check(cache)


def test_empty_set_is_allowed_only_for_a_cache_without_claim_directories(cache):
    import shutil

    shutil.rmtree(cache / NONCE)
    assert check(cache, [])["claims_count"] == 0
    assert set(json.loads((cache / "CELL-BINDING.json").read_text())) == BINDING_FIELDS
