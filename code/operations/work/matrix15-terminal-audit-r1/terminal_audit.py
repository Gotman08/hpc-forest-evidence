"""Pure terminal bookkeeping reader. No subprocess, network, model or source imports.

This is deliberately NOT a cold audit of final benchmark streams. It proves that
the terminal producer and scheduler closed the same calls already privately
audited at the first batch. A new call requires a separate private audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

BINDING_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
                  "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
INPUT_SCHEMA = "hpc-forest-matrix15-terminal-cold-input-v1"
RECEIPT_SCHEMA = "hpc-forest-matrix15-terminal-cold-receipt-v1"
SCOPE = "terminal-bookkeeping-and-unchanged-audited-call-set-only"
SHA = re.compile(r"[a-f0-9]{64}")


class Refusal(ValueError):
    pass


def need(test, message):
    if not test:
        raise Refusal(message)


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "Duplicate JSON key")
        value[key] = item
    return value


def parse(raw):
    need(len(raw) <= 16 * 1024 * 1024, "JSON exceeds bounded reader limit")
    return json.loads(raw.decode("utf8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refusal("Non-finite JSON number")))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ordinary(path):
    path = Path(path)
    need(path.is_absolute(), "Local evidence path must be absolute")
    for item in [path, *path.parents]:
        need(not item.is_symlink() and not (hasattr(item, "is_junction") and item.is_junction()),
             "Links and junctions are forbidden")
    need(path.is_file(), "Evidence is not an ordinary existing file")
    return path


def local_ref(path):
    path = ordinary(path)
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}


def checked(ref):
    need(type(ref) is dict and set(ref) == {"path", "sha256", "bytes"}, "Exact sized local reference required")
    need(type(ref["sha256"]) is str and SHA.fullmatch(ref["sha256"]) and type(ref["bytes"]) is int
         and ref["bytes"] >= 0, "Malformed local evidence reference")
    path = ordinary(ref["path"])
    raw = path.read_bytes()
    need(len(raw) == ref["bytes"] and sha(raw) == ref["sha256"], "Local evidence bytes changed")
    return parse(raw)


def finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def payload(wrapper, tool, arguments):
    need(type(wrapper) is dict and set(wrapper) == {"schema", "tool", "arguments", "observed_at", "response"}
         and wrapper["schema"] == "hpc-forest-primary-tool-observation-v1" and wrapper["tool"] == tool
         and wrapper["arguments"] == arguments and finite(wrapper["observed_at"]), "Wrong primary observation")
    response = wrapper["response"]
    need(type(response) is dict and response.get("isError") is False, "Primary MCP result failed")
    value = response.get("structuredContent")
    need(type(value) is dict, "Primary structured MCP payload missing")
    texts = [parse(item["text"].encode("utf8")) for item in response.get("content", []) if item.get("type") == "text"]
    need(texts and all(item == value for item in texts), "MCP text and structured payload disagree")
    return value


def received(item, expected_path):
    need(type(item) is dict and set(item) == {"remote_ref", "local_ref", "transfer_receipt"}, "Exact received packet required")
    remote, local = item["remote_ref"], item["local_ref"]
    need(type(remote) is dict and set(remote) == {"path", "sha256"} and remote["path"] == expected_path
         and remote["sha256"] == local.get("sha256"), "Wrong original remote artifact path/hash")
    value = checked(local)
    raw = checked(item["transfer_receipt"])
    args = raw.get("arguments", {})
    need(set(args) == {"remote_path", "local_path", "verify"} and args["remote_path"] == expected_path
         and Path(args["local_path"]) == Path(local["path"]) and args["verify"] is True,
         "SCP arguments differ from exact source and actual local file")
    transfer = payload(raw, "mcp__romeo__download_from_romeo", args)
    need(transfer.get("ok") is True and transfer.get("transport") == "scp" and transfer.get("verifie") is True
         and transfer.get("downloaded") == expected_path and Path(transfer.get("to", "")) == Path(local["path"])
         and type(transfer.get("bytes")) is int and transfer["bytes"] == local["bytes"]
         and all(transfer.get(key) == remote["sha256"] for key in ("remote_sha256", "empreinte_locale", "empreinte_distante")),
         "Actual SCP three-hash transfer verification failed")
    return value, raw["observed_at"]


def same_binding(value, binding):
    need(type(value) is dict and all(value.get(key) == item for key, item in binding.items()), "Cell binding differs")


def zero_unresolved(costs, tokens):
    need(type(costs) is dict and all(type(costs.get(key)) is int and costs[key] == 0
         for key in ("tokens_reserved", "unknown_usage_calls", "bounded_usage_calls"))
         and all(type(costs.get(key)) is int and costs[key] == tokens for key in ("tokens_used", "exact_tokens_used")),
         "Terminal token usage is unresolved or changed")


def validate(value):
    fields = {"schema", "binding", "status_ref", "efficiency_ref", "artifacts", "first_batch_private_audit", "first_batch_root_review"}
    need(type(value) is dict and set(value) == fields and value["schema"] == INPUT_SCHEMA, "Wrong cold terminal input schema")
    binding = value["binding"]
    need(type(binding) is dict and set(binding) == BINDING_FIELDS and all(type(item) is str and item for item in binding.values()),
         "Exact twelve-field binding required")
    need(binding["scope_id"] == "hpc-forest-matrix15-native-max-r2" and binding["effort"] == "max"
         and re.fullmatch(r"[a-f0-9]{32}", binding["session_id"]) and re.fullmatch(r"[1-9][0-9]*", binding["job_id"])
         and binding["cell_key"] == f"forest-r2/{binding['model']}/max/{binding['subject_id']}/seed-23"
         and binding["remote_root"].startswith("/gpfs/scratch/") and not any(p in {".", ".."} for p in binding["remote_root"].split("/"))
         and all(SHA.fullmatch(binding[key]) for key in ("source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256")),
         "Malformed cell binding")
    job, root = binding["job_id"], binding["remote_root"]
    status_raw, efficiency_raw = checked(value["status_ref"]), checked(value["efficiency_ref"])
    status = payload(status_raw, "mcp__romeo__job_status", {"job_id": job})
    efficiency = payload(efficiency_raw, "mcp__romeo__job_efficiency", {"job_id": job})
    need(status.get("ok") is True and status.get("job_id") == job and status.get("state") == "COMPLETED"
         and status.get("exit_code") == "0:0" and all(status.get(k) is True for k in ("finished", "scheduler_completed", "scheduler_success_observed")),
         "Scheduler did not report successful terminal state")
    need(efficiency.get("ok") is True and efficiency.get("found") is True and efficiency.get("job_id") == job
         and efficiency.get("state") == "COMPLETED" and efficiency.get("exit_code") == "0:0"
         and efficiency.get("alloc_cpus") == 4 and efficiency.get("alloc_gpus") == 0, "Terminal allocation differs")
    artifacts = value["artifacts"]
    paths = {"bootstrap": root + "-admission/bootstrap-result.json", "results": root + f"/results-{job}/results.json",
             "final_reconciliation": root + f"/results-{job}/reconciliation-finale-verifiee.json",
             "confirmations": root + f"/results-{job}/confirmations-finales-verifiees.json"}
    need(type(artifacts) is dict and set(artifacts) == set(paths), "All four terminal artifact packets are required")
    loaded = {key: received(artifacts[key], path) for key, path in paths.items()}
    bootstrap, results, final, confirmations = [loaded[key][0] for key in paths]
    need(bootstrap.get("schema") in {"hpc-forest-matrix15-bootstrap-result-v1", "hpc-forest-matrix15-extension-bootstrap-result-v1"}
         and bootstrap.get("binding") == binding and bootstrap.get("passed") is True and bootstrap.get("admission_accepted") is True
         and bootstrap.get("native_child_launch_attempted") is True and type(bootstrap.get("native_child_returncode")) is int
         and bootstrap["native_child_returncode"] == 0 and bootstrap.get("native_model_calls_before_authorization") == 0
         and finite(bootstrap.get("finished_at")), "Bootstrap was not successfully closed")
    need(status_raw["observed_at"] >= bootstrap["finished_at"] and efficiency_raw["observed_at"] >= bootstrap["finished_at"]
         and all(timestamp >= bootstrap["finished_at"] for _, timestamp in loaded.values()), "Evidence predates terminal bootstrap")
    same_binding(results, binding)
    same_binding(final, binding)
    same_binding(confirmations, binding)
    need(results.get("schema") == "hpc-forest-matrix15-native-single-cell-v1" and results.get("pipeline_complete") is True
         and results.get("five_confirmations_verified") is True and results.get("other_cells_started") == 0
         and results.get("automatic_extension") is False and "error" not in results, "Native pipeline did not close cleanly")
    need(final.get("schema") == "hpc-forest-matrix15-first-start-v1" and final.get("verified") is True
         and final.get("technical_errors_found") is False and final.get("invocation_unknown") is False
         and final.get("blocking_reasons") == [] and final.get("pending_first_real_evaluation") is False, "Final reconciliation is blocked")
    audit, review = checked(value["first_batch_private_audit"]), checked(value["first_batch_root_review"])
    same_binding(audit, binding)
    need(audit.get("schema") == "hpc-forest-matrix15-private-first-batch-review-v1" and audit.get("verified") is True
         and all(audit.get(k) is True for k in ("all_private_raws_received_and_hashed", "argv_matches_projections_and_local_policy", "cli_diagnostics_clean")),
         "Previously audited private call proof missing")
    need(review.get("schema") == "hpc-forest-matrix15-extension-first-batch-root-review-v1" and review.get("verified") is True
         and review.get("evidence_origin") == "received" and review.get("first_binding") == binding
         and review.get("private_review_receipt_sha256") == value["first_batch_private_audit"]["sha256"]
         and review.get("all_private_raws_received_and_hashed") is True and review.get("actual_arm_release_received") is True,
         "Actual ROOT first-batch reception review missing")
    protocol = results.get("protocol_id")
    need(type(protocol) is str and SHA.fullmatch(protocol) and final.get("protocol_id") == protocol
         and confirmations.get("protocol_id") == protocol and audit.get("protocol_id") == protocol, "Protocol differs")
    calls = final.get("all_started_calls_reconciled")
    need(type(calls) is list and calls, "No reconciled terminal calls")
    closed, seen = [], set()
    for call in calls:
        request_path = call.get("request", {}).get("path", "")
        match = re.fullmatch(re.escape(root + f"/results-{job}/mailbox/requests/") + r"([a-f0-9]{32})\.request\.json", request_path)
        need(match is not None, "Terminal request is outside original exact mailbox")
        nonce = match.group(1)
        need(nonce not in seen, "Duplicate terminal call")
        seen.add(nonce)
        known = audit.get("call_bindings", {}).get(nonce)
        need(type(known) is dict and call.get("private_cli_records") == {k: known[k] for k in
             ("invocation_sha256", "process_sha256", "argv_sha256", "skill_override_sha256", "task_cli_policy_sha256")}
             and call.get("invocation", {}).get("sha256") == known.get("invocation_projection_sha256")
             and call.get("process", {}).get("sha256") == known.get("process_projection_sha256"), "New or changed privately unaudited terminal call")
        need(call.get("normal_delivered") is True and call.get("usage_exact") is True and type(call.get("exact_tokens")) is int
             and call["exact_tokens"] >= 0 and type(call.get("known_model_negative")) is bool
             and call.get("mother_phase") in {None, "mother-preparation", "mother-synthesis"}
             and call.get("mother_call") is bool(call.get("mother_phase")), "Unsettled terminal call")
        closed.append({"nonce": nonce, "mother_phase": call["mother_phase"], "exact_tokens": call["exact_tokens"],
                       "known_model_negative": call["known_model_negative"]})
    need(sorted(closed, key=lambda x: x["nonce"]) == sorted(audit.get("calls", []), key=lambda x: x["nonce"])
         and seen == set(audit.get("call_bindings", {})), "Final call set differs from exact audited first-batch set")
    tokens = sum(call["exact_tokens"] for call in closed)
    need(audit.get("exact_tokens_all_calls") == tokens, "First-batch audited usage differs")
    reconciliation = final.get("usage_and_mother_reconciliation", {})
    need(reconciliation.get("budget_or_chronology_reset") is False and reconciliation.get("all_delivered_tokens_exact") == tokens,
         "Final reconciliation reset/usage discrepancy")
    zero_unresolved(reconciliation.get("registry_costs"), tokens)
    zero_unresolved(results.get("costs"), tokens)
    for phase in ("preparation", "synthesis"):
        mother = results.get("mother", {}).get(phase)
        phase_calls = [call for call in closed if call["mother_phase"] == "mother-" + phase]
        if mother is None:
            need(not phase_calls and phase not in reconciliation.get("mother_claims", {}), "Missing terminal mother claim")
        else:
            need(mother.get("status") not in {"started_without_final_response", "interrupted_not_replayed"}
                 and mother.get("model_calls") == len(phase_calls)
                 and reconciliation.get("mother_claims", {}).get(phase) == {"status": mother["status"],
                     "model_calls": mother["model_calls"], "delivered_calls_reconciled": len(phase_calls)}, "Mother claim is unresolved")
    need(confirmations.get("schema") == "hpc-forest-matrix15-final-confirmations-v1" and confirmations.get("verified") is True
         and confirmations.get("confirmation_repetitions") == 5 and confirmations.get("interleaving_owner") == "unchanged-Evaluator.confirm"
         and confirmations.get("best_confirmed") == results.get("best_confirmed"), "Final confirmation source metadata differs")
    best = results["best_confirmed"]
    digests, streams = confirmations.get("evaluation_digests"), confirmations.get("command_stream_provenance")
    need(type(digests) is dict and digests and type(streams) is dict and set(digests) == set(streams)
         and all(type(item) is str and SHA.fullmatch(item) for item in digests.values())
         and digests.get(best.get("experiment_id")) == best.get("evaluation_digest")
         and f"baseline-e{best.get('epoch')}" in digests, "Final confirmation references are incomplete")
    for records in streams.values():
        need(type(records) is list and records and all(type(record) is dict and type(record.get("path")) is str
             and record["path"].startswith(root + f"/results-{job}/") and type(record.get("sha256")) is str
             and not any(part in {".", ".."} for part in record["path"].split("/"))
             and SHA.fullmatch(record["sha256"]) and type(record.get("bytes")) is int and record["bytes"] > 0
             and record.get("mode") == "command-stream-v1" and record.get("verified") is True
             and record.get("operation") in {"build", "check", "benchmark"}
             and record.get("individual_case_provenance_verified") is False
             and record.get("independent_performance_audit_verified") is False for record in records),
             "Malformed source confirmation stream references")
    for artifact in (results, final, confirmations):
        need(all(artifact.get(key) is False for key in ("private_case_v2_claimed", "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified")),
             "Source incorrectly claims independent performance proof")
    return {"schema": RECEIPT_SCHEMA, "verified": True, "verified_scope": SCOPE, "binding": binding,
            "protocol_id": protocol, "closed_calls": sorted(closed, key=lambda x: x["nonce"]), "exact_tokens_all_calls": tokens,
            "source_terminal_reconciliation_verified": True, "scheduler_completed": True,
            "terminal_artifacts": artifacts, "primary_observations": {"status": value["status_ref"], "efficiency": value["efficiency_ref"]},
            "first_batch_private_audit": value["first_batch_private_audit"], "first_batch_root_review": value["first_batch_root_review"],
            "all_terminal_raws_received_and_hashed": False, "independent_performance_audit_verified": False,
            "private_case_v2_claimed": False, "new_model_calls": 0, "no_replay": True, "budget_or_chronology_reset": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true", help="Explicitly perform the cold local read; default is PREPARE only")
    args = parser.parse_args(argv)
    raw = ordinary(args.input).read_bytes()
    need(SHA.fullmatch(args.input_sha256) and sha(raw) == args.input_sha256, "Input hash changed")
    need(args.output.is_absolute() and not args.output.exists(), "New absolute output file required")
    receipt = {"schema": RECEIPT_SCHEMA, "verified": False, "prepared_only": True, "new_model_calls": 0,
               "network_calls": 0, "source_files_modified": False}
    if args.verify:
        receipt = validate(parse(raw))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
