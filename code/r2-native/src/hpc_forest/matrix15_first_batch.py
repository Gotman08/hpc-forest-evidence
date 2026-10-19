"""Cell-bound passive first-batch pause; only an actual root audit releases it."""
from __future__ import annotations

import re
import time
from pathlib import Path

from .core import InfrastructureError, atomic_json, digest, file_digest
from .matrix15_first_start import NORMAL_EVALUATIONS, first_start_receipt
from .native_matrix15 import artifact, cell_binding, read_json


def bound_ref(path):
    return {"path": str(Path(path).resolve()), "sha256": file_digest(Path(path))}


def reconcile_after_batch(controller, channel, authorization, allocation, output, first_verified):
    path = Path(output) / ("reconciliation-en-cours.json" if first_verified else "premier-demarrage-verifie.json")
    receipt = first_start_receipt(controller, channel, authorization, allocation, path)
    if receipt.get("technical_errors_found") is True:
        raise InfrastructureError("Technical/unknown invocation after batch; stop without replay")
    return first_verified or receipt["verified"], receipt


def private_call_bindings(first):
    result = {}
    for call in first["all_started_calls_reconciled"]:
        request = read_json(artifact(call["request"]))
        nonce = request.get("nonce", "")
        private = call.get("private_cli_records", {})
        if (not re.fullmatch(r"[0-9a-f]{32}", nonce) or nonce in result
                or set(private) != {"invocation_sha256", "process_sha256", "argv_sha256",
                                    "skill_override_sha256", "task_cli_policy_sha256"}
                or any(not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in private.values())
                or call.get("private_cli_review_required") is not True or call.get("private_cli_argv_verified") is not False):
            raise InfrastructureError("Every first-batch call needs exact private CLI bindings")
        result[nonce] = {**private, "invocation_projection_sha256": call["invocation"]["sha256"],
                         "process_projection_sha256": call["process"]["sha256"]}
    if not result:
        raise InfrastructureError("No real first-batch calls were available to review")
    return result


