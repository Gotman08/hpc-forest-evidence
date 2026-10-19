"""Recompute the frozen public R1/R2 article projection with the standard library.

This validates published arithmetic and evidence boundaries. It never executes
received code or upgrades source confirmation into independent performance proof.
"""
from __future__ import annotations

import csv
import hashlib
import math
import statistics
from io import StringIO
from pathlib import Path

from .recompute import EvidenceError, load_json

SUBDIR = Path("docs/article/donnees-r1-r2")
FILE_PINS = {
    "comparison.json": {"bytes": 89218, "sha256": "0c06538d1cc556fadd8cbc7fd7ad3f3238a99f4274765c47b74681c163aa3609"},
    "matrix15-comparison.csv": {"bytes": 13924, "sha256": "296782ea25cc5d66a6a30f3e4dcbd78e6fa750311bb7f3a232a3f1d59d860b87"},
    "timing-samples.csv": {"bytes": 5323, "sha256": "742c929bb0273fa3e56626e56e9831402b4e0efe37bc395757a3366425d438db"},
}
MANIFEST_SHA256 = "f18a0079c3667dc320e6d71a0f9bd306f8263822996357e83aa3204091c8f61c"
MODELS = {"gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra"}
SUBJECTS = {
    "2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
    "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
    "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci",
}
MATRIX_COLUMNS = (
    "subject_id", "model", "effort", "seed", "r1_confirmed", "r1_reference_seconds",
    "r1_candidate_seconds", "r1_gain_fraction", "r1_speedup", "r1_known_exact_tokens",
    "r1_archived_unmetered_native_invocations", "r1_received_reconciled_unmetered_calls",
    "r1_native_calls", "r1_reference_sample_sd_seconds", "r1_candidate_sample_sd_seconds",
    "r1_baseline_retained", "r2_status", "r2_initial_batch_received",
    "r2_source_confirmation_received", "r2_scientifically_admitted_gain",
    "r2_initial_reference_seconds", "r2_initial_candidate_seconds",
    "r2_initial_descriptive_speedup", "r2_source_final_reference_seconds",
    "r2_source_final_candidate_seconds", "r2_source_final_descriptive_speedup",
    "r2_known_exact_tokens", "r2_exact_calls", "scientifically_admitted_pair",
)
TIMING_COLUMNS = (
    "series_id", "edition", "phase", "role", "subject_id", "model", "effort", "seed",
    "sample_index", "seconds", "reference_mean_seconds", "normalized_seconds",
    "evidence_level", "independent_performance_audit_verified",
)
SERIES_FIELDS = {
    "id", "edition", "phase", "role", "subject_id", "model", "effort", "seed",
    "samples_seconds", "n", "mean_seconds", "sample_sd_seconds",
    "reference_mean_seconds", "normalized_samples", "normalized_mean", "evidence_level",
    "independent_performance_audit_verified",
}
SERIES_IDENTITIES = {
    "r1_reference": ("R1", "confirmation", "reference", 5, "received_historical_original_process_metadata"),
    "r1_candidate": ("R1", "confirmation", "candidate", 5, "received_historical_original_process_metadata"),
    "r2_search_reference": ("R2", "initial_search", "reference", 3, "first_batch_cold_generic_command_stream_audit"),
    "r2_search_candidate": ("R2", "initial_search", "candidate", 3, "first_batch_cold_generic_command_stream_audit"),
    "r2_confirmation_reference": ("R2", "confirmation", "reference", 5, "source_confirmed_received_archive_generic_stream_consistency"),
    "r2_confirmation_candidate": ("R2", "confirmation", "candidate", 5, "source_confirmed_received_archive_generic_stream_consistency"),
}
R2_NUMERIC = (
    "r2_initial_reference_seconds", "r2_initial_candidate_seconds", "r2_initial_descriptive_speedup",
    "r2_source_final_reference_seconds", "r2_source_final_candidate_seconds",
    "r2_source_final_descriptive_speedup", "r2_known_exact_tokens", "r2_exact_calls",
)
# Closed, reviewed public snapshot metadata. Only cells and timing arithmetic
# below vary for recomputation; no private source files are required by this tool.
FIXED = load_json(r'''{
  "boundaries": {
    "causal_claim": false,
    "error_bars": "sample_standard_deviation_descriptive_not_confidence_intervals",
    "inferential_significance_claim": false,
    "missing_numeric_csv_cells": "empty_fields_mean_not_measured_never_zero",
    "normalization": "each_phase_sample_divided_by_its_own_run_phase_reference_mean",
    "pipeline_complete_is_one_cell_not_full_matrix": true,
    "private_paths_prompts_code_cli_census_config_exported": false,
    "r1_zero_gain_semantics": "measured_baseline_retained_speedup_one",
    "scientifically_admitted_R2_gain": false,
    "source_confirmed_does_not_mean_independent_performance_audit": true,
    "source_only_job749843_substituted_for_historical_R1": false
  },
  "compiled_at_utc": "2026-10-19T11:59:22+00:00",
  "coverage": {
    "matched_subject_model_keys": 1,
    "matrix_cells": 60,
    "models": 4,
    "r1_historical_confirmed_cells": 60,
    "r1_measured_zero_gains_baseline_retained": 11,
    "r2_cells_without_scientific_measurement": 59,
    "r2_initial_batch_received_cells": 1,
    "r2_scientifically_admitted_gain_cells": 0,
    "r2_source_confirmed_cells": 1,
    "r2_technical_incidents_before_model_cells": 1,
    "scientifically_admitted_pairs": 0,
    "subjects": 15
  },
  "matched_cell": {
    "accounting": {
      "r1_known_exact_tokens": 261707,
      "r1_native_calls": 10,
      "r1_program_trials": 8,
      "r1_received_reconciled_unmetered_calls": 0,
      "r2_bounded_usage_calls": 0,
      "r2_delivered_exact_calls": 2,
      "r2_final_registry_slots": 5,
      "r2_known_exact_tokens": 32765,
      "r2_program_trials": 1,
      "r2_reserved_tokens": 0,
      "r2_search_registry_slots": 3,
      "r2_unknown_usage_calls": 0
    },
    "causal_R1_R2_comparison_admitted": false,
    "common_budget_limits": {
      "confirmation_seconds": 120,
      "confirmation_slots": 3,
      "generation_seconds": 600,
      "infrastructure_retries": 0,
      "max_depth": 6,
      "max_workers": 1,
      "mission_tokens": 589824,
      "search_slots": 11,
      "tokens": 1500000,
      "wall_seconds": 1800
    },
    "compiler_sha256": "f7e1e7952e6aa5f31a79366a8dcdd751a150ed65e949429d527e933b5e7cc028",
    "compiler_sha256_equal": true,
    "compute_node_equal": false,
    "controller_implementation_equal": false,
    "effort": "max",
    "equivalent_realized_search_effort": false,
    "model": "gpt-6-luna",
    "protocol_id_equal": false,
    "r1_actual_historical_source_archive_sha256": "cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18",
    "r1_candidate_evaluation_sha256": "070bbb838f8e8856aad73fc05da0e714adba0753eb8e91f2de8d5c5d5de9d97b",
    "r1_compute_node": "romeo-a041",
    "r1_epoch": 1,
    "r1_job_id": "748259",
    "r1_protocol_id": "da707adbad2797c21ce92f72e8b7b33630878a814445125709251a1b4d366be5",
    "r2_added_generation_admission": {
      "minimum_episode_seconds": 600.0,
      "schema": "hpc-forest-full-generation-window-v1"
    },
    "r2_candidate_evaluation_sha256": "3f77e82d4e6bb349c0b94f22016c6536b0e15c055021719d5c1a7960abeb727c",
    "r2_compute_node": "romeo-a057",
    "r2_confirmation_stream_review": {
      "command_streams_rechecked": 16,
      "confirmation_sample_processes_rechecked": 10,
      "independent_performance_audit_verified": false,
      "individual_case_provenance_verified": false,
      "received_stream_consistency_verified": true,
      "scientifically_admitted_gain": false
    },
    "r2_epoch": 1,
    "r2_job_id": "755562",
    "r2_protocol_id": "afc54473852a57f801fb42d776195f1ccbcce7949ed8cda85a76d685ae115392",
    "r2_source_archive_sha256": "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4",
    "same_allocation_or_time": false,
    "same_common_budget_limits": true,
    "same_declared_checker_contract": true,
    "same_declared_harness": true,
    "same_declared_protocol_commands_and_settings": true,
    "same_model_effort_seed": true,
    "seed": 23,
    "subject_id": "2020-quicksort",
    "timeline": {
      "audit_pause_consumed_existing_wallclock": true,
      "bootstrap_elapsed_seconds": 2196.5520235011354,
      "budget_or_chronology_reset": false,
      "budget_stop_event_created_at_utc": "2026-10-19T11:10:38.447683+00:00",
      "confirmation_seconds_reserved": 120,
      "existing_campaign_deadline_utc": "2026-10-19T11:15:04.369661+00:00",
      "existing_search_deadline_utc": "2026-10-19T11:13:04.369661+00:00",
      "initial_candidate_evaluation_created_at_utc": "2026-10-19T10:49:23.697778+00:00",
      "initial_candidate_to_budget_stop_seconds": 1274.7499046325684,
      "pause_interval_measurement_scope": "archive_file_mtimes_not_CPU_or_exact_operator_wait_measurement",
      "paused_snapshot_archive_mtime_utc": "2026-10-19T10:49:24.356543+00:00",
      "paused_to_release_file_mtime_interval_seconds": 1274.074801683426,
      "release_receipt_archive_mtime_utc": "2026-10-19T11:10:38.431345+00:00",
      "scientific_pipeline_elapsed_seconds": 1597.6080821463838,
      "scientific_started_at_utc": "2026-10-19T10:45:04.369661+00:00",
      "scientific_wall_seconds_declared": 1800,
      "source_budget_stop_reason": "No remaining search admission",
      "source_search_status": "budget_exhausted"
    }
  },
  "provenance": {
    "historical_r1_scientific_cutoff_utc": "2026-10-18T05:03:23.898140+00:00",
    "new_model_calls": 0,
    "r2_first_batch_cutoff_utc": "2026-10-19T11:11:41.348000+00:00",
    "received_archive_files": 300,
    "received_code_executed": false,
    "sources": [
      {
        "bytes": 11711,
        "id": "r1-matrix-public-r4",
        "sha256": "41ec87a5a4ed24be36a9dc1cc17dc97df8271a4ce8cd2e6200c1c3ba334597ea"
      },
      {
        "bytes": 50840,
        "id": "r1-received-confirmation-ledger",
        "sha256": "3ffd48a4bac1c259533f85f686d35aa6c5946823d39d62d7289af260914645f9"
      },
      {
        "bytes": 17633,
        "id": "r1-exact-job748259-summary",
        "sha256": "f6a730013bbc090b32914169bc16707e7cc9cde73ffcc2310870f948fb5f3a24"
      },
      {
        "bytes": 2052,
        "id": "r1-exact-job748259-config",
        "sha256": "4e2220d5b0eec02ba63d3a3bafa1087d80508c8aa663848222f63b2e3b43fe6c"
      },
      {
        "bytes": 99362,
        "id": "r1-exact-job748259-report",
        "sha256": "43729d20fb03ebe8dec19b0cab9354f099d2b557b6f8fcebe21d1bf3b056a260"
      },
      {
        "bytes": 6898,
        "id": "r2-first-batch-public",
        "sha256": "ca4d2a1dd45971d3c5de3890dfe546375e741d770e12aebec9eb4cb36c195aa0"
      },
      {
        "bytes": 98137,
        "id": "r2-private-first-batch-review",
        "sha256": "ddca5eeefbf9bb4133305e2313201419456bba32d166502e75fb921f897250fb"
      },
      {
        "bytes": 2376,
        "id": "r2-root-first-batch-review",
        "sha256": "20c92abe5cfb61bff5178492f9b5f4a79ddf7dd8d8c5a4634650827f092097c8"
      },
      {
        "bytes": 6810,
        "id": "r2-root-terminal-bookkeeping-review",
        "sha256": "3baec9a868faf229e07636c5055ebf09d32b5bc0b259f2dfc4cbed08bc1edf34"
      },
      {
        "bytes": 10800,
        "id": "r2-source-final-confirmations",
        "sha256": "612cd03ae0d9fb223c167115f40d4876885b9f851375fa1a2e912786d53e95d8"
      },
      {
        "bytes": 198096,
        "id": "r2-received-original-result-archive",
        "sha256": "c046f75af8b2d221c963b0933b70c1effa1a745c15239a99083fd6a77c87736c"
      },
      {
        "bytes": 1381,
        "id": "r2-technical-bootstrap-before-model",
        "sha256": "5b91e8bbd04ddb011af9891e74f001b2f46ea92b5a456e0e34fcc75c9560ac85"
      },
      {
        "bytes": 33711,
        "id": "r2-report-member-of-received-archive",
        "sha256": "c65136096d5c1450b694a7a13ab7c187e67d8706300b00217717119a4cc21730"
      },
      {
        "bytes": 4455,
        "id": "matched-unchanged-checker-contract",
        "sha256": "c2fa077535e04b8d3f65ca4e4705ba178b55de6513aa4d1f071374bf9a776a16"
      },
      {
        "bytes": 654,
        "id": "r1-reference-sample-0-process",
        "sha256": "cce8c353f1a1b668b76855e8fd08204d22c0116993d623f4ce439bc8582d49c5"
      },
      {
        "bytes": 654,
        "id": "r1-reference-sample-1-process",
        "sha256": "9ae0189a59b190229501faab95b77da412f0ed9cd2dafc428232a6adb2b8a74a"
      },
      {
        "bytes": 653,
        "id": "r1-reference-sample-2-process",
        "sha256": "3b07f8dac0690450510806d2582eb555869d603ecabd2505e53919ed28f3d6e5"
      },
      {
        "bytes": 653,
        "id": "r1-reference-sample-3-process",
        "sha256": "b5aedc624f230ba7a35338eb7f3cf01d6c42e3ee7ce506190a96bab51823af23"
      },
      {
        "bytes": 654,
        "id": "r1-reference-sample-4-process",
        "sha256": "b5bf897abb5578b84576bca8cdfeffb7733af56ee869a769a719a303339addb2"
      },
      {
        "bytes": 665,
        "id": "r1-candidate-sample-0-process",
        "sha256": "19f1076401d593e32558f2a2770377c5fd8dcbf74734ab77caed1992c4d9d2b5"
      },
      {
        "bytes": 665,
        "id": "r1-candidate-sample-1-process",
        "sha256": "94733e94db19c1138690d334ca3590f63a72d352c1c4c5a390198d67373d25a9"
      },
      {
        "bytes": 665,
        "id": "r1-candidate-sample-2-process",
        "sha256": "2b2196974b54bf0ce6bfe1622c6b97537a4bb3fcbe380c6b3aa38277a9765208"
      },
      {
        "bytes": 665,
        "id": "r1-candidate-sample-3-process",
        "sha256": "6bf3f2563269bd29d19c85e91c8c2a94456bc1cbfc036249dea3b5c6772648e6"
      },
      {
        "bytes": 664,
        "id": "r1-candidate-sample-4-process",
        "sha256": "da662e66498856d9f518e12d2cbe5933ffa1e51ac73db009587762dbc61e4a10"
      }
    ]
  },
  "schema": "hpc-forest-article-r1-r2-numeric-comparison-v1",
  "source_cutoff_utc": "2026-10-19T11:40:35.931000+00:00"
}''')


