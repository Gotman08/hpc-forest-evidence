"""Offline numeric projection of received R1/R2 evidence; never execute received code."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

BASE = Path(__file__).resolve().parents[2]
PUBLIC_REPO = BASE / "work/hpc-forest-evidence"
EXECUTION = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01"
R1 = Path("C:/Users/nicol/Documents/Codex/2026-10-15/cr/outputs/HPC-Forest-Etude-2020-2024-r1/runs/coverage-gpt-6-luna-max/preuves/results-748259")
OUTPUT = BASE / "outputs/HPC-Forest-Article-R1-R2-Donnees-r1/public"
HASH = re.compile(r"[a-f0-9]{64}")


def need(test, message):
    if not test:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def source(identifier, path):
    raw = Path(path).read_bytes()
    return {"id": identifier, "sha256": sha(raw), "bytes": len(raw)}


def finite_positive(value):
    return type(value) in {int, float} and math.isfinite(value) and value > 0


def utc(value):
    return datetime.fromtimestamp(value, UTC).isoformat()


def checked_archive(path, digest):
    raw = Path(path).read_bytes()
    need(sha(raw) == digest, "Received R2 archive hash differs")
    files, mtimes, kinds = {}, {}, {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as stream:
        members = stream.getmembers()
        need(len(members) < 100000, "Archive member bound exceeded")
        total = 0
        for member in members:
            name = PurePosixPath(member.name)
            need(not name.is_absolute() and name.as_posix() == member.name and "\\" not in member.name
                 and ":" not in member.name and all(member.name.split("/"))
                 and all(part not in {".", ".."} for part in name.parts)
                 and name.parts[0] == "results-755562" and member.name not in kinds, "Unsafe or duplicate archive member")
            need(member.isfile() or member.isdir(), "Archive links and special files refused")
            kinds[member.name] = "directory" if member.isdir() else "file"
            if member.isdir():
                continue
            total += member.size
            need(member.size <= 512 * 1024 * 1024 and total < 4 * 1024 * 1024 * 1024, "Archive expansion bound exceeded")
            value = stream.extractfile(member).read(member.size + 1)
            need(len(value) == member.size, "Truncated archive member")
            files[member.name], mtimes[member.name] = value, member.mtime
        for name in kinds:
            need(all(kinds.get(parent.as_posix(), "directory") == "directory" for parent in PurePosixPath(name).parents),
                 "Archive file/directory collision")
    return files, mtimes


def series(identifier, edition, phase, role, samples, reference, evidence_level):
    need(samples and all(finite_positive(item) for item in samples) and finite_positive(reference), "Invalid numeric timing samples")
    return {"id": identifier, "edition": edition, "phase": phase, "role": role, "subject_id": "2020-quicksort",
            "model": "gpt-6-luna", "effort": "max", "seed": 23, "samples_seconds": samples,
            "n": len(samples), "mean_seconds": statistics.mean(samples), "sample_sd_seconds": statistics.stdev(samples),
            "reference_mean_seconds": reference, "normalized_samples": [value / reference for value in samples],
            "normalized_mean": statistics.mean(samples) / reference, "evidence_level": evidence_level,
            "independent_performance_audit_verified": False}


def verify_confirmation_streams(files, report, confirmation, binding, external):
    """Recheck received generic streams. Do not claim case-v2 or independent performance."""
    root = binding["remote_root"]

    def resolve(ref):
        need(type(ref) is dict and isinstance(ref.get("path"), str) and HASH.fullmatch(ref.get("sha256", "")), "Bad original artifact ref")
        path = ref["path"]
        if path.startswith(root + "/"):
            data = files.get(path[len(root) + 1:])
        else:
            data = external.get(path)
        need(data is not None and sha(data) == ref["sha256"] and ("bytes" not in ref or len(data) == ref["bytes"]),
             "Missing or changed confirmation stream artifact")
        return data

    evaluations = [value for value in report["evaluations"] if value["phase"] == "confirmation"]
    need(len(evaluations) == 2, "Expected exact reference and selected confirmation outcomes")
    records_checked = 0
    samples = {}
    for evaluation in evaluations:
        experiment, outcome = evaluation["experiment_id"], evaluation["outcome"]
        need(outcome.get("correct") is True and outcome.get("status") == "valid"
             and len(outcome["times"]) == 5 and sha(canonical(outcome)) == confirmation["evaluation_digests"][experiment],
             "Final outcome differs from received source digest")
        records = confirmation["command_stream_provenance"][experiment]
        need(len(records) == 8 and len(outcome["logs"]) == 8, "Expected build/check/warmup/five benchmark records")
        measured = []
        for record, log in zip(records, outcome["logs"], strict=True):
            proof = json.loads(resolve(record))
            context = json.loads(resolve(proof["context"]))
            process = json.loads(resolve(proof["original_process_result"]))
            need(record["path"] == log + ".command-stream.json" and proof["phase"] == "confirmation"
                 and proof["experiment_id"] == experiment and proof["protocol_id"] == report["protocol_id"]
                 and proof["operator_binding"]["cell_binding"] == binding and proof["verified"] is True
                 and proof["commit"] == outcome["commit"] and proof["tree_hash"] == outcome["tree_hash"]
                 and proof["source_before"] == proof["source_after"] == {"commit": outcome["commit"], "tree_hash": outcome["tree_hash"], "clean": True}
                 and proof["mode"] == "command-stream-v1" and proof["execution_semantics_changed"] is False,
                 "Confirmation command identity differs")
            need(all(proof.get(key) is False for key in ("individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified"))
                 and proof["case_execution_records"] == [], "Generic streams must retain limited evidence scope")
            need(all(context.get(key) == value for key, value in proof.items() if key in context and key != "schema")
                 and process == {"argv": context["argv"], "returncode": proof["returncode"], "seconds": proof["measured_seconds"],
                                 "timed_out": proof["timed_out"], "log": log}
                 and process["returncode"] == 0 and process["timed_out"] is False, "Original process receipt differs")
            resolve(proof["streams"]["combined_stdout_stderr"])
            for ref in [*context["argument_files_before"], *proof["argument_files_after"]]:
                resolve(ref)
            for key in ("binary_before", "binary_after"):
                if proof.get(key) is not None:
                    resolve(proof[key])
            if proof["operation"] != "build":
                need(proof["binary_before"] == proof["binary_after"], "Confirmation binary changed")
            if re.search(r"/sample-[0-4]\.log$", log):
                need(proof["operation"] == "benchmark", "Sample is not a benchmark operation")
                measured.append(proof["measured_seconds"])
            records_checked += 1
        need(measured == outcome["times"] and math.isclose(statistics.mean(measured), outcome["mean_seconds"], rel_tol=1e-14),
             "Five source timings differ from received original process measurements")
        samples[experiment] = measured
    return samples, {"command_streams_rechecked": records_checked, "confirmation_sample_processes_rechecked": 10,
                     "received_stream_consistency_verified": True, "individual_case_provenance_verified": False,
                     "independent_performance_audit_verified": False, "scientifically_admitted_gain": False}


def build(compiled_at):
    matrix_path = PUBLIC_REPO / "evidence/received-2026-10-19-r4/matrix15.csv"
    ledger_path = PUBLIC_REPO / "evidence/received-2026-10-19/confirmations.csv"
    with matrix_path.open(newline="", encoding="utf8") as stream:
        rows = list(csv.DictReader(stream))
    with ledger_path.open(newline="", encoding="utf8") as stream:
        ledger = list(csv.DictReader(stream))
    need(len(rows) == 60 and len({(r["subject_id"], r["model"]) for r in rows}) == 60, "R1 matrix coverage differs")
    cells = []
    for row in rows:
        matching = [item for item in ledger if item["subject"] == row["subject_id"] and item["model"] == row["model"]
                    and item["effort"] == row["effort"] and float(item["reference_seconds"]) == float(row["r1_reference_seconds"])
                    and float(item["chosen_seconds"]) == float(row["r1_candidate_seconds"]) and int(item["known_exact_tokens"]) == int(row["r1_known_exact_tokens"])]
        need(len(matching) == 1, "R1 matrix row must match exactly one received historical cohort")
        old = matching[0]
        need(int(old["unmetered_calls"]) == int(row["r1_received_reconciled_unmetered_calls"]), "Received R1 cost scope differs")
        cell = {"subject_id": row["subject_id"], "model": row["model"], "effort": row["effort"], "seed": int(row["seed"]),
                "r1_confirmed": row["r1_status"] == "confirmed", "r1_reference_seconds": float(row["r1_reference_seconds"]),
                "r1_candidate_seconds": float(row["r1_candidate_seconds"]), "r1_gain_fraction": float(row["r1_gain_fraction"]),
                "r1_speedup": float(row["r1_speedup"]), "r1_known_exact_tokens": int(row["r1_known_exact_tokens"]),
                "r1_archived_unmetered_native_invocations": int(row["r1_archived_unmetered_native_invocations"]),
                "r1_received_reconciled_unmetered_calls": int(row["r1_received_reconciled_unmetered_calls"]),
                "r1_native_calls": int(old["native_calls"]), "r1_reference_sample_sd_seconds": float(old["reference_sd"]),
                "r1_candidate_sample_sd_seconds": float(old["chosen_sd"]), "r1_baseline_retained": old["baseline_retained"].lower() == "true",
                "r2_status": "not_measured", "r2_initial_batch_received": False, "r2_source_confirmation_received": False,
                "r2_scientifically_admitted_gain": False, "r2_initial_reference_seconds": None, "r2_initial_candidate_seconds": None,
                "r2_initial_descriptive_speedup": None, "r2_source_final_reference_seconds": None, "r2_source_final_candidate_seconds": None,
                "r2_source_final_descriptive_speedup": None, "r2_known_exact_tokens": None, "r2_exact_calls": None,
                "scientifically_admitted_pair": False}
        need(math.isclose(cell["r1_speedup"], cell["r1_reference_seconds"] / cell["r1_candidate_seconds"], rel_tol=1e-13), "R1 ratio differs")
        if cell["r1_gain_fraction"] == 0:
            need(cell["r1_baseline_retained"] and cell["r1_speedup"] == 1 and cell["r1_candidate_seconds"] == cell["r1_reference_seconds"],
                 "Measured R1 baseline retention must remain speedup one")
        cells.append(cell)
    public_first_path = PUBLIC_REPO / "evidence/native-first-batch-2026-10-19/first-batch.json"
    first = read(public_first_path)
    terminal_path = EXECUTION / "terminal-audit-r1.json"
    terminal, final_results = read(terminal_path), read(EXECUTION / "terminal-received-r1/results.json")
    confirmation_path = EXECUTION / "terminal-received-r2/confirmations.json"
    confirmation = read(confirmation_path)
    need(terminal["verified"] is True and terminal["verified_scope"] == "terminal-bookkeeping-and-unchanged-audited-call-set-only"
         and terminal["independent_performance_audit_verified"] is False, "ROOT terminal bookkeeping proof missing")
    archive_path = EXECUTION / "terminal-received-r2/archive-data.tar.gz"
    archive_ref = read(EXECUTION / "terminal-received-r2/archive.json")
    files, mtimes = checked_archive(archive_path, archive_ref["sha256"])
    report_bytes = files["results-755562/2020-quicksort/report/experiments.json"]
    report = json.loads(report_bytes)
    need(files["results-755562/confirmations-finales-verifiees.json"] == confirmation_path.read_bytes(), "Archive confirmation differs from SCP artifact")
    binding = terminal["binding"]
    first_private = read(EXECUTION / "first-batch-audit-r2/AUDIT-PRIVE.json")
    python_path = report["identity"]["python_executable"]
    python_record = next(item for item in first_private["received_inventory"] if item.get("remote_ref", {}).get("path") == python_path)
    python_raw = Path(python_record["local_ref"]["path"]).read_bytes()
    need(sha(python_raw) == python_record["remote_ref"]["sha256"] == python_record["local_ref"]["sha256"], "Previously received Python program changed")
    samples, stream_review = verify_confirmation_streams(files, report, confirmation, binding,
        {"/bin/sh": (EXECUTION / "external-shell-received/program.bin").read_bytes(), python_path: python_raw})
    r1_summary_path = R1 / "2020-quicksort-summary.json"
    r1_config_path = R1 / "2020-quicksort/trusted/config.json"
    r1_report_path = R1 / "2020-quicksort/report/experiments.json"
    r1_summary, r1_config, r1_report = read(r1_summary_path), read(r1_config_path), read(r1_report_path)
    best1, best2 = r1_summary["best_confirmed"], final_results["best_confirmed"]
    selected = next(cell for cell in cells if cell["subject_id"] == "2020-quicksort" and cell["model"] == "gpt-6-luna")
    need(selected["r1_candidate_seconds"] == best1["mean_seconds"] and selected["r1_reference_seconds"] == best1["reference_seconds"]
         and selected["r1_known_exact_tokens"] == r1_summary["costs"]["exact_tokens_used"], "R1 source-only/historical cohort substitution refused")
    raw1 = {}
    raw1_refs = []
    for role, experiment in (("reference", "baseline-e1"), ("candidate", best1["experiment_id"])):
        times = []
        for index in range(5):
            path = R1 / f"2020-quicksort/logs/e1/{experiment}/confirmation/attempt-001/sample-{index}.log.json"
            process = read(path)
            need(process["returncode"] == 0 and process["timed_out"] is False and finite_positive(process["seconds"]), "R1 original timing process failed")
            times.append(process["seconds"])
            raw1_refs.append(source(f"r1-{role}-sample-{index}-process", path))
        expected = best1["reference_seconds"] if role == "reference" else best1["mean_seconds"]
        need(statistics.mean(times) == expected, "R1 samples do not reproduce exact CSV cohort")
        raw1[role] = times
    need(final_results["pipeline_complete"] is True and report["best_confirmed"] == best2
         and confirmation["best_confirmed"] == best2 and final_results["costs"]["exact_tokens_used"] == 32765
         and len(terminal["closed_calls"]) == 2, "R2 terminal identity/accounting differs")
    selected.update(r2_status="source_confirmed_single_cell_not_independent_performance_audit", r2_initial_batch_received=True,
        r2_source_confirmation_received=True, r2_initial_reference_seconds=first["contemporary_reference"]["mean_seconds"],
        r2_initial_candidate_seconds=first["initial_search"]["mean_seconds"],
        r2_initial_descriptive_speedup=first["comparison"]["initial_mean_ratio"],
        r2_source_final_reference_seconds=best2["reference_seconds"], r2_source_final_candidate_seconds=best2["mean_seconds"],
        r2_source_final_descriptive_speedup=best2["reference_seconds"] / best2["mean_seconds"], r2_known_exact_tokens=32765, r2_exact_calls=2)
    incident_root = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-02"
    incident_path = incident_root / "bootstrap-failed-755766.json"
    incident = read(incident_path)
    need(incident["binding"]["model"] == "gpt-6.1-sol" and incident["binding"]["subject_id"] == "2023-count"
         and incident["admission_accepted"] is False and incident["native_child_launch_attempted"] is False
         and incident["native_model_calls_before_authorization"] == 0, "Technical incident scientific boundary differs")
    next(cell for cell in cells if cell["subject_id"] == "2023-count" and cell["model"] == "gpt-6.1-sol")["r2_status"] = "technical_failure_before_model_no_scientific_measurement"
    groups = [series("r1_reference", "R1", "confirmation", "reference", raw1["reference"], best1["reference_seconds"], "received_historical_original_process_metadata"),
              series("r1_candidate", "R1", "confirmation", "candidate", raw1["candidate"], best1["reference_seconds"], "received_historical_original_process_metadata"),
              series("r2_search_reference", "R2", "initial_search", "reference", first["contemporary_reference"]["samples_seconds"], first["contemporary_reference"]["mean_seconds"], "first_batch_cold_generic_command_stream_audit"),
              series("r2_search_candidate", "R2", "initial_search", "candidate", first["initial_search"]["samples_seconds"], first["contemporary_reference"]["mean_seconds"], "first_batch_cold_generic_command_stream_audit"),
              series("r2_confirmation_reference", "R2", "confirmation", "reference", samples["baseline-e1"], best2["reference_seconds"], "source_confirmed_received_archive_generic_stream_consistency"),
              series("r2_confirmation_candidate", "R2", "confirmation", "candidate", samples[best2["experiment_id"]], best2["reference_seconds"], "source_confirmed_received_archive_generic_stream_consistency")]
    r2_config = report["config"]
    contract1 = (R1 / "2020-quicksort/trusted/contract.json").read_bytes()
    contract2 = files["results-755562/2020-quicksort/trusted/contract.json"]
    need(sha(contract1) == sha(contract2) == binding["r1_contract_sha256"], "Paired declared checker contract changed")
    budget1 = r1_config["budget"]
    budget2 = r2_config["budget"]
    common_budget = {key: budget1[key] for key in budget1}
    need(all(budget2.get(key) == value for key, value in common_budget.items()), "Declared shared budgets differ")
    need(r1_config["protocol"] == r2_config["protocol"] and r1_config["harness"] == r2_config["harness"], "Declared protocol/harness differs")
    pause = json.loads(files["results-755562/premier-batch-en-attente.json"])
    budget_events = [event for event in report["events"] if event["kind"] == "budget_stop"]
    stop = budget_events[-1]
    candidate_search = next(item for item in report["evaluations"] if item["phase"] == "search" and item["experiment_id"] == best2["experiment_id"])
    r2_started_at = pause["existing_campaign_deadline"] - budget2["wall_seconds"]
    timeline = {"source_search_status": final_results["search"]["status"], "source_budget_stop_reason": json.loads(stop["payload"])["reason"],
                "scientific_wall_seconds_declared": budget2["wall_seconds"], "confirmation_seconds_reserved": budget2["confirmation_seconds"],
                "scientific_started_at_utc": utc(r2_started_at), "initial_candidate_evaluation_created_at_utc": utc(candidate_search["created"]),
                "paused_snapshot_archive_mtime_utc": utc(mtimes["results-755562/premier-batch-en-attente.json"]),
                "release_receipt_archive_mtime_utc": utc(mtimes["results-755562/premier-batch-release-verifiee.json"]),
                "budget_stop_event_created_at_utc": utc(stop["created"]), "existing_search_deadline_utc": utc(pause["existing_search_deadline"]),
                "existing_campaign_deadline_utc": utc(pause["existing_campaign_deadline"]),
                "initial_candidate_to_budget_stop_seconds": stop["created"] - candidate_search["created"],
                "paused_to_release_file_mtime_interval_seconds": mtimes["results-755562/premier-batch-release-verifiee.json"] - mtimes["results-755562/premier-batch-en-attente.json"],
                "pause_interval_measurement_scope": "archive_file_mtimes_not_CPU_or_exact_operator_wait_measurement",
                "audit_pause_consumed_existing_wallclock": True, "budget_or_chronology_reset": pause["budget_or_chronology_reset"],
                "scientific_pipeline_elapsed_seconds": final_results["elapsed_seconds"], "bootstrap_elapsed_seconds": read(EXECUTION / "terminal-received-r1/bootstrap.json")["bootstrap_elapsed_seconds"]}
    sources = [source("r1-matrix-public-r4", matrix_path), source("r1-received-confirmation-ledger", ledger_path),
               source("r1-exact-job748259-summary", r1_summary_path), source("r1-exact-job748259-config", r1_config_path),
               source("r1-exact-job748259-report", r1_report_path), source("r2-first-batch-public", public_first_path),
               source("r2-private-first-batch-review", EXECUTION / "first-batch-audit-r2/AUDIT-PRIVE.json"),
               source("r2-root-first-batch-review", EXECUTION / "extension-gate-r1/ROOT-REVIEW-REEL.json"),
               source("r2-root-terminal-bookkeeping-review", terminal_path), source("r2-source-final-confirmations", confirmation_path),
               source("r2-received-original-result-archive", archive_path), source("r2-technical-bootstrap-before-model", incident_path),
               {"id": "r2-report-member-of-received-archive", "sha256": sha(report_bytes), "bytes": len(report_bytes)},
               {"id": "matched-unchanged-checker-contract", "sha256": sha(contract1), "bytes": len(contract1)}, *raw1_refs]
    observed_paths = [EXECUTION / "terminal-raw-r2/confirmations.json", EXECUTION / "terminal-raw-r2/archive-data.json",
                      incident_root / "BOOTSTRAP-FAILED-SCP-REEL-r1.json"]
    source_cutoff = utc(max(read(path)["observed_at"] for path in observed_paths))
    return {"schema": "hpc-forest-article-r1-r2-numeric-comparison-v1", "compiled_at_utc": compiled_at, "source_cutoff_utc": source_cutoff,
            "coverage": {"matrix_cells": 60, "subjects": 15, "models": 4, "r1_historical_confirmed_cells": 60,
                         "r1_measured_zero_gains_baseline_retained": 11, "r2_initial_batch_received_cells": 1,
                         "r2_source_confirmed_cells": 1, "r2_cells_without_scientific_measurement": 59,
                         "r2_scientifically_admitted_gain_cells": 0, "matched_subject_model_keys": 1,
                         "scientifically_admitted_pairs": 0, "r2_technical_incidents_before_model_cells": 1},
            "cells": cells, "series": groups,
            "matched_cell": {"subject_id": "2020-quicksort", "model": "gpt-6-luna", "effort": "max", "seed": 23,
                "r1_job_id": "748259", "r2_job_id": "755562", "r1_epoch": best1["epoch"], "r2_epoch": best2["epoch"],
                "r1_protocol_id": best1["protocol_id"], "r2_protocol_id": best2["protocol_id"],
                "r1_actual_historical_source_archive_sha256": "cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18",
                "r2_source_archive_sha256": binding["source_zip_sha256"],
                "r1_candidate_evaluation_sha256": best1["evaluation_digest"], "r2_candidate_evaluation_sha256": best2["evaluation_digest"],
                "same_declared_checker_contract": True, "same_declared_protocol_commands_and_settings": True,
                "same_declared_harness": True, "same_common_budget_limits": True, "common_budget_limits": common_budget,
                "r2_added_generation_admission": budget2.get("generation_admission"),
                "compiler_sha256_equal": r1_config["compiler"]["sha256"] == r2_config["compiler"]["sha256"],
                "compiler_sha256": r2_config["compiler"]["sha256"], "same_model_effort_seed": True,
                "r1_compute_node": r1_report["identity"]["hostname"], "r2_compute_node": report["identity"]["hostname"],
                "compute_node_equal": r1_report["identity"]["hostname"] == report["identity"]["hostname"],
                "controller_implementation_equal": r1_report["identity"]["controller_implementation"] == report["identity"]["controller_implementation"],
                "protocol_id_equal": best1["protocol_id"] == best2["protocol_id"], "same_allocation_or_time": False,
                "equivalent_realized_search_effort": False, "causal_R1_R2_comparison_admitted": False,
                "timeline": timeline, "r2_confirmation_stream_review": stream_review,
                "accounting": {"r1_known_exact_tokens": selected["r1_known_exact_tokens"], "r1_received_reconciled_unmetered_calls": selected["r1_received_reconciled_unmetered_calls"],
                               "r1_native_calls": selected["r1_native_calls"], "r1_program_trials": len(r1_report["experiments"]),
                               "r2_known_exact_tokens": 32765, "r2_delivered_exact_calls": 2, "r2_program_trials": len(report["experiments"]),
                               "r2_search_registry_slots": final_results["search"]["costs"]["slots"], "r2_final_registry_slots": final_results["costs"]["slots"],
                               "r2_unknown_usage_calls": 0, "r2_bounded_usage_calls": 0, "r2_reserved_tokens": 0}},
            "provenance": {"historical_r1_scientific_cutoff_utc": "2026-10-18T05:03:23.898140+00:00", "r2_first_batch_cutoff_utc": first["source_cutoff_utc"],
                           "sources": sources, "received_archive_files": len(files), "received_code_executed": False, "new_model_calls": 0},
            "boundaries": {"missing_numeric_csv_cells": "empty_fields_mean_not_measured_never_zero", "r1_zero_gain_semantics": "measured_baseline_retained_speedup_one",
                           "normalization": "each_phase_sample_divided_by_its_own_run_phase_reference_mean",
                           "error_bars": "sample_standard_deviation_descriptive_not_confidence_intervals",
                           "causal_claim": False, "inferential_significance_claim": False, "scientifically_admitted_R2_gain": False,
                           "source_confirmed_does_not_mean_independent_performance_audit": True,
                           "pipeline_complete_is_one_cell_not_full_matrix": True, "source_only_job749843_substituted_for_historical_R1": False,
                           "private_paths_prompts_code_cli_census_config_exported": False}}


def write_outputs(value, output):
    need(not output.exists(), "New output directory required")
    output.mkdir(parents=True)
    with (output / "comparison.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    with (output / "matrix15-comparison.csv").open("x", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(value["cells"][0]), lineterminator="\n")
        writer.writeheader()
        for row in value["cells"]:
            writer.writerow({key: str(item).lower() if type(item) is bool else item for key, item in row.items()})
    timing_rows = []
    for group in value["series"]:
        for index, seconds in enumerate(group["samples_seconds"]):
            timing_rows.append({"series_id": group["id"], "edition": group["edition"], "phase": group["phase"], "role": group["role"],
                "subject_id": group["subject_id"], "model": group["model"], "effort": group["effort"], "seed": group["seed"],
                "sample_index": index, "seconds": seconds, "reference_mean_seconds": group["reference_mean_seconds"],
                "normalized_seconds": group["normalized_samples"][index], "evidence_level": group["evidence_level"],
                "independent_performance_audit_verified": "false"})
    need(len(timing_rows) == 26, "Expected exact ten R1/six initial R2/ten final R2 samples")
    with (output / "timing-samples.csv").open("x", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(timing_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(timing_rows)
    for path in output.iterdir():
        raw = path.read_bytes()
        need(not any(token in raw for token in (b"C:\\", b"/gpfs/", b"/scratch_p/", b"argv\"", b"instructions.txt", b"config.toml")), "Private path/CLI leaked into numeric projection")
    manifest = {path.name: {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size} for path in sorted(output.iterdir())}
    with (output / "FILES.sha256.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {path.name: sha(path.read_bytes()) for path in sorted(output.iterdir())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiled-at-utc", required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(write_outputs(build(args.compiled_at_utc), args.output), sort_keys=True))


if __name__ == "__main__":
    main()
