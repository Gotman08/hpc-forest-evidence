"""Validate the public first native batch projection without executing received code."""
from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import re
import statistics

from .recompute import EvidenceError, load_json

SUBDIR = Path("evidence/native-first-batch-2026-10-19")
SOURCE_CUTOFF = "2026-10-19T11:11:41.348000+00:00"
AUDIT_CUTOFF = "2026-10-19T11:09:30.683709+00:00"
RECORDED_SEARCH_SCORE = 0.5338473950146169
FIELDS = {
    "schema", "scope", "source_cutoff_utc", "audit_cutoff_utc", "cell", "allocation",
    "provenance", "initial_search", "contemporary_reference", "comparison",
    "model_accounting", "audit", "paused_snapshot", "release_acceptance", "pre_admission_incident",
}
PROVENANCE_FIELDS = {
    "source_archive_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256",
    "protocol_id", "first_start_receipt_sha256", "evaluation_snapshot_sha256",
    "reference_origin_sha256", "paused_snapshot_sha256", "private_audit_sha256",
    "private_audit_digest_sha256", "proposal_receipt_sha256", "cold_reader_sha256",
}
TIMING_FIELDS = {"samples_seconds", "mean_seconds", "sample_stdev_seconds", "outcome_sha256"}
CALL_FIELDS = {"role", "exact_tokens", "usage_exact", "normal_delivered", "request_sha256", "response_sha256"}
ACCOUNTING = {
    "delivered_calls": 2, "registry_slots": 3, "tokens_used": 32765, "tokens_reserved": 0,
    "unknown_usage_calls": 0, "bounded_usage_calls": 0, "exact_tokens_used": 32765,
}
AUDIT = {
    "private_cli_verified": True, "all_private_raws_received_and_hashed": True,
    "argv_matches_projections_and_local_policy": True, "cli_diagnostics_clean": True,
    "raw_skill_paths_exported": False, "independent_SQLite_snapshot_reaudited": False,
    "independent_performance_audit_verified": False, "no_replay": True,
    "new_model_or_budget_authorized": False, "source127_release_validator_passed": True,
    "observation_mode": "command-stream-v1", "private_case_v2_claimed": False,
    "independent_raw_stdout_per_candidate_verified": False, "candidate_command_streams": 6,
    "reference_command_streams": 6, "individual_case_provenance_verified": False,
}
PAUSED = {
    "first_batch_completed": True, "waiting_for_external_root_audit": True,
    "existing_search_deadline": 1792408384.3696613,
    "existing_campaign_deadline": 1792408504.3696613,
    "budget_or_chronology_reset": False, "new_requests_created": 0,
    "release_installed_at_audit": False, "arm_release_acceptance_claimed": False,
    "campaign_completion_claimed": False, "other_cell_launches_claimed": 0,
}
RELEASE = {
    "verified": True, "observed_utc": SOURCE_CUTOFF,
    "receipt_sha256": "60f1bb327a0caa9fbf3d873cf7a4ab967db234728832de9a2f03206798e10c87",
    "release_sha256": "93db932c62fbd0788bf9b3a645cce4d6998c75e8296752fa2be7a968b052b085",
    "budget_or_chronology_reset": False, "replayed_claims": 0, "accepted_before_search_deadline": True,
}
RELEASE_DIGEST_FIELDS = {
    "receipt_sha256", "primary_readback_sha256", "release_sha256",
    "private_cli_audit_sha256", "private_review_receipt_sha256",
}
INCIDENT = {
    "failed_job": "755550", "failed_job_terminal_state": "FAILED", "scientific_clock_started": False,
    "native_model_calls": 0, "diagnostic_job": "755551", "diagnostic_state": "COMPLETED",
    "diagnostic_exit_code": "0:0", "native_source_modified": False,
    "empty_cuda_visibility_missing_before_inline_env": True,
    "empty_cuda_visibility_restored_for_diagnostic": True,
}


def need(condition, message):
    if not condition:
        raise EvidenceError(message)