def need(condition, message):
    if not condition:
        raise EvidenceError(message)


def closed(value, fields, location):
    need(type(value) is dict and set(value) == set(fields), f"Closed article comparison fields required: {location}")


def fixed(value, expected, location):
    need(type(value) is type(expected), f"Article comparison type differs: {location}")
    if isinstance(expected, dict):
        closed(value, expected, location)
        for key, item in expected.items():
            fixed(value[key], item, f"{location}.{key}")
    elif isinstance(expected, list):
        need(len(value) == len(expected), f"Article comparison list differs: {location}")
        for index, item in enumerate(expected):
            fixed(value[index], item, f"{location}[{index}]")
    else:
        need(value == expected, f"Article comparison snapshot differs: {location}")


def number(value, *, positive=False):
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def near(value, expected, location):
    need(number(value) and number(expected) and math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-15),
         f"Article comparison arithmetic differs: {location}")


def identity(value):
    fixed({key: value[key] for key in ("subject_id", "model", "effort", "seed")},
          {"subject_id": "2020-quicksort", "model": "gpt-6-luna", "effort": "max", "seed": 23}, "matched identity")


def validate(value):
    """Return a numeric summary; source-only confirmation always stays bounded."""
    closed(value, {*FIXED, "cells", "series"}, "root")
    for key, expected in FIXED.items():
        fixed(value[key], expected, key)
    cells = value["cells"]
    need(type(cells) is list and len(cells) == 60, "Sixty article comparison cells required")
    identities = set()
    measured = None
    zero_gains = 0
    for cell in cells:
        closed(cell, MATRIX_COLUMNS, "cell")
        subject, model = cell["subject_id"], cell["model"]
        need(type(subject) is str and subject in SUBJECTS and type(model) is str and model in MODELS,
             "Unknown article matrix identity")
        key = subject, model
        need(key not in identities, "Duplicate article matrix identity")
        identities.add(key)
        fixed(cell["effort"], "max", "cell.effort")
        fixed(cell["seed"], 23, "cell.seed")
        fixed(cell["r1_confirmed"], True, "cell.r1_confirmed")
        for field in ("r1_reference_seconds", "r1_candidate_seconds", "r1_speedup"):
            need(number(cell[field], positive=True), f"Positive finite article matrix value required: {field}")
        for field in ("r1_reference_sample_sd_seconds", "r1_candidate_sample_sd_seconds", "r1_gain_fraction"):
            need(number(cell[field]), f"Nonnegative finite article matrix value required: {field}")
        need(cell["r1_speedup"] >= 1 and cell["r1_gain_fraction"] < 1, "Invalid historical retained-program ratio")
        for field in ("r1_known_exact_tokens", "r1_native_calls", "r1_archived_unmetered_native_invocations",
                      "r1_received_reconciled_unmetered_calls"):
            need(type(cell[field]) is int and cell[field] >= 0, f"Integer historical accounting required: {field}")
        near(cell["r1_speedup"], cell["r1_reference_seconds"] / cell["r1_candidate_seconds"], "R1 speedup")
        near(cell["r1_gain_fraction"], 1 - cell["r1_candidate_seconds"] / cell["r1_reference_seconds"], "R1 gain")
        fixed(cell["r1_baseline_retained"], cell["r1_gain_fraction"] == 0, "cell.r1_baseline_retained")
        if cell["r1_baseline_retained"]:
            zero_gains += 1
            fixed(cell["r1_speedup"], 1.0, "R1 retained baseline speedup")
            near(cell["r1_candidate_seconds"], cell["r1_reference_seconds"], "R1 retained baseline time")
        for field in ("r2_scientifically_admitted_gain", "scientifically_admitted_pair"):
            fixed(cell[field], False, field)
        is_measured = key == ("2020-quicksort", "gpt-6-luna")
        fixed(cell["r2_initial_batch_received"], is_measured, "cell.initial_batch_received")
        fixed(cell["r2_source_confirmation_received"], is_measured, "cell.source_confirmation_received")
        if is_measured:
            measured = cell
            fixed(cell["r2_status"], "source_confirmed_single_cell_not_independent_performance_audit", "R2 measured status")
            for field in R2_NUMERIC:
                need(number(cell[field], positive=True), f"R2 measured numeric observation required: {field}")
            fixed(cell["r2_known_exact_tokens"], 32765, "R2 exact tokens")
            fixed(cell["r2_exact_calls"], 2, "R2 exact calls")
            near(cell["r2_initial_descriptive_speedup"], cell["r2_initial_reference_seconds"] / cell["r2_initial_candidate_seconds"], "R2 initial ratio")
            near(cell["r2_source_final_descriptive_speedup"], cell["r2_source_final_reference_seconds"] / cell["r2_source_final_candidate_seconds"], "R2 source final ratio")
        else:
            need(all(cell[field] is None for field in R2_NUMERIC), "Unmeasured R2 values must remain NA, never zero")
            status = "technical_failure_before_model_no_scientific_measurement" if key == ("2023-count", "gpt-6.1-sol") else "not_measured"
            fixed(cell["r2_status"], status, "R2 unmeasured status")
    need(identities == {(subject, model) for subject in SUBJECTS for model in MODELS}
         and zero_gains == 11 and measured is not None, "Article matrix coverage differs")

    groups = value["series"]
    need(type(groups) is list and len(groups) == 6, "Six separate timing series required")
    by_id = {}
    for group in groups:
        closed(group, SERIES_FIELDS, "series")
        identifier = group["id"]
        need(type(identifier) is str and identifier in SERIES_IDENTITIES and identifier not in by_id, "Unknown/duplicate timing series")
        by_id[identifier] = group
        identity(group)
        edition, phase, role, count, level = SERIES_IDENTITIES[identifier]
        for field, expected in (("edition", edition), ("phase", phase), ("role", role), ("n", count), ("evidence_level", level),
                                ("independent_performance_audit_verified", False)):
            fixed(group[field], expected, f"{identifier}.{field}")
        samples = group["samples_seconds"]
        need(type(samples) is list and len(samples) == count and all(number(item, positive=True) and item < 3600 for item in samples),
             "Positive finite original timing samples required")
        need(number(group["reference_mean_seconds"], positive=True), "Within-run reference mean required")
        try:
            mean, deviation = statistics.mean(samples), statistics.stdev(samples)
            normalized = [item / group["reference_mean_seconds"] for item in samples]
        except (ArithmeticError, ValueError) as error:
            raise EvidenceError("Invalid article timing arithmetic") from error
        near(group["mean_seconds"], mean, f"{identifier}.mean")
        near(group["sample_sd_seconds"], deviation, f"{identifier}.sample_sd")
        near(group["normalized_mean"], mean / group["reference_mean_seconds"], f"{identifier}.normalized_mean")
        need(type(group["normalized_samples"]) is list and len(group["normalized_samples"]) == count, "Complete normalized samples required")
        for actual, expected in zip(group["normalized_samples"], normalized, strict=True):
            near(actual, expected, f"{identifier}.normalized_sample")
    for prefix in ("r1", "r2_search", "r2_confirmation"):
        reference, candidate = by_id[prefix + "_reference"], by_id[prefix + "_candidate"]
        near(reference["reference_mean_seconds"], reference["mean_seconds"], prefix + ".own_reference")
        near(candidate["reference_mean_seconds"], reference["mean_seconds"], prefix + ".candidate_reference")
    fields = (
        ("r1_reference_seconds", "r1_reference", "mean_seconds"),
        ("r1_candidate_seconds", "r1_candidate", "mean_seconds"),
        ("r1_reference_sample_sd_seconds", "r1_reference", "sample_sd_seconds"),
        ("r1_candidate_sample_sd_seconds", "r1_candidate", "sample_sd_seconds"),
        ("r2_initial_reference_seconds", "r2_search_reference", "mean_seconds"),
        ("r2_initial_candidate_seconds", "r2_search_candidate", "mean_seconds"),
        ("r2_source_final_reference_seconds", "r2_confirmation_reference", "mean_seconds"),
        ("r2_source_final_candidate_seconds", "r2_confirmation_candidate", "mean_seconds"),
    )
    for field, identifier, statistic in fields:
        near(measured[field], by_id[identifier][statistic], "matrix/series linkage: " + field)
    fixed(measured["r1_known_exact_tokens"], value["matched_cell"]["accounting"]["r1_known_exact_tokens"], "R1 matched tokens")
    fixed(measured["r1_native_calls"], 10, "R1 matched native calls")
    fixed(measured["r1_received_reconciled_unmetered_calls"], 0, "R1 matched received unmetered calls")
    return {
        "matrix_cells": 60, "r1_confirmed": 60, "r1_zero_gains": zero_gains,
        "r2_received_cells": 1, "r2_missing_cells": 59, "series": 6,
        "timing_samples": sum(group["n"] for group in groups),
        "scientifically_admitted_pairs": 0, "scientifically_admitted_R2_gains": 0,
        "causal_claim": False, "independent_performance_audit_verified": False,
        "r1_job_id": value["matched_cell"]["r1_job_id"], "r2_job_id": value["matched_cell"]["r2_job_id"],
        "r2_exact_calls": 2, "r2_exact_tokens": 32765, "r2_search_registry_slots": 3, "r2_final_registry_slots": 5,
        "r1_descriptive_speedup": measured["r1_speedup"],
        "r2_initial_descriptive_speedup": measured["r2_initial_descriptive_speedup"],
        "r2_source_final_descriptive_speedup": measured["r2_source_final_descriptive_speedup"],
        "source_cutoff_utc": value["source_cutoff_utc"],
    }


