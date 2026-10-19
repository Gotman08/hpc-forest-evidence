"""Reject altered baseline arithmetic, missing subjects and unsupported result claims."""
import copy
import json
import unittest
from pathlib import Path

from tools.qualification import validate
from tools.recompute import EvidenceError

ROOT = Path(__file__).resolve().parents[1]


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads((ROOT / "evidence/qualification-2026-10-19/baselines.json").read_text(encoding="utf-8"))

    def test_recalculate_all_received_baselines(self):
        self.assertEqual(validate(self.value), {"subjects": 15, "samples": 75})

    def test_reject_changed_timing_statistics(self):
        for key in ("mean_seconds", "sample_stdev_seconds"):
            with self.subTest(key=key):
                value = copy.deepcopy(self.value)
                value["subjects"][0][key] += 0.001
                with self.assertRaises(EvidenceError):
                    validate(value)

    def test_reject_nonfinite_boolean_zero_and_missing_samples(self):
        for bad in (float("nan"), float("inf"), True, 0, -1, "0.1"):
            with self.subTest(value=bad):
                value = copy.deepcopy(self.value)
                value["subjects"][0]["confirmation_seconds"][0] = bad
                with self.assertRaises(EvidenceError):
                    validate(value)
        self.value["subjects"][0]["confirmation_seconds"].pop()
        with self.assertRaises(EvidenceError):
            validate(self.value)

    def test_reject_model_gain_claims_and_private_extra_fields(self):
        for key, bad in (("native_model_calls", 1), ("scientific_gain_claimed", True),
                         ("native_matrix_results_claimed", True), ("scope", "model_result"),
                         ("private_local_path", "private")):
            with self.subTest(key=key):
                value = copy.deepcopy(self.value)
                value[key] = bad
                with self.assertRaises(EvidenceError):
                    validate(value)

    def test_reject_incomplete_reordered_or_duplicated_subjects(self):
        for mutation in (lambda rows: rows.pop(), lambda rows: rows.reverse(),
                         lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0]))):
            value = copy.deepcopy(self.value)
            mutation(value["subjects"])
            with self.assertRaises(EvidenceError):
                validate(value)


if __name__ == "__main__":
    unittest.main()
