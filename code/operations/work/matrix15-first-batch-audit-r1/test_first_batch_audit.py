"""NEUTRAL filesystem fixtures only; zero actual model, CLI, transport, or job calls.

The only external identity seam replaces the four production binary pins with
four synthetic files. Source127, its actual archive, validators and real static
60-cell plan are verified. This fixture can never be a production receipt.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("first_batch_audit.py")
SPEC = importlib.util.spec_from_file_location("first_batch_audit_under_test", SCRIPT)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)
ROOT = SCRIPT.parents[2]
PROJECT = ROOT / "work/matrix15-admission-no-cycle-r2/project"
SOURCE = {"project_root": str(PROJECT),
          "source_zip": producer.local_ref(ROOT / "outputs/HPC-Forest-Matrice15-Admission-r2/HPC-FOREST-MATRIX15-ADMISSION-r2.zip"),
          "runtime_manifest": producer.local_ref(ROOT / "outputs/HPC-Forest-Matrice15-Admission-r2/RUNTIME-PRIVE-LOCAL.json")}


class Fixture:
    def __init__(self, root):
        self.root = root
        self.remote = "/gpfs/scratch/NEUTRAL-FIRST-BATCH-NEVER-RUN"
        self.received, self.locals, self.counter = [], [], 0

    def raw(self, filename, data):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return producer.local_ref(path)

    def local(self, filename, value):
        return self.raw(filename, producer.encoded(value))

    def receive(self, remote, value=None, raw=None):
        self.counter += 1
        local = self.raw(f"received/{self.counter}.bin", raw if raw is not None else producer.encoded(value))
        original = {"path": remote, "sha256": local["sha256"]}
        result = {"ok": True, "downloaded": remote, "to": local["path"], "bytes": local["bytes"],
                  "verifie": True, "remote_sha256": local["sha256"], "empreinte_locale": local["sha256"],
                  "empreinte_distante": local["sha256"], "transport": "scp"}
        transfer = self.local(f"receipts/{self.counter}.json", {"structuredContent": result, "content": [
            {"type": "text", "text": json.dumps(result)}], "isError": False})
        self.received.append({"remote_ref": original, "local_ref": local, "transfer_receipt": transfer})
        return original

    def evidence(self):
        return producer.Evidence(self.received, self.locals)

    def stream(self, experiment, status="incorrect"):
        log = self.remote + "/results-12345/" + experiment + ".build.log"
        stream = self.receive(log, raw=b"NEUTRAL build result\n")
        sized_stream = {**stream, "bytes": len(b"NEUTRAL build result\n")}
        context = {"schema": "hpc-forest-matrix15-command-context-v1", "mode": "command-stream-v1", "never_model_input": True,
                   "operator_binding": {"mode": "command-stream-v1", "cell_binding": self.binding,
                       "source_runtime_sha256": "7" * 64, "cell_contract_sha256": "8" * 64, "protocol_plan_sha256": "9" * 64},
                   "protocol_id": self.protocol, "operation": "build", "experiment_id": experiment, "epoch": 1,
                   "commit": "a" * 40, "tree_hash": "b" * 40, "phase": "search", "argv": ["/usr/bin/NEUTRAL-build"],
                   "worktree": self.remote + "/tree", "binary_path": self.remote + "/binary", "environment_overrides": {},
                   "source_before": {"commit": "a" * 40, "tree_hash": "b" * 40, "clean": True}, "binary_before": None,
                   "argument_files_before": [], "stdin_layout": "original_run_process_DEVNULL_unchanged", "inherited_environment_captured": False}
        context_ref = self.receive(log + ".command-context.json", context)
        process = {"argv": context["argv"], "returncode": 1 if status == "build_failed" else 0,
                   "seconds": 0.1, "timed_out": False, "log": log}
        process_ref = self.receive(log + ".json", process)
        proof = {**context, "schema": "hpc-forest-matrix15-command-execution-v1", "verified": True,
                 "context": {**context_ref, "bytes": len(producer.encoded(context))}, "source_after": context["source_before"],
                 "binary_after": None, "argument_files_after": [], "returncode": process["returncode"], "timed_out": False,
                 "measured_seconds": 0.1, "original_process_result": {**process_ref, "bytes": len(producer.encoded(process))},
                 "hashing_outside_measured_interval": True, "execution_semantics_changed": False,
                 "streams": {"combined_stdout_stderr": sized_stream, "separate_stdout": None, "separate_stderr": None,
                             "layout": "original_run_process_combined_unchanged"}, "case_execution_records": [],
                 "individual_case_provenance_verified": False, "independent_raw_stdout_per_candidate_verified": False,
                 "independent_performance_audit_verified": False}
        ref = self.receive(log + ".command-stream.json", proof)
        record = {**ref, "bytes": len(producer.encoded(proof)), "mode": "command-stream-v1", "operation": "build",
                  "verified": True, "individual_case_provenance_verified": False, "independent_performance_audit_verified": False}
        return {"status": status, "correct": False, "commit": "a" * 40, "tree_hash": "b" * 40, "logs": [log]}, [record]

    def call(self, nonce, mother=None, *, error=None, events=None):
        client = self.modules[0]
        directory = self.cache / nonce
        directory.mkdir()
        request = {"nonce": nonce, "mission_id": "mother" if mother else "child-1-h1", "meta_role": mother,
                   "model": self.binding["model"], "reasoning_effort": "max", "session_id": self.binding["session_id"],
                   "kind": "source-proposal", "messages": [{"role": "system", "content": "NEUTRAL instructions"},
                       {"role": "user", "content": "NEUTRAL fixture"}], "schema": {"type": "object"}}
        request_raw = producer.encoded(request)
        request_ref = producer.local_ref(self.raw(directory.relative_to(self.root) / "downloaded-request.json", request_raw)["path"])
        self.raw(directory.relative_to(self.root) / "request.json", request_raw)
        argv = producer.expected_argv(client, self.cli["executable_path"], self.binding["model"], self.policy, directory)
        invocation = {"argv": argv, "model": self.binding["model"], "reasoning_effort": "max", "request_sha256": request_ref["sha256"],
                      "hosted_inference": True, "source_execution_allowed": False}
        process = {"argv": argv, "returncode": 0, "timed_out": False, "seconds": 0.1, "log": str(directory / "codex.jsonl")}
        self.local(directory.relative_to(self.root) / "invocation.json", invocation)
        self.local(directory.relative_to(self.root) / "codex.jsonl.json", process)
        self.local(directory.relative_to(self.root) / "generation-claimed.json", {"request_sha256": request_ref["sha256"], "claimed_at": 1001})
        self.raw(directory.relative_to(self.root) / "instructions.txt", b"NEUTRAL instructions")
        self.local(directory.relative_to(self.root) / "output-schema.json", client.wire_schema(request["schema"]))
        self.local(directory.relative_to(self.root) / "agent-result.json", {})
        event_values = events or [{"type": "thread.started", "thread_id": "neutral"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "neutral", "type": "agent_message", "text": "{}"}},
            {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3}}]
        log = self.raw(directory.relative_to(self.root) / "codex.jsonl", b"".join(producer.encoded(e).replace(b"\n", b"") + b"\n" for e in event_values))
        diagnostics = client.diagnostics_from_events(Path(log["path"]))
        diagnostics_ref = self.local(directory.relative_to(self.root) / "cli-diagnostics.json", diagnostics)
        old_model, old_effort = client.MODEL, client.EFFORT
        client.MODEL, client.EFFORT = self.binding["model"], "max"
        try:
            usage, _ = client.usage_from_events(Path(log["path"]))
        finally:
            client.MODEL, client.EFFORT = old_model, old_effort
        usage.update(cli_diagnostics_sha256=diagnostics_ref["sha256"], cli_diagnostic_count=len(diagnostics["findings"]))
        response = {"nonce": nonce, "model": self.binding["model"], "reasoning_effort": "max", "session_id": self.binding["session_id"],
                    "request_sha256": request_ref["sha256"], "infrastructure_error": False, "error": error, "data": {}, "usage": usage}
        response_ref = self.local(directory.relative_to(self.root) / "response.json", response)
        ready = {"sha256": response_ref["sha256"], "bytes": response_ref["bytes"]}
        self.local(directory.relative_to(self.root) / "response-ready.json", ready)
        delivered = {**self.binding, "request_sha256": request_ref["sha256"], "response_sha256": response_ref["sha256"], "delivered_at": 1002}
        self.local(directory.relative_to(self.root) / "delivered.json", delivered)
        channel = self.remote + "/results-12345/mailbox"
        refs = {"request": self.receive(channel + "/requests/" + nonce + ".request.json", raw=request_raw),
                "response": self.receive(channel + "/responses/" + nonce + ".response.json", response),
                "ready": self.receive(channel + "/responses/" + nonce + ".ready.json", ready),
                "delivered": self.receive(channel + "/logs/" + nonce + ".delivered.json", delivered),
                "error_and_usage_log": self.receive(channel + "/logs/" + nonce + ".codex.jsonl", raw=Path(log["path"]).read_bytes())}
        old_policy = client.CLI_POLICY
        client.CLI_POLICY = self.policy
        projections = {}
        try:
            for kind, filename in (("invocation", "invocation.json"), ("process", "codex.jsonl.json")):
                projection = client.cli_metadata_projection(directory / filename, self.policy_ref["sha256"], kind)
                refs[kind] = self.receive(channel + "/logs/" + nonce + "." + filename, projection)
                projections[kind] = projection
        finally:
            client.CLI_POLICY = old_policy
        p = projections["invocation"]
        call = {**refs, "mission_id": request["mission_id"], "mother_call": bool(mother), "mother_phase": mother,
                "normal_delivered": True, "usage_exact": True, "exact_tokens": usage["tokens"], "known_model_negative": error is not None,
                "private_cli_review_required": True, "private_cli_argv_verified": False,
                "private_cli_records": {"invocation_sha256": p["private_record_sha256"], "process_sha256": projections["process"]["private_record_sha256"],
                    "argv_sha256": p["private_argv_sha256"], "skill_override_sha256": p["private_skill_override_sha256"],
                    "task_cli_policy_sha256": self.policy_ref["sha256"]}}
        self.private[nonce] = {name: producer.local_ref(directory / name) for name in producer.CACHE_FILES | {"agent-result.json"}}
        return call


@pytest.fixture
def case(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    f.modules = producer.sealed_source(SOURCE)
    client, native, _batch = f.modules
    plan_path = ROOT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r1/shared-windows/plan-60-v2.json"
    need_plan = json.loads(plan_path.read_bytes())
    plan_ref = f.receive(f.remote + "/plan.json", need_plan)
    subject = native.resolve_subject(need_plan, "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23")
    binding = {"scope_id": native.SCOPE, **{k: subject[k] for k in ("cell_key", "subject_id", "model", "effort", "session_id")},
               "job_id": "12345", "remote_root": f.remote, "source_zip_sha256": producer.ZIP_SHA,
               "plan_sha256": plan_ref["sha256"], "preparation_manifest_sha256": need_plan["preparation_manifest"]["sha256"],
               "r1_contract_sha256": subject["r1_contract_ref"]["sha256"]}
    f.binding, f.protocol = binding, "c" * 64
    f.cache, f.private = tmp_path / "cache", {}
    f.cache.mkdir()
    f.local("cache/CELL-BINDING.json", binding)
    binary_refs = {name: f.raw("binaries/" + name, ("NEUTRAL-" + name).encode()) for name in native.CLI_FILES}
    monkeypatch.setattr(native, "CLI_FILES", {name: ref["sha256"] for name, ref in binary_refs.items()})
    f.locals.extend(binary_refs.values())
    f.policy = {"schema": client.TASK_CLI_POLICY_SCHEMA, **binding, "cli_executable_sha256": binary_refs["codex.exe"]["sha256"],
        "skill_candidate_directories": ["C:\\NEUTRAL-SKILL-NEVER-READ"], "filesystem_metadata_sha256": "d" * 64,
        "is_actual_CLI_discovery_receipt": False, "instruction_or_SKILL_body_read": False,
        "cli_feature_overrides": client.TASK_CLI_FEATURES, "code_mode_host_executable_sha256": client.CODE_MODE_HOST_SHA256}
    f.policy_ref = f.local("cli-policy-" + binding["session_id"] + ".json", f.policy)
    f.cli = {**binding, "executable_path": binary_refs["codex.exe"]["path"], "executable_sha256": binary_refs["codex.exe"]["sha256"],
             "source_execution_allowed": False, "task_cli_policy_sha256": f.policy_ref["sha256"],
             "files": {name: producer.ref2(ref) for name, ref in binary_refs.items()}}
    cli_ref = f.receive(f.remote + "/cli.json", f.cli)
    artifacts = {key: {"path": f.remote + "/unused-" + key + ".json", "sha256": "e" * 64} for key in native.ARTIFACTS}
    artifacts.update(plan=plan_ref, cli_identity=cli_ref, source_zip={"path": f.remote + "/source.zip", "sha256": producer.ZIP_SHA},
                     runtime_manifest={"path": f.remote + "/runtime.json", "sha256": producer.RUNTIME_SHA},
                     preparation_manifest={"path": f.remote + "/prep.json", "sha256": need_plan["preparation_manifest"]["sha256"]})
    f.auth = {"schema": "hpc-forest-matrix15-authorization-v1", **{k: binding[k] for k in
        ("scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id", "remote_root")}, "verified": True,
        "expires_at": 1800000000, "user_messages": ["NEUTRAL fixture never use"], "old_candidates_imported": False,
        "operator_algorithm_advice": False, "native_calls_started_at_authorization": 0, "artifacts": artifacts}
    f.calls = [f.call("a" * 32, "mother-preparation"), f.call("b" * 32)]
    f.outcome, streams = f.stream("child-1")
    identity = {**binding, "protocol_id": f.protocol}
    origin_outcome, origin_records = f.stream("baseline-e1", "valid")
    origin = {"schema": "hpc-forest-matrix15-runtime-reference-origin-v1", "verified": True, **identity,
              "reference_origin_is_current_allocation": True, "qualification_timings_imported": False,
              "experiment_id": "baseline-e1", "command_stream_provenance": origin_records,
              "outcome_sha256": native.digest(origin_outcome)}
    origin_ref = f.receive(f.remote + "/results-12345/runtime-reference-origin.json", origin)
    marker = f.receive(f.remote + "/results-12345/mailbox/OWNER.json", binding)
    worker = f.receive(f.remote + "/results-12345/mailbox/worker-ready.json", binding)
    evaluation = {**identity, "never_model_input": True, "experiment_id": "child-1", "outcome": f.outcome}
    evaluation_ref = f.receive(f.remote + "/results-12345/premiere-evaluation-reelle.json", evaluation)
    f.first = {"schema": "hpc-forest-matrix15-first-start-v1", **identity, "verified": True, "blocking_reasons": [],
        "technical_errors_found": False, "invocation_unknown": False, "automatic_extension": False,
        "extension_to_other_cells_allowed": False, "admission_artifacts": artifacts, "all_started_calls_reconciled": f.calls,
        "first_normal_delivered_call": f.calls[1], "first_real_evaluation": {"experiment_id": "child-1", "status": "incorrect",
            "outcome_sha256": native.digest(f.outcome), "candidate_negative_preserved": True},
        "private_cli_review_required": True, "private_cli_argv_verified": False, "observation_mode": "command-stream-v1",
        "private_case_v2_claimed": False, "evaluation_snapshot": evaluation_ref, "channel_owner": marker, "worker_identity": worker,
        "runtime_reference_origin": origin_ref, "command_stream_provenance": streams,
        "usage_and_mother_reconciliation": {"registry_costs": {"exact_tokens_used": 20, "unknown_usage_calls": 0,
            "bounded_usage_calls": 0}, "all_delivered_tokens_exact": 20, "budget_or_chronology_reset": False,
            "mother_claims": {"preparation": {"status": "complete", "model_calls": 1, "delivered_calls_reconciled": 1}}}}
    first_ref = f.receive(f.remote + "/results-12345/premier-demarrage-verifie.json", f.first)
    f.snapshot = {"schema": "hpc-forest-matrix15-first-batch-paused-v1", **identity, "first_batch_completed": True,
        "first_start_receipt": first_ref, "evaluation_snapshot": evaluation_ref, "first_start_public_verified": True,
        "existing_campaign_deadline": 1800000000, "existing_search_deadline": 1799999880,
        "budget_or_chronology_reset": False, "new_requests_created": 0, "private_cli_argv_verified_on_ARM": False,
        "waiting_for_external_root_audit": True}
    snapshot_ref = f.receive(f.remote + "/results-12345/premier-batch-en-attente.json", f.snapshot)
    auth_ref = f.receive(f.remote + "/authorization.json", f.auth)
    f.input = {"schema": producer.INPUT_SCHEMA, "evidence_origin": "received", "source": SOURCE,
        "authorization": auth_ref, "paused_snapshot": snapshot_ref, "received": f.received, "local_refs": f.locals,
        "cache_root": str(f.cache), "private_nonces": f.private, "policy_ref": f.policy_ref,
        "output_directory": str(tmp_path / "PROPOSAL-NEUTRAL-NEVER-INSTALL")}
    return f


def test_real_sealed_source_and_full_neutral_graph_with_negative_preserved(case):
    result = producer.audit(case.input, now=1799999000)
    assert result[0]["exact_tokens_all_calls"] == 20
    assert result[0]["candidate_negative_preserved"] is True
    assert result[0]["independent_SQLite_snapshot_reaudited"] is False
    assert result[0]["release_installed"] is False


def test_source_renderer_parity_with_current_constructor(case, monkeypatch, tmp_path):
    client = case.modules[0]
    previous_policy, previous_model = client.CLI_POLICY, client.MODEL
    client.CLI_POLICY, client.MODEL = case.policy, case.binding["model"]
    monkeypatch.setattr(client.shutil, "which", lambda _: case.cli["executable_path"])
    try:
        request = case.evidence().read(case.calls[1]["request"])
        expected = producer.expected_argv(client, case.cli["executable_path"], case.binding["model"], case.policy, tmp_path / "render-only")
        assert expected == client.command_for(request, tmp_path / "render-only", case.cli["executable_path"])
    finally:
        client.CLI_POLICY, client.MODEL = previous_policy, previous_model


def test_output_proposals_pass_unchanged_native_validator_and_have_no_private_paths(case):
    input_ref = case.local("input.json", case.input)
    receipt = producer.run(input_ref["path"], input_ref["sha256"], produce=True)
    output = Path(case.input["output_directory"])
    assert producer.parse(Path(receipt["path"]).read_bytes())["source127_validate_first_batch_release_passed"] is True
    projection = producer.parse((output / "audit-cli-prive-digest.json").read_bytes())
    assert str(case.cache) not in json.dumps(projection)
    assert "NEUTRAL-SKILL" not in json.dumps(projection)
    private = producer.parse((output / "AUDIT-PRIVE.json").read_bytes())
    assert "projection_sha256" not in private
    assert private["original_evaluation_outcome"]["status"] == "incorrect"
    with pytest.raises(producer.Refusal, match="Fresh absent"):
        producer.run(input_ref["path"], input_ref["sha256"], produce=True)


def test_default_prepare_cannot_claim_a_release(case):
    case.input["evidence_origin"] = "prepared"
    input_ref = case.local("input.json", case.input)
    receipt = producer.run(input_ref["path"], input_ref["sha256"])
    value = producer.parse(Path(receipt["path"]).read_bytes())
    assert value["verified"] is False
    assert value["native_model_calls"] == 0
    assert not (Path(case.input["output_directory"]) / "audit-cli-prive-digest.json").exists()


@pytest.mark.parametrize("field,value", [("evidence_origin", "prepared"), ("evidence_origin", "neutral")])
def test_no_production_prepared_or_neutral_switch(case, field, value):
    case.input[field] = value
    with pytest.raises(producer.Refusal, match="Only actual received"):
        producer.audit(case.input, now=1799999000)


def test_foreign_nonce_even_without_started_call_blocks(case):
    (case.cache / ("f" * 32)).mkdir()
    with pytest.raises(producer.Refusal, match="omits or adds"):
        producer.audit(case.input, now=1799999000)


def test_missing_mother_private_cache_blocks(case):
    del case.private["a" * 32]
    with pytest.raises(producer.Refusal, match="omits or adds"):
        producer.audit(case.input, now=1799999000)


def test_unknown_mother_claim_blocks_without_replay(case):
    first = copy.deepcopy(case.first)
    first["usage_and_mother_reconciliation"]["mother_claims"]["preparation"]["status"] = "started_without_final_response"
    with pytest.raises(producer.Refusal, match="mother claim"):
        producer.audit_calls(first, case.auth, case.binding, str(case.cache), case.private, case.policy_ref, case.evidence(), case.modules[0])


def test_resealed_private_argv_policy_drift_blocks(case):
    nonce = "b" * 32
    directory = case.cache / nonce
    for filename in ("invocation.json", "codex.jsonl.json"):
        record = producer.parse((directory / filename).read_bytes())
        record["argv"][record["argv"].index('--model') + 1] = "gpt-6-astra"
        (directory / filename).write_bytes(producer.encoded(record))
        case.private[nonce][filename] = producer.local_ref(directory / filename)
    # Resealing the raw digest alone must never authorize a changed argv.
    case.first["all_started_calls_reconciled"][1]["private_cli_records"]["invocation_sha256"] = case.private[nonce]["invocation.json"]["sha256"]
    with pytest.raises(producer.Refusal, match="Private argv"):
        producer.audit_calls(case.first, case.auth, case.binding, str(case.cache), case.private, case.policy_ref, case.evidence(), case.modules[0])


@pytest.mark.parametrize("events", [
    [{"type": "error", "message": "failed to load local skill"}, {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}],
    [{"type": "warning", "message": "unknown configuration"}, {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}],
    [{"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}, {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}],
    [{"type": "turn.completed", "usage": {"input_tokens": None, "output_tokens": 1}}],
    [{"type": "item.completed", "item": {"id": "tool", "type": "command_execution", "text": "forbidden"}},
     {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}],
])
def test_resealed_known_cli_errors_unknown_usage_tools_block(case, events):
    # Rebuild a separate fresh nonce/refs using the same production-shaped input
    # instead of merely breaking an outer hash, so semantic refusal is exercised.
    call = case.call("c" * 32, events=events)
    first = copy.deepcopy(case.first)
    first["all_started_calls_reconciled"].append(call)
    with pytest.raises(producer.Refusal, match="diagnostics|Unknown usage"):
        producer.audit_calls(first, case.auth, case.binding, str(case.cache), case.private, case.policy_ref, case.evidence(), case.modules[0])


def test_known_model_negative_remains_allowed_with_clean_exact_transport(case):
    call = case.call("c" * 32, error="Known invalid structured model proposal")
    first = copy.deepcopy(case.first)
    first["all_started_calls_reconciled"].append(call)
    first["usage_and_mother_reconciliation"]["registry_costs"]["exact_tokens_used"] = 30
    first["usage_and_mother_reconciliation"]["all_delivered_tokens_exact"] = 30
    result = producer.audit_calls(first, case.auth, case.binding, str(case.cache), case.private, case.policy_ref, case.evidence(), case.modules[0])
    assert result["calls"][-1]["known_model_negative"] is True
    assert result["exact_tokens_all_calls"] == 30


def test_windows_private_request_reserialization_keeps_original_download_digest(case):
    nonce = "b" * 32
    path = case.cache / nonce / "request.json"
    request = producer.parse(path.read_bytes())
    # core.atomic_json writes text on Windows; the mailbox request itself is bytes.
    path.write_bytes((json.dumps(request, sort_keys=False, indent=2) + "\n").replace("\n", "\r\n").encode())
    case.private[nonce]["request.json"] = producer.local_ref(path)
    result = producer.audit_calls(case.first, case.auth, case.binding, str(case.cache), case.private, case.policy_ref, case.evidence(), case.modules[0])
    assert result["exact_tokens_all_calls"] == 20


@pytest.mark.parametrize("change", ["expired", "reset", "subject", "new_requests"])
def test_resealed_snapshot_change_or_expiry_blocks(case, change):
    snapshot = copy.deepcopy(case.snapshot)
    now = 1799999000
    if change == "expired":
        now = snapshot["existing_search_deadline"]
    elif change == "reset":
        snapshot["existing_search_deadline"] += 120
    elif change == "subject":
        snapshot["subject_id"] = "2020-graph"
    else:
        snapshot["new_requests_created"] = 1
    with pytest.raises(producer.Refusal, match="snapshot|deadline"):
        producer.paused_snapshot(snapshot, case.input["paused_snapshot"], case.first, case.auth, case.binding, now)


def test_received_transfer_hash_not_just_resealed_outer_input(case):
    item = case.received[0]
    item["remote_ref"]["sha256"] = "f" * 64
    with pytest.raises(producer.Refusal, match="download receipt"):
        case.evidence()


@pytest.mark.parametrize("change", ["wrong_transport", "payload_error", "negative_verified", "fixture"])
def test_transfer_semantics_resealed_tampering_blocks(case, change):
    item = case.received[0]
    path = Path(item["transfer_receipt"]["path"])
    raw = producer.parse(path.read_bytes())
    value = raw["structuredContent"]
    if change == "wrong_transport":
        value["transport"] = "NEUTRAL-NO-TRANSPORT"
    elif change == "payload_error":
        value["error"] = "scp failed"
    elif change == "negative_verified":
        value["verified"] = False
    else:
        value["fixture"] = True
    raw["content"][0]["text"] = json.dumps(value)
    path.write_bytes(producer.encoded(raw))
    item["transfer_receipt"] = producer.local_ref(path)
    with pytest.raises(producer.Refusal, match="download receipt|transfer result"):
        case.evidence()


@pytest.mark.parametrize("level", ["outer", "mcp_response", "result"])
@pytest.mark.parametrize("flag,value", [("verified", False), ("test_only", True), ("prepared", True)])
def test_primary_transfer_rejects_negative_at_all_three_levels(case, level, flag, value):
    item = case.received[0]
    path = Path(item["transfer_receipt"]["path"])
    response = producer.parse(path.read_bytes())
    wrapper = {"schema": "hpc-forest-primary-tool-observation-v1", "tool": "mcp__romeo__download_from_romeo",
               "arguments": {"remote_path": item["remote_ref"]["path"], "local_path": item["local_ref"]["path"],
                             "verify": True, "recursive": False}, "response": response}
    if level == "outer":
        wrapper[flag] = value
    elif level == "mcp_response":
        response[flag] = value
    else:
        response["structuredContent"][flag] = value
        response["content"][0]["text"] = json.dumps(response["structuredContent"])
    path.write_bytes(producer.encoded(wrapper))
    item["transfer_receipt"] = producer.local_ref(path)
    with pytest.raises(producer.Refusal, match="transfer result"):
        case.evidence()


def test_private_changes_after_call_audit_are_rehashed(case, monkeypatch):
    original = producer.verify_streams
    def mutate_after_calls(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs["experiment_id"] == "child-1":
            (case.cache / ("b" * 32) / "instructions.txt").write_bytes(b"changed after call audit")
        return result
    monkeypatch.setattr(producer, "verify_streams", mutate_after_calls)
    with pytest.raises(producer.Refusal, match="bytes or digest changed"):
        producer.audit(case.input, now=1799999000)


def test_source_tree_tamper_refused_before_import(case, tmp_path):
    alternate = tmp_path / "changed-source"
    shutil.copytree(PROJECT, alternate)
    (alternate / "src/hpc_forest/codex_process.py").write_bytes(b"raise AssertionError('must never import')\n")
    source = {**SOURCE, "project_root": str(alternate)}
    with pytest.raises(producer.Refusal, match="source127 file differs"):
        producer.sealed_source(source)


def test_cli_no_clock_model_or_neutral_override():
    with pytest.raises(SystemExit):
        producer.main(["--input", "x", "--input-sha256", "a" * 64, "--now", "1"])
    with pytest.raises(SystemExit):
        producer.main(["--input", "x", "--input-sha256", "a" * 64, "--neutral"])
