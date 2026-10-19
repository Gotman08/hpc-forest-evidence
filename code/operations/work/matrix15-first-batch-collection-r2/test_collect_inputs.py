"""NEUTRAL local catalog fixtures only; no actual SCP/model/process is called."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("collection_under_test", Path(__file__).with_name("collect_inputs.py"))
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


@pytest.fixture
def case(tmp_path):
    reader = helper.runtime()
    catalog = []
    counter = 0
    remote = "/gpfs/scratch/NEUTRAL-collection-proof-never-run"
    def local(name, value=None, raw=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else reader.encoded(value))
        return reader.local_ref(path)
    def receive(name, value=None, raw=None):
        nonlocal counter
        counter += 1
        data = local("received/" + str(counter), value, raw)
        original = {"path": remote + "/" + name, "sha256": data["sha256"]}
        payload = {"ok": True, "downloaded": original["path"], "to": data["path"], "bytes": data["bytes"],
                   "transport": "scp", "verifie": True, "remote_sha256": data["sha256"],
                   "empreinte_locale": data["sha256"], "empreinte_distante": data["sha256"]}
        receipt = local("receipts/" + str(counter), {"structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload)}], "isError": False})
        catalog.append({"remote_ref": original, "local_ref": data, "transfer_receipt": receipt})
        return original
    nonce = "a" * 32
    identity = {"scope_id": "scope", "cell_key": "cell", "subject_id": "2020-quicksort", "model": "gpt-6-luna",
                "effort": "max", "session_id": "b" * 32, "job_id": "12345", "remote_root": remote}
    plan = receive("plan.json", {})
    binaries = {name: {k: local("binaries/" + name, raw=("NEUTRAL-" + name).encode())[k] for k in ("path", "sha256")}
                for name in ("codex.exe", "codex-code-mode-host.exe", "codex-command-runner.exe", "codex-windows-sandbox-setup.exe")}
    cli = receive("cli.json", {"files": binaries})
    auth = receive("authorization.json", {**identity, "schema": "hpc-forest-matrix15-authorization-v1", "verified": True,
                                         "artifacts": {"plan": plan, "cli_identity": cli}})
    call = {"request": receive("requests/" + nonce + ".request.json", {"nonce": nonce}),
            "response": receive("response.json", {"error": None}),
            **{key: receive(key + ".json", {}) for key in ("ready", "invocation", "delivered", "process")},
            "error_and_usage_log": receive("codex.jsonl", raw=b"NEUTRAL raw log\n")}
    raw_file = receive("original.log", raw=b"NEUTRAL command log")
    context = receive("context.json", {"schema": "hpc-forest-matrix15-command-context-v1", "binary_before": None,
                                        "argument_files_before": []})
    process = receive("original.log.json", {})
    binary = receive("binary", raw=b"NEUTRAL executable bytes never executed")
    stream = receive("command-stream.json", {"schema": "hpc-forest-matrix15-command-execution-v1", "verified": True,
        "context": context, "original_process_result": process, "streams": {"combined_stdout_stderr": raw_file},
        "binary_before": None, "binary_after": binary, "argument_files_before": [], "argument_files_after": []})
    origin = receive("origin.json", {"schema": "hpc-forest-matrix15-runtime-reference-origin-v1", "verified": True,
                                      "command_stream_provenance": [stream]})
    evaluation = receive("evaluation.json", {"never_model_input": True, "outcome": {"status": "incorrect"}})
    first_value = {"schema": "hpc-forest-matrix15-first-start-v1", "verified": True, "technical_errors_found": False,
        "invocation_unknown": False, "channel_owner": receive("owner.json", {}), "worker_identity": receive("worker.json", {}),
        "runtime_reference_origin": origin, "evaluation_snapshot": evaluation, "all_started_calls_reconciled": [call],
        "first_real_evaluation": {"logs": [raw_file]}, "command_stream_provenance": [stream]}
    first = receive("first.json", first_value)
    snapshot = receive("paused.json", {"schema": "hpc-forest-matrix15-first-batch-paused-v1",
        "waiting_for_external_root_audit": True, "first_start_receipt": first, "evaluation_snapshot": evaluation})
    cache = tmp_path / "cache"
    for name in reader.CACHE_FILES | {"agent-result.json"}:
        local("cache/" + nonce + "/" + name, {})
    local("cache/CELL-BINDING.json", identity)
    policy = local("policy.json", {})
    value = {"schema": helper.SCHEMA, "mode": "COLLECT", "authorization": auth, "paused_snapshot": snapshot,
             "catalog": catalog, "local_refs": [], "external_program_copies": [], "cache_root": str(cache), "policy_ref": policy,
             "audit_output_directory": str(tmp_path / "future-audit"), "output_directory": str(tmp_path / "out")}
    return reader, value, receive, local, first_value


def test_complete_graph_proposes_input_without_invoking_audit(case):
    reader, value, _receive, _local, _first = case
    result = helper.collect(value, reader)
    assert result["collection_complete"] is True
    assert result["verified"] is False
    assert result["audit_invoked"] is False
    assert result["audit_input"]["schema"] == reader.INPUT_SCHEMA
    assert len(result["audit_input"]["local_refs"]) == 4
    assert set(result["audit_input"]["private_nonces"]) == {"a" * 32}
    assert not Path(value["audit_output_directory"]).exists()


def test_missing_download_is_returned_exactly_without_prefix_rewrite(case):
    reader, value, _receive, _local, _first = case
    missing = value["catalog"].pop(0)
    result = helper.collect(value, reader)
    assert result["collection_complete"] is False
    assert result["audit_input"] is None
    assert result["missing_remote"][0]["remote_ref"] == missing["remote_ref"]


def test_conflicting_sha_for_original_path_is_rejected(case):
    reader, value, receive, _local, first = case
    other = copy.deepcopy(receive("different-log", raw=b"changed"))
    other["path"] = first["first_real_evaluation"]["logs"][0]["path"]
    first["first_real_evaluation"]["logs"].append(other)
    new_first = receive("changed-first.json", first)
    snapshot = {"schema": "hpc-forest-matrix15-first-batch-paused-v1", "waiting_for_external_root_audit": True,
                "first_start_receipt": new_first, "evaluation_snapshot": first["evaluation_snapshot"]}
    value["paused_snapshot"] = receive("changed-paused.json", snapshot)
    with pytest.raises(ValueError, match="Conflicting SHA"):
        helper.collect(value, reader)


def test_unknown_nonce_in_cache_blocks_closed_input(case):
    reader, value, _receive, local, _first = case
    local("cache/" + ("f" * 32) + "/generation-claimed.json", {})
    result = helper.collect(value, reader)
    assert result["collection_complete"] is False
    assert result["audit_input"] is None
    assert "foreign nonces" in result["blockers"][0]


def test_missing_private_file_keeps_input_open(case):
    reader, value, _receive, _local, _first = case
    # Point to another absent cache; all originals remain preserved.
    value["cache_root"] = str(Path(value["cache_root"]).parent / "absent-cache")
    result = helper.collect(value, reader)
    assert result["collection_complete"] is False
    assert result["missing_private"]


def test_unknown_schema_refuses_instead_of_guessing_graph(case):
    reader, value, receive, _local, _first = case
    value["paused_snapshot"] = receive("unknown.json", {"schema": "future-unknown"})
    with pytest.raises(ValueError, match="Unknown/unpaused"):
        helper.collect(value, reader)


def test_request_body_foreign_nonce_cannot_close(case):
    reader, value, receive, _local, first = case
    first["all_started_calls_reconciled"][0]["request"] = receive("requests/" + "a" * 32 + ".request.json", {"nonce": "c" * 32})
    # Replace original same-path download with its new version; conflicting old
    # catalog copies are deliberately removed to exercise semantic nonce refusal.
    old_request = value["catalog"][3]["remote_ref"]
    value["catalog"][:] = [entry for entry in value["catalog"] if entry["remote_ref"] != old_request]
    new_first = receive("foreign-first.json", first)
    value["paused_snapshot"] = receive("foreign-paused.json", {"schema": "hpc-forest-matrix15-first-batch-paused-v1",
        "waiting_for_external_root_audit": True, "first_start_receipt": new_first, "evaluation_snapshot": first["evaluation_snapshot"]})
    with pytest.raises(ValueError):
        helper.collect(value, reader)


def test_model_payload_ref_is_not_traversed(case):
    reader, value, receive, _local, first = case
    first["all_started_calls_reconciled"][0]["response"] = receive("model-response-with-data.json", {"error": None,
        "data": {"path": "/unrequested/model-path", "sha256": "f" * 64}})
    new_first = receive("model-payload-first.json", first)
    value["paused_snapshot"] = receive("model-payload-paused.json", {"schema": "hpc-forest-matrix15-first-batch-paused-v1",
        "waiting_for_external_root_audit": True, "first_start_receipt": new_first, "evaluation_snapshot": first["evaluation_snapshot"]})
    result = helper.collect(value, reader)
    assert result["collection_complete"] is True
    assert not result["missing_remote"]


def test_prepare_default_cannot_propose_input(case):
    reader, value, _receive, _local, _first = case
    value["mode"] = "PREPARE"
    assert helper.collect(value, reader)["audit_input"] is None


def test_output_is_exclusive_and_writes_only_proposal(case, tmp_path, monkeypatch):
    reader, value, _receive, local, _first = case
    monkeypatch.setattr(helper, "DEST", tmp_path)
    input_ref = local("input.json", value)
    receipt = helper.run(input_ref["path"], input_ref["sha256"])
    assert reader.parse(Path(receipt["path"]).read_bytes())["collection_complete"] is True
    assert (Path(value["output_directory"]) / "INPUT-AUDIT-PROPOSITION.json").is_file()
    assert not Path(value["audit_output_directory"]).exists()
    with pytest.raises(ValueError, match="Fresh"):
        helper.run(input_ref["path"], input_ref["sha256"])


def test_catalog_negative_receipt_is_not_promoted(case):
    reader, value, _receive, local, _first = case
    entry = value["catalog"][0]
    raw = reader.parse(Path(entry["transfer_receipt"]["path"]).read_bytes())
    raw["structuredContent"]["verifie"] = False
    raw["content"][0]["text"] = json.dumps(raw["structuredContent"])
    entry["transfer_receipt"] = local("failed-receipt.json", raw)
    with pytest.raises(ValueError, match="download receipt"):
        helper.collect(value, reader)


def test_sqlite_wal_is_not_added_to_download_frontier(case):
    reader, value, receive, _local, first = case
    first["first_real_evaluation"]["logs"].append({"path": "/gpfs/scratch/registry.sqlite3-wal", "sha256": "f" * 64})
    new_first = receive("sqlite-ref-first.json", first)
    value["paused_snapshot"] = receive("sqlite-ref-paused.json", {"schema": "hpc-forest-matrix15-first-batch-paused-v1",
        "waiting_for_external_root_audit": True, "first_start_receipt": new_first, "evaluation_snapshot": first["evaluation_snapshot"]})
    with pytest.raises(ValueError, match="SQLite/WAL"):
        helper.collect(value, reader)


def test_missing_external_copy_requires_two_actual_original_scp_refs(case):
    reader, value, _receive, _local, _first = case
    root = reader.EXTERNAL_COPY_ROOT
    refs = {"manifest_ref": {"path": root + "/manifest.json", "sha256": "d" * 64},
            "copy_ref": {"path": root + "/bin-sh", "sha256": reader.EXTERNAL_SHELL_SHA}}
    value["external_program_copies"] = [refs]
    result = helper.collect(value, reader)
    assert result["collection_complete"] is False
    assert {r["remote_ref"]["path"] for r in result["missing_remote"]} == {r["path"] for r in refs.values()}
    assert all(r["remote_ref"]["path"] != "/bin/sh" for r in result["missing_remote"])
    assert result["audit_input"] is None


def test_unknown_external_packet_fields_are_refused_before_traversal(case):
    reader, value, _receive, _local, _first = case
    value["external_program_copies"] = [{"waiver": "/bin/sh"}]
    with pytest.raises(reader.Refusal, match="Exact external copy packet"):
        helper.collect(value, reader)