def validate_first_batch_release(release, snapshot, first, authorization):
    identity = {**cell_binding(authorization), "protocol_id": first.get("protocol_id")}
    fields = {"schema", "verified", *identity, "paused_snapshot", "first_start_receipt",
              "evaluation_snapshot", "private_cli_audit", "no_replay", "new_model_or_budget_authorized"}
    if (set(release) != fields or release.get("schema") != "hpc-forest-matrix15-first-batch-release-v1"
            or release.get("verified") is not True or any(release.get(key) != value for key, value in identity.items())
            or any(snapshot.get(key) != value for key, value in identity.items())
            or release.get("no_replay") is not True or release.get("new_model_or_budget_authorized") is not False
            or release.get("paused_snapshot") != snapshot["self_ref"]
            or release.get("first_start_receipt") != snapshot["first_start_receipt"]
            or release.get("evaluation_snapshot") != snapshot["evaluation_snapshot"]):
        raise InfrastructureError("Release does not bind the unchanged cell/subject/protocol checkpoint")
    artifact(release["paused_snapshot"])
    receipt = read_json(artifact(release["first_start_receipt"]))
    if (receipt != first or first.get("verified") is not True or first.get("technical_errors_found") is not False
            or first.get("invocation_unknown") is not False or not first.get("first_normal_delivered_call")
            or first.get("first_real_evaluation", {}).get("status") not in NORMAL_EVALUATIONS
            or first.get("private_cli_review_required") is not True or first.get("private_cli_argv_verified") is not False
            or first.get("observation_mode") != "command-stream-v1" or first.get("private_case_v2_claimed") is not False
            or any(first.get(key) != value for key, value in identity.items())):
        raise InfrastructureError("Actual cell-bound delivery and generic evaluation required for release")
    evaluation = read_json(artifact(release["evaluation_snapshot"]))
    if (evaluation.get("never_model_input") is not True
            or any(evaluation.get(key) != value for key, value in identity.items())
            or evaluation.get("experiment_id") != first["first_real_evaluation"]["experiment_id"]
            or evaluation.get("outcome", {}).get("status") != first["first_real_evaluation"]["status"]
            or digest(evaluation.get("outcome")) != first["first_real_evaluation"]["outcome_sha256"]):
        raise InfrastructureError("Release evaluation differs; negative algorithmic outcomes must stay negative")
    audit = read_json(artifact(release["private_cli_audit"]))
    audit_fields = {"schema", "verified", *identity, "first_start_receipt_sha256", "paused_snapshot_sha256",
                    "call_bindings", "all_private_raws_received_and_hashed", "argv_matches_projections_and_local_policy",
                    "cli_diagnostics_clean", "raw_skill_paths_exported", "private_review_receipt_sha256"}
    if (set(audit) != audit_fields or audit.get("schema") != "hpc-forest-matrix15-private-cli-audit-digest-projection-v1"
            or audit.get("verified") is not True or any(audit.get(key) != value for key, value in identity.items())
            or audit.get("first_start_receipt_sha256") != snapshot["first_start_receipt"]["sha256"]
            or audit.get("paused_snapshot_sha256") != snapshot["self_ref"]["sha256"]
            or audit.get("call_bindings") != private_call_bindings(first)
            or any(audit.get(key) is not True for key in ("all_private_raws_received_and_hashed",
                   "argv_matches_projections_and_local_policy", "cli_diagnostics_clean"))
            or audit.get("raw_skill_paths_exported") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", str(audit.get("private_review_receipt_sha256", "")))):
        raise InfrastructureError("Actual hash-linked root private CLI audit required; ARM cannot certify private argv")
    return audit


def wait_first_batch_release(controller, authorization, output, first, *, now=time.time,
                             monotonic=time.monotonic, sleep=time.sleep):
    """Wait within the original clock and reserve; this function creates no call."""
    output = Path(output)
    deadline = min(controller.db.get("deadline") - controller.config["budget"]["confirmation_seconds"],
                   authorization["expires_at"])
    identity = {**cell_binding(authorization), "protocol_id": first.get("protocol_id")}
    first_ref = bound_ref(output / "premier-demarrage-verifie.json")
    snapshot_path = output / "premier-batch-en-attente.json"
    snapshot = {"schema": "hpc-forest-matrix15-first-batch-paused-v1", **identity,
                "first_batch_completed": True, "first_start_receipt": first_ref,
                "evaluation_snapshot": first.get("evaluation_snapshot"), "first_start_public_verified": first.get("verified") is True,
                "existing_campaign_deadline": controller.db.get("deadline"), "existing_search_deadline": deadline,
                "budget_or_chronology_reset": False, "new_requests_created": 0,
                "private_cli_argv_verified_on_ARM": False, "waiting_for_external_root_audit": True}
    if snapshot_path.exists():
        raise InfrastructureError("First-batch checkpoint exists; no overwrite or replay")
    atomic_json(snapshot_path, snapshot)
    snapshot["self_ref"] = bound_ref(snapshot_path)
    end = monotonic() + max(0.0, deadline - now())
    release_path = output / "autorisation-apres-premier-batch.json"
    refused_hashes = set()
    while now() < deadline and monotonic() < end:
        if release_path.is_file():
            checksum = file_digest(release_path)
            if checksum not in refused_hashes:
                try:
                    audit = validate_first_batch_release(read_json(release_path), snapshot, first, authorization)
                except (InfrastructureError, ValueError, OSError, KeyError, TypeError, IndexError) as exc:
                    refused_hashes.add(checksum)
                    atomic_json(output / ("refus-release-" + checksum + ".json"),
                                {"verified": False, **identity, "release_sha256": checksum,
                                 "reason": type(exc).__name__ + ": " + str(exc), "next_batch_started": False})
                else:
                    if now() >= deadline or monotonic() >= end:
                        break
                    atomic_json(output / "premier-batch-release-verifiee.json",
                                {"verified": True, **identity, "release": bound_ref(release_path),
                                 "private_cli_audit": read_json(release_path)["private_cli_audit"],
                                 "private_review_receipt_sha256": audit["private_review_receipt_sha256"],
                                 "budget_or_chronology_reset": False, "replayed_claims": 0})
                    return True
        sleep(min(2.0, max(0.0, deadline - now()), max(0.0, end - monotonic())))
    atomic_json(output / "premier-batch-attente-expiree.json",
                {"verified": False, **identity, "reason": "existing_search_budget_expired_while_waiting_for_actual_audit",
                 "snapshot": snapshot["self_ref"], "existing_search_deadline": deadline,
                 "next_batch_started": False, "budget_or_chronology_reset": False,
                 "model_error_or_response_fabricated": False, "replayed_claims": 0})
    return False
