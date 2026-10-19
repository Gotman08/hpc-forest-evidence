"""Keep the frozen R1/R2 article comparison numerically reproducible and bounded."""
import copy
import hashlib
import json
import statistics
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.article_r5 import (
    FILE_PINS,
    MATRIX_COLUMNS,
    SUBDIR,
    csv_rows,
    validate,
    verify,
)
from tools.recompute import EvidenceError, load_json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / SUBDIR


def objects(value, path=()):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from objects(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from objects(item, path + (index,))


def at(value, path):
    for part in path:
        value = value[part]
    return value


class ArticleR5Tests(unittest.TestCase):
    def setUp(self):
        self.value = load_json((DATA / "comparison.json").read_text(encoding="utf8"))

    def reject(self, path, replacement):
        value = copy.deepcopy(self.value)
        at(value, path[:-1])[path[-1]] = replacement
        with self.assertRaises(EvidenceError):
            validate(value)

    def test_recompute_and_verify_public_projection(self):
        summary = validate(self.value)
        self.assertEqual(verify(ROOT), summary)
        expected = {"matrix_cells": 60, "r1_confirmed": 60, "r1_zero_gains": 11,
                    "r2_received_cells": 1, "r2_missing_cells": 59, "series": 6, "timing_samples": 26,
                    "scientifically_admitted_pairs": 0, "scientifically_admitted_R2_gains": 0,
                    "r1_job_id": "748259", "r2_job_id": "755562", "r2_exact_calls": 2,
                    "r2_exact_tokens": 32765, "r2_search_registry_slots": 3, "r2_final_registry_slots": 5}
        for key, wanted in expected.items():
            self.assertEqual(summary[key], wanted, key)
        self.assertFalse(summary["independent_performance_audit_verified"])
        self.assertFalse(summary["causal_claim"])

    def test_every_public_object_has_closed_keys(self):
        for path, original in objects(self.value):
            with self.subTest(path=path, mutation="private addition"):
                value = copy.deepcopy(self.value)
                at(value, path)["private_unpublished_field"] = "not public evidence"
                with self.assertRaises(EvidenceError):
                    validate(value)
            with self.subTest(path=path, mutation="missing field"):
                value = copy.deepcopy(self.value)
                del at(value, path)[next(iter(original))]
                with self.assertRaises(EvidenceError):
                    validate(value)

    def test_missing_r2_observations_never_become_zero(self):
        for index, cell in enumerate(self.value["cells"]):
            if cell["r2_initial_batch_received"]:
                continue
            for field in ("r2_initial_reference_seconds", "r2_initial_candidate_seconds",
                          "r2_source_final_reference_seconds", "r2_source_final_candidate_seconds", "r2_known_exact_tokens"):
                with self.subTest(index=index, field=field):
                    self.reject(("cells", index, field), 0)

    def test_duplicate_matrix_identity_and_wrong_baseline_retention_rejected(self):
        self.reject(("cells", 1), copy.deepcopy(self.value["cells"][0]))
        for index, cell in enumerate(self.value["cells"]):
            if cell["r1_baseline_retained"]:
                self.reject(("cells", index, "r1_speedup"), 0.0)
                self.reject(("cells", index, "r1_baseline_retained"), False)
                break

    def test_stage_sizes_and_original_samples_required(self):
        for index, group in enumerate(self.value["series"]):
            self.reject(("series", index, "samples_seconds"), group["samples_seconds"][:-1])
            for bad in (0, -1, True, False, "0.1", float("nan"), float("inf"), 10**400):
                with self.subTest(series=index, bad_type=type(bad).__name__):
                    self.reject(("series", index, "samples_seconds", 0), bad)

    def test_statistics_normalization_and_matrix_linkage_recomputed(self):
        for index, group in enumerate(self.value["series"]):
            self.assertEqual(group["mean_seconds"], statistics.mean(group["samples_seconds"]))
            self.assertEqual(group["sample_sd_seconds"], statistics.stdev(group["samples_seconds"]))
            for field in ("mean_seconds", "sample_sd_seconds", "normalized_mean", "reference_mean_seconds"):
                self.reject(("series", index, field), group[field] + 0.01)
            self.reject(("series", index, "normalized_samples", 0), group["normalized_samples"][0] + 0.01)
        index = next(index for index, cell in enumerate(self.value["cells"]) if cell["r2_initial_batch_received"])
        self.reject(("cells", index, "r2_source_final_descriptive_speedup"), 1.0)
        self.reject(("cells", index, "r2_exact_calls"), 5)

    def test_claims_jobs_and_effective_effort_cannot_be_promoted(self):
        for key in ("causal_claim", "inferential_significance_claim", "scientifically_admitted_R2_gain"):
            self.reject(("boundaries", key), True)
        for key in ("causal_R1_R2_comparison_admitted", "equivalent_realized_search_effort", "same_allocation_or_time"):
            self.reject(("matched_cell", key), True)
        self.reject(("matched_cell", "r1_job_id"), "749843")
        self.reject(("matched_cell", "r2_confirmation_stream_review", "independent_performance_audit_verified"), True)
        self.reject(("matched_cell", "timeline", "budget_or_chronology_reset"), True)
        self.reject(("matched_cell", "accounting", "r2_delivered_exact_calls"), 5)

    def test_manifest_is_three_files_without_self_reference(self):
        manifest = load_json((DATA / "FILES.sha256.json").read_text(encoding="utf8"))
        self.assertEqual(manifest, FILE_PINS)
        self.assertNotIn("FILES.sha256.json", manifest)
        for name, ref in manifest.items():
            raw = (DATA / name).read_bytes()
            self.assertEqual(len(raw), ref["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ref["sha256"])

    def test_csv_duplicate_extra_columns_and_na_changes_rejected(self):
        text = (DATA / "matrix15-comparison.csv").read_text(encoding="utf8")
        rows = csv_rows(text, MATRIX_COLUMNS)
        self.assertEqual(len(rows), 60)
        self.assertEqual(sum(row["r2_initial_reference_seconds"] == "" for row in rows), 59)
        with self.assertRaises(EvidenceError):
            csv_rows(text.replace("subject_id,model", "subject_id,subject_id", 1), MATRIX_COLUMNS)
        with self.assertRaises(EvidenceError):
            csv_rows(text.replace("subject_id,model", "subject_id,private,model", 1), MATRIX_COLUMNS)

    def test_hash_provenance_rejects_tampered_data_and_unknown_annex(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / SUBDIR
            folder.mkdir(parents=True)
            for name in (*FILE_PINS, "FILES.sha256.json"):
                (folder / name).write_bytes((DATA / name).read_bytes())
            # Unrecognized inventory is rejected before unrelated source files are opened.
            (folder / "private.txt").write_text("private", encoding="utf8")
            with self.assertRaises(EvidenceError):
                verify(root)
            (folder / "private.txt").unlink()
            (folder / "comparison.json").write_text(json.dumps({**self.value, "fixture": True}), encoding="utf8")
            with self.assertRaises(EvidenceError):
                verify(root)


if __name__ == "__main__":
    unittest.main()