def csv_rows(text, columns):
    reader = csv.DictReader(StringIO(text, newline=""))
    need(reader.fieldnames == list(columns), "Exact article CSV columns required")
    rows = list(reader)
    need(all(set(row) == set(columns) and all(type(item) is str for item in row.values()) for row in rows),
         "Malformed article CSV row")
    return rows


def rendered(value):
    return "" if value is None else str(value).lower() if type(value) is bool else str(value)


def expected_timing_rows(value):
    rows = []
    for group in value["series"]:
        for index, seconds in enumerate(group["samples_seconds"]):
            rows.append({
                "series_id": group["id"], "edition": group["edition"], "phase": group["phase"], "role": group["role"],
                "subject_id": group["subject_id"], "model": group["model"], "effort": group["effort"], "seed": group["seed"],
                "sample_index": index, "seconds": seconds, "reference_mean_seconds": group["reference_mean_seconds"],
                "normalized_seconds": group["normalized_samples"][index], "evidence_level": group["evidence_level"],
                "independent_performance_audit_verified": False,
            })
    return rows


def verify(root: Path):
    """Verify the frozen files, manifest, CSV/JSON agreement and public source pins."""
    root = Path(root)
    folder = root / SUBDIR
    names = {*FILE_PINS, "FILES.sha256.json"}
    annexes = {"provenance.json", "rebuild-figures.py", "REPRODUCTION.md"}
    actual_names = {path.name for path in folder.iterdir()} if folder.is_dir() else set()
    need(folder.is_dir() and not folder.is_symlink() and names <= actual_names <= names | annexes,
         "Exact public article data inventory required")
    need(all(path.is_file() and not path.is_symlink() for path in folder.iterdir()), "Ordinary public data annex required")
    contents = {}
    for name in names:
        path = folder / name
        need(path.is_file() and not path.is_symlink(), "Ordinary public article data file required")
        contents[name] = path.read_bytes()
    manifest = load_json(contents["FILES.sha256.json"].decode("utf8"))
    fixed(manifest, FILE_PINS, "data manifest")
    need(hashlib.sha256(contents["FILES.sha256.json"]).hexdigest() == MANIFEST_SHA256, "Article data manifest hash differs")
    for name, pin in FILE_PINS.items():
        need(len(contents[name]) == pin["bytes"] and hashlib.sha256(contents[name]).hexdigest() == pin["sha256"],
             "Frozen article data file hash differs: " + name)
    value = load_json(contents["comparison.json"].decode("utf8"))
    summary = validate(value)
    matrix_rows = csv_rows(contents["matrix15-comparison.csv"].decode("utf8"), MATRIX_COLUMNS)
    expected = [{key: rendered(row[key]) for key in MATRIX_COLUMNS} for row in value["cells"]]
    need(matrix_rows == expected, "Article matrix CSV/JSON disagree")
    timing_rows = csv_rows(contents["timing-samples.csv"].decode("utf8"), TIMING_COLUMNS)
    expected = [{key: rendered(row[key]) for key in TIMING_COLUMNS} for row in expected_timing_rows(value)]
    need(timing_rows == expected, "Article timing CSV/JSON disagree")
    public_sources = {
        "r1-matrix-public-r4": "evidence/received-2026-10-19-r4/matrix15.csv",
        "r1-received-confirmation-ledger": "evidence/received-2026-10-19/confirmations.csv",
        "r2-first-batch-public": "evidence/native-first-batch-2026-10-19/first-batch.json",
    }
    source_pins = {item["id"]: item for item in value["provenance"]["sources"]}
    for identifier, relative in public_sources.items():
        raw = (root / relative).read_bytes()
        need(len(raw) == source_pins[identifier]["bytes"] and hashlib.sha256(raw).hexdigest() == source_pins[identifier]["sha256"],
             "Article public source provenance differs: " + identifier)
    return summary
