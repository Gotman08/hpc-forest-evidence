"""Offline completeness, unknown-cost preservation and tamper rejection checks."""
import contextlib
import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import received

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / received.SUBDIR


class ReceivedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = received.verify(ROOT)

    @contextlib.contextmanager
    def copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / received.SUBDIR
            shutil.copytree(DATA, destination)
            yield root, destination

    def test_complete_received_inventory_and_negative_trials(self):
        expected = {"registers": 209, "confirmations": 193, "native_cohorts": 14,
                    "cpu_samples": 11575, "cpu_points": 2315, "cpu_comparisons": 1830,
                    "cpu_campaigns": 58, "cpu_batches": 10, "trials": 2482,
                    "historical_summaries": 42, "cost_exports": 11}
        for key, value in expected.items():
            self.assertEqual(self.summary[key], value)
        self.assertEqual(self.summary["trial_result_states"], {
            "valid": 1685, "build_failed": 211, "incorrect": 144,
            "generation_failed": 142, "infrastructure_error": 195,
            "duplicate": 103, "cancelled_budget": 1, "runtime_failed": 1})
        self.assertEqual(self.summary["cohorts"]["count"], 20)
        self.assertEqual(self.summary["cohorts"]["source_only_sol"], 15)

    def test_sol_unknown_costs_and_preinvocation_expirations_remain_distinct(self):
        exports = received.load(DATA / "cost-observations.json")
        sol = next(e for e in exports if e["source"] == "couts-source-only-sol.json")
        self.assertEqual(sol["summary"]["known_exact_tokens"], 2676472)
        self.assertEqual(sol["summary"]["observations"], 124)
        self.assertEqual(sol["summary"]["unknown_exact_total"], 10)
        self.assertFalse(sol["total_exact_consumption_available"])
        measured = [r for r in sol["calls"] if r["state"] == "exact"]
        unknown = [r for r in sol["calls"] if r["state"] == "unmeasured"]
        expired = [r for r in sol["calls"] if r["state"] == "expired_before_invocation_proven"]
        self.assertEqual((len(measured), len(unknown), len(expired)), (111, 10, 3))
        self.assertTrue(all(r["exact_total"] is None for r in unknown))
        self.assertTrue(all(r["exact_total"] == 0 for r in expired))
        self.assertNotIn("global_exact_tokens", self.summary)

    def test_sol_r2h_pairs_and_incidents_are_separate(self):
        sol = received.load(DATA / "sol-r2h.json")
        self.assertEqual(sum(c["exact_tokens"] for c in sol["calls"]), 59037)
        self.assertEqual([len(sol[r]["times"]) for r in ["reference", "winner"]], [5, 5])
        self.assertAlmostEqual(sol["reported_speedup"], 8.927268770813551)
        self.assertFalse(sol["independent_evaluator_implementation"])
        self.assertFalse(sol["historical_aggregates_include_this_supplement"])
        self.assertEqual({r["model"] for r in sol["zero_start_allocations"]},
                         {"gpt-6-astra", "gpt-5.6-terra", "gpt-6-luna"})
        operations = received.load(DATA / "operational-status.json")
        self.assertEqual(operations["r2g"]["known_exact_tokens"], 146676)
        self.assertFalse(operations["r2g"]["five_confirmations_verified"])
        self.assertFalse(operations["r2g"]["native_research_admitted"])

    def test_campaign_mapping_is_opaque_and_source_fingerprints_are_present(self):
        rows = received.load(DATA / "campaigns.json")
        self.assertEqual(len({r["campaign_id"] for r in rows}), 209)
        for row in rows:
            self.assertEqual(row["campaign_id"], "campaign-" + row["campaign_root_sha256"])
            self.assertNotIn("campaign_root", row)
        sources = received.load(DATA / "provenance.json")["sources"]
        self.assertIn("registres-recalcules.json", {s["name"] for s in sources})
        self.assertIn("RESULT-EXTERNAL-FROZEN-PAIR.json", {s["name"] for s in sources})

    def test_verifier_is_portable_and_leaves_evidence_unchanged(self):
        with self.copied() as (root, data):
            def hashes():
                return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in data.iterdir() if p.is_file()}
            before = hashes()
            self.assertEqual(received.verify(root), self.summary)
            self.assertEqual(before, hashes())

    def test_missing_cpu_repetition_is_rejected(self):
        with self.copied() as (root, data):
            path = data / "cpu-timings.csv"
            rows = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8", newline="\n")
            with self.assertRaises(received.ReceivedError):
                received.verify(root)

    def test_malformed_csv_schema_and_nonfinite_values_are_rejected(self):
        for field, value in [("header", "private_prompt"), ("wall_seconds", "NaN")]:
            with self.subTest(field=field), self.copied() as (root, data):
                path = data / "cpu-timings.csv"
                lines = path.read_text(encoding="utf-8").splitlines()
                if field == "header":
                    lines[0] += "," + value
                else:
                    row = lines[1].split(",")
                    row[received.CPU_FIELDS.index(field)] = value
                    lines[1] = ",".join(row)
                path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
                with self.assertRaises(received.ReceivedError):
                    received.verify(root)

    def test_unapproved_nested_trial_content_is_rejected(self):
        with self.copied() as (root, data):
            path = data / "registers.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[0])
            row["trials"][0]["mission"]["prompt"] = "private"
            lines[0] = json.dumps(row)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            with self.assertRaises(received.ReceivedError):
                received.verify(root)

    def test_unknown_cost_cannot_silently_become_zero(self):
        with self.copied() as (root, data):
            path = data / "cost-observations.json"
            exports = received.load(path)
            row = next(r for e in exports for r in e["calls"] if r["exact_total"] is None)
            row["exact_total"] = 0
            received.write_json(path, exports)
            with self.assertRaises(received.ReceivedError):
                received.verify(root)

    def test_jointly_corrupted_scaling_and_efficiency_are_rejected(self):
        with self.copied() as (root, data):
            path = data / "cpu-comparisons.csv"
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            row = next(r for r in rows if r["cores"] == "16")
            row["scaling_speedup"] = "12345"
            row["scaling_efficiency"] = str(12345 / int(row["cores"]))
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=received.COMPARE_FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(received.ReceivedError, "Arithmetic mismatch"):
                received.verify(root)

    def test_duplicate_json_keys_and_boolean_token_count_are_rejected(self):
        with self.assertRaises(received.ReceivedError):
            received.parse_json('{"state": "exact", "state": "pending"}')
        with self.copied() as (root, data):
            path = data / "cost-observations.json"
            exports = received.load(path)
            exports[0]["calls"][0]["exact_total"] = True
            received.write_json(path, exports)
            with self.assertRaises(received.ReceivedError):
                received.verify(root)


if __name__ == "__main__":
    unittest.main()
