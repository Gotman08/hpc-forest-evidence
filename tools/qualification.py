"""Recalculate the public zero-model baseline projection; never execute received code."""
from __future__ import annotations

import math
import re
import statistics
from pathlib import Path

from .recompute import EvidenceError, load_json

SUBJECTS = (
    "2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
    "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
    "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci",
)
SHA_FIELDS = {"private_archive_sha256", "private_cold_audit_sha256", "cold_reader_sha256",
              "source_archive_sha256", "source_plan_sha256"}
FIELDS = {"schema", "scope", "qualification_job_id", "qualification_started_utc", "scheduler_state",
          "scheduler_exit_code", "scheduler_elapsed_seconds", "allocation", "native_model_calls",
          "scientific_gain_claimed", "native_matrix_results_claimed", "subjects", *SHA_FIELDS}
ROW_FIELDS = {"subject_id", "confirmation_seconds", "mean_seconds", "sample_stdev_seconds",
              "binary_sha256", "r1_contract_sha256", "protocol_id", "private_reference_receipt_sha256"}


def need(condition, message):
    if not condition:
        raise EvidenceError(message)


def number(value):
    return type(value) in {int, float} and math.isfinite(value) and value > 0


def validate(value):
    need(type(value) is dict and set(value) == FIELDS, "Closed public Q15 fields required")
    need(value["schema"] == "hpc-forest-public-baseline-qualification-v1"
         and value["scope"] == "baseline_qualification_only"
         and value["qualification_job_id"] == "755488"
         and value["qualification_started_utc"] == "2026-10-19T09:22:23.063063+00:00"
         and value["scheduler_state"] == "COMPLETED" and value["scheduler_exit_code"] == "0:0"
         and type(value["scheduler_elapsed_seconds"]) is int and value["scheduler_elapsed_seconds"] == 65,
         "Actual completed Q15 observation required")
    need(value["allocation"] == {"architecture": "aarch64", "nodes": 1, "tasks": 1,
                                "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0}
         and all(type(v) is int for k, v in value["allocation"].items() if k != "architecture"),
         "Q15 allocation differs")
    need(type(value["native_model_calls"]) is int and value["native_model_calls"] == 0
         and value["scientific_gain_claimed"] is False and value["native_matrix_results_claimed"] is False,
         "Baseline qualification cannot become a model result or a speedup")
    need(all(isinstance(value[key], str) and re.fullmatch("[0-9a-f]{64}", value[key]) for key in SHA_FIELDS),
         "Q15 provenance digests missing")
    rows = value["subjects"]
    need(type(rows) is list and len(rows) == len(SUBJECTS), "All fifteen Q15 subjects required")
    for expected, row in zip(SUBJECTS, rows):
        need(type(row) is dict and set(row) == ROW_FIELDS and row["subject_id"] == expected,
             "Ordered closed Q15 subject fields required")
        need(all(isinstance(row[key], str) and re.fullmatch("[0-9a-f]{64}", row[key])
                 for key in ROW_FIELDS - {"subject_id", "confirmation_seconds", "mean_seconds", "sample_stdev_seconds"}),
             "Q15 subject digests missing")
        times = row["confirmation_seconds"]
        need(type(times) is list and len(times) == 5 and all(number(t) for t in times),
             "Five positive finite Q15 timings required")
        for key, expected_value in (("mean_seconds", statistics.mean(times)),
                                    ("sample_stdev_seconds", statistics.stdev(times))):
            need(type(row[key]) in {int, float} and math.isfinite(row[key])
                 and math.isclose(row[key], expected_value, rel_tol=1e-12, abs_tol=1e-15),
                 "Q15 timing arithmetic differs")
    return {"subjects": len(rows), "samples": sum(len(row["confirmation_seconds"]) for row in rows)}


def verify(root: Path):
    return validate(load_json((root / "evidence/qualification-2026-10-19/baselines.json").read_text(encoding="utf-8")))