def closed(value, fields, location):
    need(type(value) is dict and set(value) == set(fields), f"Closed native first-batch fields required: {location}")


def values(value, expected, location):
    for key, wanted in expected.items():
        need(type(value[key]) is type(wanted) and value[key] == wanted,
             f"Native first-batch observation differs: {location}.{key}")


def fixed(value, expected, location):
    closed(value, expected, location)
    values(value, expected, location)


def digest(value, location):
    need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
         f"Invalid native first-batch SHA-256: {location}")


def number(value):
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def same_number(value, expected, location):
    need(number(value) and number(expected)
         and math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-15),
         f"Native first-batch arithmetic differs: {location}")


def timings(value, location):
    samples = value["samples_seconds"]
    need(type(samples) is list and len(samples) == 3 and all(number(t) and t > 0 for t in samples),
         f"Three positive finite native timings required: {location}")
    try:
        mean, stdev = statistics.mean(samples), statistics.stdev(samples)
    except (OverflowError, ValueError) as error:
        raise EvidenceError(f"Invalid native timing arithmetic: {location}") from error
    need(number(value["mean_seconds"]) and value["mean_seconds"] > 0
         and number(value["sample_stdev_seconds"]) and value["sample_stdev_seconds"] >= 0,
         f"Invalid native timing statistic: {location}")
    same_number(value["mean_seconds"], mean, f"{location}.mean_seconds")
    same_number(value["sample_stdev_seconds"], stdev, f"{location}.sample_stdev_seconds")
    digest(value["outcome_sha256"], f"{location}.outcome_sha256")
    return mean


