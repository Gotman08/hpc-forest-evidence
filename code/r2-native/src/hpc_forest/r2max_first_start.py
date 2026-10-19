"""Bind the first real delivered call and evaluated candidate; never fabricate admission."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .codex_process import check_cli_metadata_projection
from .core import InfrastructureError, atomic_json, digest, file_digest
from .native_r2max import EFFORT, SCOPE, artifact, cell_binding, read_json, selected_identity

NORMAL_EVALUATIONS = {"valid", "incorrect", "build_failed", "runtime_failed"}


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": file_digest(Path(path))}


def evaluation_provenance(outcome, experiment, *, phase="search"):
    records = []
    for name in outcome.get("logs", []):
        path = Path(name)
        proof_path = path.with_suffix(path.suffix + ".private-execution.json")
        proof = read_json(proof_path)
        context = read_json(artifact(proof.get("context")))
        combined = proof.get("streams", {}).get("combined_stdout_stderr", {})
        if (proof.get("schema") != "hpc-forest-private-evaluation-execution-v2"
                or proof.get("verified") is not True or proof.get("experiment_id") != experiment
                or proof.get("phase") != phase or proof.get("never_model_input") is not True
                or combined.get("sha256") != file_digest(path) or combined.get("bytes") != path.stat().st_size
                or proof.get("hashing_outside_measured_interval") is not True
                or proof.get("execution_semantics_changed") is not False):
            raise ValueError("First real evaluation lacks exact private experiment/phase/raw attribution")
        if (context.get("schema") != "hpc-forest-private-evaluation-context-v1"
                or context.get("never_model_input") is not True or not context.get("argv")
                or any(context.get(key) != proof.get(key) for key in
                       ("experiment_id", "phase", "epoch", "commit", "tree_hash", "operation",
                        "argv", "binary_path", "binary_sha256_before", "private_cases"))
                or proof.get("operation") not in {"build", "check", "benchmark"}
                or (proof["operation"] != "build" and
                    (not proof.get("binary_sha256_before")
                     or proof["binary_sha256_before"] != proof.get("binary_sha256_after")))
                or proof.get("streams", {}).get("layout") != "original_run_process_combined_unchanged"
                or proof["streams"].get("separate_stdout") is not None
                or proof["streams"].get("separate_stderr") is not None):
            raise ValueError("Private context/command/binary/stream-layout attribution differs")
        cases = proof.get("case_execution_records", [])
        if proof["operation"] == "check" and not cases:
            raise ValueError("Correctness log has no private case execution record")
        for case_ref in cases:
            case_path = artifact(case_ref)
            case = read_json(case_path)
            if (case.get("schema") != "hpc-forest-private-case-execution-v2"
                    or case.get("context", {}).get("sha256") != proof["context"]["sha256"]
                    or case.get("experiment_id") != experiment or case.get("phase") != phase
                    or case.get("binary_sha256_before") != proof["binary_sha256_before"]
                    or case.get("binary_sha256_after") != proof["binary_sha256_after"]
                    or not any(row.get("case_sha256") == case.get("case_sha256")
                               and row.get("stdin_sha256") == case.get("stdin_sha256")
                               and row.get("stdin_bytes") == case.get("stdin_bytes")
                               for row in context.get("private_cases", []))):
                raise ValueError("Private case input/phase/binary attribution differs")
            for stream in ("stdout", "stderr"):
                raw = case_path.parent / (stream + ".bin")
                if (case.get(stream, {}).get("file") != raw.name
                        or case[stream].get("sha256") != file_digest(raw)
                        or case[stream].get("bytes") != raw.stat().st_size):
                    raise ValueError("Private actual case stream changed")
            historical = case_path.with_name("execution.json")
            if (case.get("historical_record", {}).get("file") != historical.name
                    or case["historical_record"].get("sha256") != file_digest(historical)):
                raise ValueError("Private historical execution record changed")
        records.append(ref(proof_path))
    if not records:
        raise ValueError("First evaluation has no exact private execution provenance")
    return records


def inspect_call(channel, request_path, authorization):
    model, session = selected_identity(authorization)
    request = read_json(request_path)
    nonce = request.get("nonce", "")
    response_path = channel / "responses" / f"{nonce}.response.json"
    ready_path = channel / "responses" / f"{nonce}.ready.json"
    invocation_path = channel / "logs" / f"{nonce}.invocation.json"
    delivery_path = channel / "logs" / f"{nonce}.delivered.json"
    process_path = channel / "logs" / f"{nonce}.codex.jsonl.json"
    log_path = channel / "logs" / f"{nonce}.codex.jsonl"
    end = time.monotonic() + 15
    while not delivery_path.is_file() and time.monotonic() < end:
        time.sleep(0.1)
    response, ready = read_json(response_path), read_json(ready_path)
    invocation_projection, delivered, process_projection = read_json(invocation_path), read_json(delivery_path), read_json(process_path)
    cli = read_json(artifact(authorization["artifacts"]["cli_identity"]))
    invocation, argv = check_cli_metadata_projection(invocation_projection, "invocation", cli, model)
    process, process_argv = check_cli_metadata_projection(process_projection, "process", cli, model)
    if (argv != process_argv or any(invocation_projection[key] != process_projection[key] for key in
            ("private_argv_sha256", "private_skill_override_sha256", "task_cli_policy_sha256", "private_skill_path_count"))):
        raise ValueError("Private CLI metadata projections do not bind the same invocation")
    request_sha, response_sha = file_digest(request_path), file_digest(response_path)
    if not isinstance(request.get("mission_id"), str):
        raise ValueError("Normal request has no mission identity")
    identity = {"model": model, "reasoning_effort": EFFORT, "session_id": session}
    if (request.get("kind") != "source-proposal" or any(request.get(k) != v for k, v in identity.items())
            or any(response.get(k) != v for k, v in identity.items())
            or response.get("nonce") != nonce or response.get("request_sha256") != request_sha
            or response.get("infrastructure_error") is not False
            or ready.get("sha256") != response_sha or ready.get("bytes") != response_path.stat().st_size
            or delivered.get("request_sha256") != request_sha or delivered.get("response_sha256") != response_sha
            or delivered.get("scope_id") != SCOPE or delivered.get("session_id") != session
            or delivered.get("model") != model or delivered.get("effort") != EFFORT
            or delivered.get("job_id") != authorization["job_id"]
            or delivered.get("source_zip_sha256") != authorization["artifacts"]["source_zip"]["sha256"]
            or delivered.get("plan_sha256") != authorization["artifacts"]["plan"]["sha256"]
            or process.get("returncode") != 0 or process.get("timed_out") is not False
            or invocation.get("request_sha256") != request_sha
            or invocation.get("model") != model or invocation.get("reasoning_effort") != EFFORT
            or invocation.get("source_execution_allowed") is not False):
        raise ValueError("Incomplete, failed or unrelated normal native call")
    if (not argv or argv[0] != cli.get("executable_path") or "--model" not in argv
            or argv[argv.index("--model") + 1] != model
            or 'model_reasoning_effort="max"' not in argv):
        raise ValueError("First invocation does not prove the exact admitted CLI/MAX identity")
    usage = response.get("usage", {})
    if (usage.get("token_accounting") != "exact" or type(usage.get("tokens")) is not int
            or usage["tokens"] < 0 or type(usage.get("llm_calls")) is not int
            or usage["llm_calls"] != 1 or usage.get("tool_events") != []
            or usage.get("codex_jsonl_sha256") != file_digest(log_path)):
        raise ValueError("Unknown invocation, usage or tool event blocks extension")
    return {"request": ref(request_path), "response": ref(response_path), "ready": ref(ready_path),
            "invocation": ref(invocation_path), "delivered": ref(delivery_path),
            "process": ref(process_path), "error_and_usage_log": ref(log_path),
            "mission_id": request.get("mission_id"), "mother_call": bool(request.get("meta_role")),
            "normal_delivered": True, "usage_exact": True,
            "known_model_negative": response.get("error") is not None,
            "private_cli_review_required": True, "private_cli_argv_verified": False,
            "private_cli_records": {
                "invocation_sha256": invocation_projection["private_record_sha256"],
                "process_sha256": process_projection["private_record_sha256"],
                "argv_sha256": invocation_projection["private_argv_sha256"],
                "skill_override_sha256": invocation_projection["private_skill_override_sha256"],
                "task_cli_policy_sha256": invocation_projection["task_cli_policy_sha256"]}}


def first_start_receipt(controller, channel, authorization, allocation, output):
    """Called only after a real batch. Negative candidate outcomes remain negative."""
    model, session = selected_identity(authorization)
    result = {"schema": "hpc-forest-primes-r2max-first-start-verified-v1", "scope_id": SCOPE,
              "verified": False, "model": model, "effort": EFFORT, "session_id": session,
              "job_id": allocation["job_id"], "allocation": allocation,
              "source_zip_sha256": authorization["artifacts"]["source_zip"]["sha256"],
              "plan_sha256": authorization["artifacts"]["plan"]["sha256"],
              "preparation_manifest_sha256": authorization["artifacts"]["preparation_manifest"]["sha256"],
              "automatic_extension": False, "extension_to_other_models_allowed": False,
              "hardware_or_process_isolation_proved": False, "blocking_reasons": [],
              "pending_first_real_evaluation": False, "technical_errors_found": False,
              "private_cli_review_required": True, "private_cli_argv_verified": False,
              "verified_scope": "Public CLI projection/response linkage and actual evaluation only; private argv not audited on ARM",
              "admission_artifacts": authorization["artifacts"]}
    try:
        if allocation["job_id"] != authorization["job_id"]:
            raise ValueError("First-start allocation differs from its admission")
        worker_path = channel / "worker-ready.json"
        worker = read_json(worker_path)
        cli = read_json(artifact(authorization["artifacts"]["cli_identity"]))
        expected_worker = {**cell_binding(authorization), "owner": authorization["job_id"], "mode": "codex", "model": model,
                           "reasoning_effort": EFFORT, "session_id": session,
                           "source_zip_sha256": result["source_zip_sha256"],
                           "plan_sha256": result["plan_sha256"],
                           "codex_executable": cli["executable_path"],
                           "codex_cli_version": cli["version"],
                           "codex_executable_sha256": cli["executable_sha256"]}
        if any(worker.get(k) != value for k, value in expected_worker.items()):
            raise ValueError("First-start worker/CLI is not the admitted normal native worker")
        result["worker_identity"] = ref(worker_path)
        reference_path = output.parent / "runtime-reference-origin.json"
        reference = read_json(reference_path)
        if (reference.get("verified") is not True or reference.get("job_id") != allocation["job_id"]
                or reference.get("reference_origin_is_current_allocation") is not True
                or reference.get("qualification_timings_imported") is not False
                or reference.get("source_zip_sha256") != result["source_zip_sha256"]
                or reference.get("plan_sha256") != result["plan_sha256"]
                or reference.get("native_model_calls") != 0):
            raise ValueError("Reference timings are not from the current native allocation")
        result["runtime_reference_origin"] = ref(reference_path)
        calls = [inspect_call(channel, p, authorization)
                 for p in sorted((channel / "requests").glob("*.request.json"), key=lambda p: p.stat().st_mtime_ns)]
        normal = [call for call in calls if not call["mother_call"]]
        result["all_started_calls_reconciled"] = calls
        rows = controller.db.rows("SELECT id,result FROM trials WHERE result IS NOT NULL ORDER BY created,id")
        if any(json.loads(row["result"]).get("status") in {"infrastructure_error", "usage_unavailable"} for row in rows):
            raise ValueError("A real evaluation/interface infrastructure error blocks continuation")
        first = next((row for row in rows if json.loads(row["result"]).get("status") in NORMAL_EVALUATIONS), None)
        if first is None or not normal:
            result.update(pending_first_real_evaluation=True, invocation_unknown=False,
                          verification_state="known_calls_reconciled_pending_real_evaluation",
                          known_model_outcomes=[{"experiment_id": row["id"],
                                                "status": json.loads(row["result"]).get("status")} for row in rows])
            atomic_json(output, result)
            return result
        outcome = json.loads(first["result"])
        if not any(call["mission_id"] == first["id"] or call["mission_id"].startswith(first["id"] + "-h")
                   for call in normal):
            raise ValueError("First real evaluation is not linked to a delivered normal child call")
        logs = [ref(Path(name)) for name in outcome.get("logs", [])]
        if not logs:
            raise ValueError("First real evaluation has no preserved execution logs")
        private_execution_refs = evaluation_provenance(outcome, first["id"])
        evaluation_path = output.with_name("premiere-evaluation-reelle.json")
        atomic_json(evaluation_path, {"experiment_id": first["id"], "outcome": outcome, "never_model_input": True})
        result.update(verified=True, first_normal_delivered_call=normal[0],
                      all_started_calls_reconciled=calls,
                      first_real_evaluation={"experiment_id": first["id"], "status": outcome["status"],
                                             "correct": outcome.get("correct"), "outcome_sha256": digest(outcome),
                                             "logs": logs, "candidate_negative_preserved": outcome["status"] != "valid"},
                      private_execution_provenance=private_execution_refs,
                      evaluation_snapshot=ref(evaluation_path), registry_path=str(controller.db.path), invocation_unknown=False,
                      technical_errors_found=False)
    except (InfrastructureError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        result["blocking_reasons"].append(type(exc).__name__ + ": " + str(exc))
        result.update(technical_errors_found=True, invocation_unknown=True,
                      verification_state="blocked_technical_or_unknown")
    atomic_json(output, result)
    return result
