"""Reconcile one matrix cell's real calls and generic command observations.

This observer neither starts calls nor promotes command streams to per-case proof.
All model, usage and negative-outcome checks precede any continuation receipt.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .codex_process import check_cli_metadata_projection
from .core import InfrastructureError, atomic_json, digest, file_digest
from .matrix15_provenance import command_stream_provenance
from .native_matrix15 import EFFORT, artifact, cell_binding, read_json, selected_identity

NORMAL_EVALUATIONS = {"valid", "incorrect", "build_failed", "runtime_failed"}


def ref(path):
    path = Path(path)
    return {"path": str(path.resolve()), "sha256": file_digest(path)}


def _write_once_or_same(path, value):
    if path.exists():
        if read_json(path) != value:
            raise InfrastructureError("An immutable observation already exists with different bytes")
    else:
        atomic_json(path, value)


def inspect_call(channel, request_path, authorization):
    """Inspect a delivery already started by the owned worker, including mother calls."""
    channel, request_path = Path(channel), Path(request_path)
    model, session = selected_identity(authorization)
    binding = cell_binding(authorization)
    request = read_json(request_path)
    nonce = request.get("nonce", "")
    if not re.fullmatch(r"[0-9a-f]{32}", nonce) or request_path.name != nonce + ".request.json":
        raise InfrastructureError("Request nonce/path identity differs")
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
    invocation_projection = read_json(invocation_path)
    delivered, process_projection = read_json(delivery_path), read_json(process_path)
    cli = read_json(artifact(authorization["artifacts"]["cli_identity"]))
    invocation, argv = check_cli_metadata_projection(invocation_projection, "invocation", cli, model)
    process, process_argv = check_cli_metadata_projection(process_projection, "process", cli, model)
    if (argv != process_argv or any(invocation_projection[key] != process_projection[key] for key in
            ("private_argv_sha256", "private_skill_override_sha256", "task_cli_policy_sha256", "private_skill_path_count"))):
        raise InfrastructureError("Private CLI projections do not bind one invocation")
    request_sha, response_sha = file_digest(request_path), file_digest(response_path)
    identity = {"model": model, "reasoning_effort": EFFORT, "session_id": session}
    if (not isinstance(request.get("mission_id"), str) or not request["mission_id"]
            or request.get("meta_role") not in {None, "mother-preparation", "mother-synthesis"}
            or request.get("kind") != "source-proposal"
            or any(request.get(key) != value for key, value in identity.items())
            or any(response.get(key) != value for key, value in identity.items())
            or response.get("nonce") != nonce or response.get("request_sha256") != request_sha
            or response.get("infrastructure_error") is not False
            or ready.get("sha256") != response_sha or ready.get("bytes") != response_path.stat().st_size
            or delivered.get("request_sha256") != request_sha or delivered.get("response_sha256") != response_sha
            or any(delivered.get(key) != value for key, value in binding.items())
            or process.get("returncode") != 0 or process.get("timed_out") is not False
            or invocation.get("request_sha256") != request_sha
            or invocation.get("model") != model or invocation.get("reasoning_effort") != EFFORT
            or invocation.get("source_execution_allowed") is not False):
        raise InfrastructureError("Incomplete, failed or unrelated normal matrix call")
    if (not argv or argv[0] != cli.get("executable_path") or "--model" not in argv
            or argv[argv.index("--model") + 1] != model or 'model_reasoning_effort="max"' not in argv):
        raise InfrastructureError("Invocation does not prove the admitted CLI/MAX identity")
    usage = response.get("usage", {})
    if (usage.get("token_accounting") != "exact" or type(usage.get("tokens")) is not int
            or usage["tokens"] < 0 or type(usage.get("llm_calls")) is not int or usage["llm_calls"] != 1
            or usage.get("tool_events") != [] or usage.get("codex_jsonl_sha256") != file_digest(log_path)):
        raise InfrastructureError("Unknown usage or tool events block continuation")
    return {"request": ref(request_path), "response": ref(response_path), "ready": ref(ready_path),
            "invocation": ref(invocation_path), "delivered": ref(delivery_path), "process": ref(process_path),
            "error_and_usage_log": ref(log_path), "mission_id": request["mission_id"],
            "mother_call": bool(request.get("meta_role")), "mother_phase": request.get("meta_role"),
            "normal_delivered": True, "usage_exact": True, "exact_tokens": usage["tokens"],
            "known_model_negative": response.get("error") is not None,
            "private_cli_review_required": True, "private_cli_argv_verified": False,
            "private_cli_records": {"invocation_sha256": invocation_projection["private_record_sha256"],
                "process_sha256": process_projection["private_record_sha256"],
                "argv_sha256": invocation_projection["private_argv_sha256"],
                "skill_override_sha256": invocation_projection["private_skill_override_sha256"],
                "task_cli_policy_sha256": invocation_projection["task_cli_policy_sha256"]}}


def reconcile_usage_and_mothers(controller, calls):
    """Missing published calls or unresolved local mother claims must not disappear."""
    costs = controller.db.costs()
    if (any(type(costs.get(key)) is not int or costs[key] != 0
            for key in ("unknown_usage_calls", "bounded_usage_calls"))
            or type(costs.get("exact_tokens_used")) is not int
            or costs["exact_tokens_used"] != sum(call["exact_tokens"] for call in calls)):
        raise InfrastructureError("Registry exact usage does not reconcile every delivered call")
    mothers = {}
    for phase in ("preparation", "synthesis"):
        value = controller.db.get("mother_plan:" + phase)
        phase_calls = [call for call in calls if call.get("mother_phase") == "mother-" + phase]
        if value is None and phase_calls:
            raise InfrastructureError("Delivered mother invocation has no owned controller claim")
        if value is not None:
            if (not isinstance(value, dict)
                    or value.get("status") in {"started_without_final_response", "interrupted_not_replayed"}):
                raise InfrastructureError("Unresolved mother claim blocks continuation without replay")
            model_calls = value.get("model_calls", 0)
            if type(model_calls) is not int or model_calls not in {0, 1} or len(phase_calls) != model_calls:
                raise InfrastructureError("Mother episode claims do not reconcile their exact single invocation")
            mothers[phase] = {"status": value.get("status"), "model_calls": value.get("model_calls", 0),
                              "delivered_calls_reconciled": len(phase_calls)}
    return {"registry_costs": costs, "all_delivered_tokens_exact": costs["exact_tokens_used"],
            "mother_claims": mothers, "budget_or_chronology_reset": False}


def evaluation_provenance(outcome, experiment, *, policy, protocol_id, phase):
    if phase not in {"search", "confirmation"}:
        raise InfrastructureError("Explicit search or confirmation provenance phase required")
    records = command_stream_provenance(outcome, experiment, expected_policy=policy, protocol_id=protocol_id)
    for record in records:
        path = Path(record["path"])
        proof = read_json(path)
        if proof.get("phase") != phase or file_digest(path) != record["sha256"]:
            raise InfrastructureError("Command provenance belongs to another phase or changed after validation")
    return records


def _evaluation_refs(controller, outcome, experiment, binding):
    policy = controller.config.get("execution_provenance", {})
    if (policy.get("mode") != "command-stream-v1" or policy.get("cell_binding") != binding
            or controller.config["protocol"].get("private_execution_audit") is True):
        raise InfrastructureError("Generic provenance must bind this cell without claiming primes case-v2")
    return evaluation_provenance(outcome, experiment, policy=policy,
                                 protocol_id=controller.db.get("protocol_id"), phase="search")


def _reference_origin(controller, authorization, allocation, output, binding):
    epoch = controller.epoch()["id"]
    experiment = f"baseline-e{epoch}"
    records = [row for row in controller.db.evaluations("search", epoch)
               if row["experiment_id"] == experiment]
    if len(records) != 1:
        raise InfrastructureError("Exactly one current-allocation baseline is required")
    outcome = records[0]["outcome"]
    if outcome.get("status") != "valid" or outcome.get("correct") is not True:
        raise InfrastructureError("The current baseline did not pass its unchanged official checker")
    streams = _evaluation_refs(controller, outcome, experiment, binding)
    value = {"schema": "hpc-forest-matrix15-runtime-reference-origin-v1", **binding,
             "verified": True, "allocation": allocation, "protocol_id": controller.db.get("protocol_id"),
             "experiment_id": experiment, "outcome_sha256": digest(outcome), "command_stream_provenance": streams,
             "reference_origin_is_current_allocation": True, "qualification_timings_imported": False,
             "never_model_input": True, "independent_raw_stdout_per_candidate_verified": False,
             "independent_performance_audit_verified": False}
    path = output.parent / "runtime-reference-origin.json"
    _write_once_or_same(path, value)
    return ref(path)


def first_start_receipt(controller, channel, authorization, allocation, output):
    """Observe settled calls after a batch; preserve algorithmic negatives verbatim."""
    channel, output = Path(channel), Path(output)
    model, session = selected_identity(authorization)
    binding = cell_binding(authorization)
    protocol_id = controller.db.get("protocol_id")
    result = {"schema": "hpc-forest-matrix15-first-start-v1", **binding, "protocol_id": protocol_id,
              "verified": False, "allocation": allocation, "automatic_extension": False,
              "extension_to_other_cells_allowed": False, "blocking_reasons": [],
              "pending_first_real_evaluation": False, "technical_errors_found": False,
              "private_cli_review_required": True, "private_cli_argv_verified": False,
              "observation_mode": "command-stream-v1", "private_case_v2_claimed": False,
              "independent_raw_stdout_per_candidate_verified": False,
              "independent_performance_audit_verified": False,
              "verified_scope": "Cell-bound CLI public projection/delivery and generic command streams; private argv pending root audit",
              "admission_artifacts": authorization["artifacts"]}
    try:
        if allocation["job_id"] != binding["job_id"] or not re.fullmatch(r"[0-9a-f]{64}", str(protocol_id)):
            raise InfrastructureError("First-start allocation/protocol differs from admission")
        owner_path, worker_path = channel / "OWNER.json", channel / "worker-ready.json"
        owner, worker = read_json(owner_path), read_json(worker_path)
        cli = read_json(artifact(authorization["artifacts"]["cli_identity"]))
        expected_worker = {**binding, "owner": binding["job_id"], "mode": "codex", "model": model,
                           "reasoning_effort": EFFORT, "session_id": session,
                           "codex_executable": cli["executable_path"], "codex_cli_version": cli["version"],
                           "codex_executable_sha256": cli["executable_sha256"]}
        if (any(owner.get(key) != value for key, value in binding.items())
                or any(worker.get(key) != value for key, value in expected_worker.items())):
            raise InfrastructureError("Worker/channel identity is not the admitted matrix cell")
        result.update(worker_identity=ref(worker_path), channel_owner=ref(owner_path))
        result["runtime_reference_origin"] = _reference_origin(controller, authorization, allocation, output, binding)
        requests = sorted((channel / "requests").glob("*.request.json"), key=lambda path: path.stat().st_mtime_ns)
        calls = [inspect_call(channel, path, authorization) for path in requests]
        result["all_started_calls_reconciled"] = calls
        result["usage_and_mother_reconciliation"] = reconcile_usage_and_mothers(controller, calls)
        normal = [call for call in calls if not call["mother_call"]]
        rows = controller.db.rows("SELECT id,result FROM trials WHERE result IS NOT NULL ORDER BY created,id")
        if any(json.loads(row["result"]).get("status") in {"infrastructure_error", "usage_unavailable"} for row in rows):
            raise InfrastructureError("An evaluation/interface infrastructure error blocks continuation")
        first = next((row for row in rows if json.loads(row["result"]).get("status") in NORMAL_EVALUATIONS), None)
        if first is None or not normal:
            result.update(pending_first_real_evaluation=True, invocation_unknown=False,
                          verification_state="known_calls_reconciled_pending_real_evaluation",
                          known_model_outcomes=[{"experiment_id": row["id"],
                                                "status": json.loads(row["result"]).get("status")} for row in rows])
        else:
            outcome = json.loads(first["result"])
            if not any(call["mission_id"] == first["id"] or call["mission_id"].startswith(first["id"] + "-h") for call in normal):
                raise InfrastructureError("Evaluation is not linked to a delivered normal child call")
            streams = _evaluation_refs(controller, outcome, first["id"], binding)
            evaluation_path = output.with_name("premiere-evaluation-reelle.json")
            _write_once_or_same(evaluation_path, {**binding, "protocol_id": protocol_id,
                "experiment_id": first["id"], "outcome": outcome, "never_model_input": True,
                "observation_mode": "command-stream-v1", "private_case_v2_claimed": False})
            result.update(verified=True, first_normal_delivered_call=normal[0],
                          first_real_evaluation={"experiment_id": first["id"], "status": outcome["status"],
                              "correct": outcome.get("correct"), "outcome_sha256": digest(outcome),
                              "logs": [ref(Path(name)) for name in outcome.get("logs", [])],
                              "candidate_negative_preserved": outcome["status"] != "valid"},
                          command_stream_provenance=streams, evaluation_snapshot=ref(evaluation_path),
                          registry_path=str(controller.db.path), invocation_unknown=False,
                          verification_state="public_linkage_and_generic_commands_verified_private_cli_pending")
    except (InfrastructureError, OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        result["blocking_reasons"].append(type(exc).__name__ + ": " + str(exc))
        result.update(technical_errors_found=True, invocation_unknown=True,
                      verification_state="blocked_technical_or_unknown")
    atomic_json(output, result)
    return result