def validate(value):
    """Check the dated projection's closed schema, arithmetic and admission limits."""
    closed(value, FIELDS, "root")
    values(value, {"schema": "hpc-forest-public-native-first-batch-v1",
                   "scope": "initial_search_batch_only", "source_cutoff_utc": SOURCE_CUTOFF,
                   "audit_cutoff_utc": AUDIT_CUTOFF}, "root")
    fixed(value["cell"], {"subject_id": "2020-quicksort", "model": "gpt-6-luna", "effort": "max",
                          "seed": 23, "job_id": "755562"}, "cell")
    fixed(value["allocation"], {"architecture": "aarch64", "nodes": 1, "tasks": 1,
                                "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0,
                                "affinity_cpu_count": 4}, "allocation")
    provenance = value["provenance"]
    closed(provenance, PROVENANCE_FIELDS, "provenance")
    for key in PROVENANCE_FIELDS:
        digest(provenance[key], f"provenance.{key}")

    candidate = value["initial_search"]
    closed(candidate, TIMING_FIELDS | {"status", "correct", "binary_sha256", "recorded_search_score"},
           "initial_search")
    values(candidate, {"status": "valid", "correct": True}, "initial_search")
    digest(candidate["binary_sha256"], "initial_search.binary_sha256")
    candidate_mean = timings(candidate, "initial_search")
    # This is the recorded search score, a different observation from the mean ratio below.
    same_number(candidate["recorded_search_score"], RECORDED_SEARCH_SCORE, "initial_search.recorded_search_score")

    reference = value["contemporary_reference"]
    closed(reference, TIMING_FIELDS | {"current_allocation", "qualification_timings_imported", "sample_stream_sha256"},
           "contemporary_reference")
    values(reference, {"current_allocation": True, "qualification_timings_imported": False}, "contemporary_reference")
    streams = reference["sample_stream_sha256"]
    need(type(streams) is list and len(streams) == 3, "Three reference sample-stream digests required")
    for index, stream in enumerate(streams):
        digest(stream, f"contemporary_reference.sample_stream_sha256[{index}]")
    reference_mean = timings(reference, "contemporary_reference")

    comparison = value["comparison"]
    closed(comparison, {"initial_mean_ratio", "initial_runtime_reduction_fraction", "final_confirmation_received",
                        "scientifically_admitted_gain"}, "comparison")
    values(comparison, {"final_confirmation_received": False, "scientifically_admitted_gain": False}, "comparison")
    ratio, reduction = reference_mean / candidate_mean, 1 - candidate_mean / reference_mean
    need(number(comparison["initial_mean_ratio"]) and comparison["initial_mean_ratio"] > 0,
         "Native first-batch mean ratio must be positive and finite")
    same_number(comparison["initial_mean_ratio"], ratio, "comparison.initial_mean_ratio")
    same_number(comparison["initial_runtime_reduction_fraction"], reduction, "comparison.initial_runtime_reduction_fraction")

    accounting = value["model_accounting"]
    closed(accounting, set(ACCOUNTING) | {"calls"}, "model_accounting")
    values(accounting, ACCOUNTING, "model_accounting")
    calls = accounting["calls"]
    need(type(calls) is list and len(calls) == 2, "Two delivered model calls required; registry slots are not calls")
    for index, (call, role, tokens) in enumerate(zip(calls, ("mother_preparation", "first_optimization"), (15629, 17136))):
        location = f"model_accounting.calls[{index}]"
        closed(call, CALL_FIELDS, location)
        values(call, {"role": role, "exact_tokens": tokens, "usage_exact": True, "normal_delivered": True}, location)
        digest(call["request_sha256"], f"{location}.request_sha256")
        digest(call["response_sha256"], f"{location}.response_sha256")
    need(sum(call["exact_tokens"] for call in calls) == accounting["exact_tokens_used"] == accounting["tokens_used"],
         "Native exact token accounting differs")

    audit = value["audit"]
    closed(audit, set(AUDIT) | {"external_shell"}, "audit")
    values(audit, AUDIT, "audit")
    shell = audit["external_shell"]
    shell_expected = {
        "program": "/bin/sh", "sha256": "7e3a3f9d6715ccab40ba328d2220f59f70133ac164ac491a07c5cff2dc035753",
        "bytes": 1366952, "copy_job_id": "755597", "copy_node": "romeo-a057", "model_calls": 0,
        "copy_received_and_hashed": True,
    }
    closed(shell, set(shell_expected) | {"manifest_sha256"}, "audit.external_shell")
    values(shell, shell_expected, "audit.external_shell")
    digest(shell["manifest_sha256"], "audit.external_shell.manifest_sha256")

    paused = value["paused_snapshot"]
    fixed(paused, PAUSED, "paused_snapshot")
    release = value["release_acceptance"]
    closed(release, set(RELEASE) | RELEASE_DIGEST_FIELDS, "release_acceptance")
    values(release, RELEASE, "release_acceptance")
    for key in RELEASE_DIGEST_FIELDS:
        digest(release[key], f"release_acceptance.{key}")
    need(release["private_cli_audit_sha256"] == provenance["private_audit_digest_sha256"]
         and release["private_review_receipt_sha256"] == provenance["private_audit_sha256"],
         "Release acceptance must refer to the received private audits")
    # The paused snapshot predates the later ARM acceptance; its historical flags remain false.
    need(datetime.fromisoformat(AUDIT_CUTOFF).timestamp()
         <= datetime.fromisoformat(release["observed_utc"]).timestamp()
         < paused["existing_search_deadline"] < paused["existing_campaign_deadline"],
         "Native release chronology or unchanged deadlines differ")

    incident = value["pre_admission_incident"]
    closed(incident, set(INCIDENT) | {"receipt_sha256"}, "pre_admission_incident")
    values(incident, INCIDENT, "pre_admission_incident")
    digest(incident["receipt_sha256"], "pre_admission_incident.receipt_sha256")
    return {
        "cell": dict(value["cell"]), "candidate_samples": len(candidate["samples_seconds"]),
        "reference_samples": len(reference["samples_seconds"]), "delivered_calls": len(calls),
        "registry_slots": accounting["registry_slots"], "exact_tokens_used": accounting["exact_tokens_used"],
        "recorded_search_score": candidate["recorded_search_score"], "initial_mean_ratio": ratio,
        "initial_runtime_reduction_fraction": reduction,
    }


def verify(root: Path):
    return validate(load_json((Path(root) / SUBDIR / "first-batch.json").read_text(encoding="utf-8")))
