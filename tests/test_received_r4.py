"""Reject misleading missing-data, changed history and remote-success claims."""
from contextlib import contextmanager
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.received import ReceivedError
from tools import received_r4

ROOT = Path(__file__).resolve().parents[1]


class ReceivedR4Tests(unittest.TestCase):
    @contextmanager
    def copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / received_r4.SUBDIR
            shutil.copytree(ROOT / received_r4.SUBDIR, folder)
            original = root / "evidence/received-2026-10-19/confirmations.csv"
            original.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "evidence/received-2026-10-19/confirmations.csv", original)
            yield root, folder

    def rewrite_rows(self, path, edit):
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        edit(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def rewrite_operations(self, path, edit):
        value = json.loads(path.read_text(encoding="utf-8"))
        edit(value)
        path.write_text(json.dumps(value), encoding="utf-8", newline="\n")

    def test_complete_snapshot_and_exact_reviewed_article(self):
        summary = received_r4.verify(ROOT)
        self.assertEqual((summary["matrix_cells"], summary["r2_NA"], summary["r1_zero_gains"]), (60, 60, 11))
        self.assertEqual(summary["complete_scientific_pairs"], 0)
        self.assertEqual(summary["r1_cost_scope_differences"], 3)

    def test_reject_archive_counter_used_as_received_unknown_cost(self):
        with self.copied() as (root, folder):
            def edit(rows):
                row = next(r for r in rows if r["subject_id"] == "2023-count" and r["model"] == "gpt-6-astra")
                row["r1_received_reconciled_unmetered_calls"] = row["r1_archived_unmetered_native_invocations"]
            self.rewrite_rows(folder / "matrix15.csv", edit)
            with self.assertRaisesRegex(ReceivedError, "Historical cost"):
                received_r4.verify_data(root)

    def test_reject_na_replaced_by_numeric_zero(self):
        with self.copied() as (root, folder):
            self.rewrite_rows(folder / "matrix15.csv", lambda rows: rows[0].__setitem__("r2_gain_fraction", "0"))
            with self.assertRaisesRegex(ReceivedError, "NA"):
                received_r4.verify_data(root)

    def test_reject_missing_or_duplicate_cell(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), self.copied() as (root, folder):
                def edit(rows):
                    rows.pop()
                    if duplicate:
                        rows.append(dict(rows[0]))
                self.rewrite_rows(folder / "matrix15.csv", edit)
                with self.assertRaises(ReceivedError):
                    received_r4.verify_data(root)

    def test_reject_changed_historical_r1_value(self):
        with self.copied() as (root, folder):
            self.rewrite_rows(folder / "matrix15.csv", lambda rows: rows[0].__setitem__("r1_speedup", "999"))
            with self.assertRaisesRegex(ReceivedError, "historical"):
                received_r4.verify_data(root)

    def test_reject_nonfinite_measured_value(self):
        with self.copied() as (root, folder):
            self.rewrite_rows(folder / "matrix15.csv", lambda rows: rows[0].__setitem__("r1_reference_seconds", "NaN"))
            with self.assertRaisesRegex(ReceivedError, "Nonfinite"):
                received_r4.verify_data(root)

    def test_reject_corrupt_authorization_changed_to_absent(self):
        with self.copied() as (root, folder):
            self.rewrite_operations(folder / "operational-status.json",
                lambda data: data["attempts"][1].__setitem__("authorization_files_present", False))
            with self.assertRaisesRegex(ReceivedError, "corrupt AUTH"):
                received_r4.verify_data(root)

    def test_reject_local_ascii_test_promoted_to_remote_success(self):
        with self.copied() as (root, folder):
            self.rewrite_operations(folder / "operational-status.json",
                lambda data: data["ascii_validation"].__setitem__("successful_remote_transport_proved", True))
            with self.assertRaisesRegex(ReceivedError, "remote success"):
                received_r4.verify_data(root)

    def test_reject_prepared_attempt_promoted_to_job(self):
        with self.copied() as (root, folder):
            self.rewrite_operations(folder / "operational-status.json",
                lambda data: data["attempt4_at_cutoff"].__setitem__("jobs_submitted", 3))
            with self.assertRaisesRegex(ReceivedError, "Prepared A4"):
                received_r4.verify_data(root)
