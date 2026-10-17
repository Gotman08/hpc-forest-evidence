"""Checks for evidence rejection, arithmetic and portability; no program execution."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.recompute import ROOT, EvidenceError, compare, compute, controller, load_json, scaling
from tools.verify import verify_links, verify_manifest


class TimingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controller_rows = [load_json(line) for line in
                               (ROOT / "evidence/controller/timings.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.cpu_rows = load_json((ROOT / "evidence/cpu-scaling/timings.json").read_text(encoding="utf-8"))

    def test_published_numbers_recompute_from_raw_records(self):
        expected = load_json((ROOT / "evidence/results.json").read_text(encoding="utf-8"))
        compare(compute(), expected)
        nbody = next(row for row in expected["cpu_scaling"]["comparisons"]
                     if row["subject"] == "2022-nbody" and row["cores"] == 16)
        self.assertAlmostEqual(nbody["own_core_speedup"], 14.376946408492195)

    def test_warmup_durations_do_not_change_reported_results(self):
        rows = copy.deepcopy(self.controller_rows)
        for row in rows:
            if row["phase"] == "warmup":
                row["cycles_wall_ns"] = [n * 1000 for n in row["cycles_wall_ns"]]
                row["wall_ns"] = sum(row["cycles_wall_ns"])
        self.assertEqual(controller(rows), controller(self.controller_rows))

    def test_controller_missing_and_duplicate_series_are_rejected(self):
        for rows in (self.controller_rows[:-1], self.controller_rows + self.controller_rows[:1]):
            with self.subTest(samples=len(rows)), self.assertRaises(EvidenceError):
                controller(rows)

    def test_controller_corrupt_counters_and_contracts_are_rejected(self):
        for field, value in (("wall_ns", 1), ("cpu_ns", True), ("seed", 24),
                             ("phase", "measurement"), ("cycles_wall_ns", [-1] * 8),
                             ("variant", "new_variant")):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.controller_rows)
                rows[0][field] = value
                with self.assertRaises(EvidenceError):
                    controller(rows)

    def test_different_traces_cannot_be_treated_as_matched(self):
        rows = copy.deepcopy(self.controller_rows)
        rows[1]["trace_sha256"] = "0" * 64
        with self.assertRaises(EvidenceError):
            controller(rows)

    def test_cpu_missing_and_duplicate_repetitions_are_rejected(self):
        for rows in (self.cpu_rows[:-1], self.cpu_rows + self.cpu_rows[:1]):
            with self.subTest(samples=len(rows)), self.assertRaises(EvidenceError):
                scaling(rows)

    def test_changed_executable_cannot_support_a_core_scaling_curve(self):
        rows = copy.deepcopy(self.cpu_rows)
        rows[1]["binary_sha256"] = "0" * 64
        with self.assertRaises(EvidenceError):
            scaling(rows)

    def test_changed_input_cannot_support_a_core_scaling_curve(self):
        rows = copy.deepcopy(self.cpu_rows)
        rows[1]["input_sha256"] = "0" * 64
        with self.assertRaises(EvidenceError):
            scaling(rows)

    def test_invalid_or_missing_correctness_is_never_accepted(self):
        for field, value in (("matches_oracle", False), ("matches_oracle", None),
                             ("returncode", 1), ("returncode", False)):
            with self.subTest(field=field, value=value):
                rows = copy.deepcopy(self.cpu_rows)
                rows[0][field] = value
                with self.assertRaises(EvidenceError):
                    scaling(rows)

    def test_bad_sample_times_are_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True, "0.1"):
            with self.subTest(value=value):
                rows = copy.deepcopy(self.cpu_rows)
                rows[0]["seconds"] = value
                with self.assertRaises(EvidenceError):
                    scaling(rows)

    def test_zero_cpu_counter_remains_an_observed_counter(self):
        rows = copy.deepcopy(self.cpu_rows)
        rows[0]["cpu_seconds"] = 0.0
        self.assertEqual(scaling(rows)["samples"], 200)

    def test_ambiguous_json_is_rejected(self):
        for text in ('{"value":1,"value":2}', '{"value":NaN}', '{"value":Infinity}'):
            with self.subTest(text=text), self.assertRaises(EvidenceError):
                load_json(text)

    def test_published_result_changes_are_detected(self):
        for left, right in (({"x": True}, {"x": 1}), ({"x": 1}, {"x": 1.01}),
                            ({"x": 1}, {"y": 1}), ([1], [1, 2])):
            with self.subTest(right=right), self.assertRaises(EvidenceError):
                compare(left, right)


class BundleIntegrityTests(unittest.TestCase):
    def make_bundle(self, root, *, name="README.md"):
        content = b"example\n"
        (root / "README.md").write_bytes(content)
        manifest = {"schema": 1, "files": [{"path": name, "bytes": len(content),
                                             "sha256": hashlib.sha256(content).hexdigest()}]}
        (root / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_valid_bundle_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_bundle(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertEqual(verify_manifest(root), 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_modified_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_bundle(root)
            (root / "README.md").write_bytes(b"changed\n")
            with self.assertRaises(EvidenceError):
                verify_manifest(root)

    def test_unlisted_public_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_bundle(root)
            (root / "unexpected.txt").write_bytes(b"unreviewed")
            with self.assertRaises(EvidenceError):
                verify_manifest(root)

    def test_missing_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_bundle(root)
            (root / "README.md").unlink()
            with self.assertRaises(EvidenceError):
                verify_manifest(root)

    def test_manifest_cannot_escape_the_repository(self):
        for name in ("../outside", "/absolute", "C:/absolute", "..\\outside", "MANIFEST.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.make_bundle(root, name=name)
                with self.assertRaises(EvidenceError):
                    verify_manifest(root)

    def test_broken_document_links_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text("[Missing](missing.md)", encoding="utf-8")
            with self.assertRaises(EvidenceError):
                verify_links(root)

    def test_valid_relative_link_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text("[Evidence](data.json)", encoding="utf-8")
            (root / "data.json").write_text("{}", encoding="utf-8")
            self.assertEqual(verify_links(root), 1)


if __name__ == "__main__":
    unittest.main()
