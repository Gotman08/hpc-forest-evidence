"""NEUTRAL fixtures only: no real process enumeration, native launch, or network."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import capacity as cap

NOW = 1800000000.0
BINDING = {"scope_id": "NEUTRAL-matrix-scope", "cell_key": "NEUTRAL/cell", "subject_id": "NEUTRAL-subject",
    "model": "NEUTRAL-model", "effort": "max", "session_id": "a" * 32, "job_id": "NEUTRAL-job",
    "remote_root": "/NEUTRAL/root", "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
    "preparation_manifest_sha256": "3" * 64, "r1_contract_sha256": "4" * 64}


def process(pid=1, *, parent=0, module="matrix15_worker", session="b" * 32, role="worker"):
    script = "hpc_forest." + module if role == "worker" else "native-launcher.ps1"
    return {"ProcessId": pid, "ParentProcessId": parent, "ExecutablePath": "C:\\NEUTRAL\\python.exe",
        "CommandLine": f'python -m {script} --session-id {session} --channel /NEUTRAL/mailbox',
        "CreationDate": datetime.fromtimestamp(NOW - 60, UTC).isoformat()}


def idle():
    return {"ProcessId": 0, "ParentProcessId": 0, "ExecutablePath": None, "CommandLine": None, "CreationDate": None}


def census(processes=None):
    return json.dumps([idle()] if processes is None else processes).encode()


class CapacityFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="NEUTRAL-capacity-")
        self.root = Path(self.temp.name)
        self.registry, self.output = self.root / "registry", self.root / "output"
        self.registry.mkdir()
        self.output.mkdir()
        self.lock = self.root / "capacity.lock"
        self.factory_number = 0
        self.no_real = patch.object(cap, "collect_windows", side_effect=AssertionError("Real census prohibited by NEUTRAL test"))
        self.no_real.start()

    def tearDown(self):
        self.no_real.stop()
        self.temp.cleanup()

    def evidence(self, ref, analysis):
        self.assertTrue(self.lock.exists())
        self.assertEqual(analysis["observed_at"], NOW)
        self.factory_number += 1
        primary = cap.exclusive_bytes(self.root / f"NEUTRAL-primary-report-{self.factory_number}.txt",
            b"NEUTRAL fixture primary report. No operational approval; verified=False.\n")
        producer_sha = cap.reference(cap.__file__)["sha256"]
        values = {
            "reservation_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": producer_sha,
                "exclusive_lock_reviewed": True, "pending_capacity_accounting_reviewed": True,
                "maximum_native_workers_total": 4, "evidence_refs": [primary]},
            "local_projection_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": producer_sha,
                "private_census_export_excluded": True, "current_census_binding_reviewed": True,
                "fixture_promotion_excluded": True, "evidence_refs": [primary]},
            "source_only_received_closure": {"source_only_received": True, "source_only_closed": True,
                "source_only_may_resume": False, "closed_source_only_session_ids": ["d" * 32], "evidence_refs": [primary]},
            "source_only_absence": {"observed_at": analysis["observed_at"], "private_full_census_sha256": ref["sha256"],
                "source_only_active_workers": 0, "all_native_workers_known": True,
                "source_only_received_closure_sha256": None},
            "other_owned_worker_reconciliation": {"observed_at": analysis["observed_at"], "private_full_census_sha256": ref["sha256"],
                "other_native_workers_count": analysis["native_workers_count"], "all_native_workers_known": True,
                "launcher_python_pairs_count_as_one": True, "reconciled_session_ids": analysis["session_ids"],
                "owned_worker_receipts": [], "all_workers_owned_and_reconciled": True}}
        for index, group in enumerate(analysis["private_native_groups"]):
            owned_ref = cap.exclusive_json(self.root / f"NEUTRAL-owned-{self.factory_number}-{index}.json", {
                "schema": "hpc-forest-native-owned-worker-identity-v1", "verified": False, "ownership_established": True,
                "session_id": group[0]["session_id"], "channel": group[0]["channel"],
                "processes": [{key: item[key] for key in cap.PROCESS_FIELDS} for item in group]})
            values["other_owned_worker_reconciliation"]["owned_worker_receipts"].append(owned_ref)
        refs = {}
        order = ["source_only_received_closure", *sorted(cap.EXTERNAL_EVIDENCE_FIELDS - {"source_only_received_closure"})]
        for name in order:
            if name == "source_only_absence":
                values[name]["source_only_received_closure_sha256"] = refs["source_only_received_closure"]["sha256"]
            refs[name] = cap.exclusive_json(self.root / f"NEUTRAL-{self.factory_number}-{name}.json",
                {**BINDING, "verified": False, "schema": cap.EVIDENCE_SCHEMAS[name], **values[name]})
        return refs

    def context(self, *, raw=None, binding=None, factory=None, now=NOW):
        return cap.exclusive_capacity(self.lock, self.registry, BINDING if binding is None else binding,
            self.output, now, evidence_factory=self.evidence if factory is None else factory,
            collector=lambda: census() if raw is None else raw)

    def test_fixture_lock_real_but_every_verdict_false_and_census_private(self):
        with self.context() as result:
            self.assertTrue(self.lock.exists())
            self.assertFalse(result["verified"])
            for key in ("lane", "projection", "reservation", "registry_reservation"):
                self.assertFalse(cap.read_json(result[key]["path"])["verified"])
            self.assertTrue(Path(result["private_census"]["path"]).is_relative_to(self.registry / "private"))
            projected = Path(result["projection"]["path"]).read_text()
            self.assertNotIn("CommandLine", projected)
            self.assertNotIn(result["private_census"]["path"], projected)
            self.assertEqual(Path(result["new_cache_root"]).parent, self.registry)
        self.assertFalse(self.lock.exists())
        self.assertTrue(Path(result["registry_reservation"]["path"]).exists())

    def test_exclusive_lock_collision_has_no_collection_or_overwrite(self):
        self.lock.write_text("NEUTRAL-owner")
        with self.assertRaises(FileExistsError):
            with self.context():
                self.fail("Lock admitted")
        self.assertEqual(self.lock.read_text(), "NEUTRAL-owner")
        self.assertEqual(list(self.registry.iterdir()), [])

    def test_output_collision_preserves_bytes_before_lock(self):
        collision = self.output / "owned-lane-projection.json"
        collision.write_bytes(b"NEUTRAL-existing")
        with self.assertRaisesRegex(cap.CapacityError, "collision"):
            with self.context():
                self.fail("Collision admitted")
        self.assertEqual(collision.read_bytes(), b"NEUTRAL-existing")
        self.assertFalse(self.lock.exists())

    def test_full_binding_exact_and_digest_checks(self):
        for mutation in ({"extra": "NEUTRAL"}, {"effort": "high"}, {"source_zip_sha256": "bad"}, {"session_id": "other"}):
            with self.subTest(mutation=mutation), self.assertRaises(cap.CapacityError):
                with self.context(binding={**BINDING, **mutation}):
                    self.fail("Invalid binding admitted")

    def test_invalid_now_refused(self):
        for value in (float("nan"), float("inf"), True, "NEUTRAL"):
            with self.subTest(value=value), self.assertRaises(cap.CapacityError):
                with self.context(now=value):
                    self.fail("Invalid time admitted")

    def test_four_known_workers_refused(self):
        workers = [process(index + 1, session=str(index + 1) * 32) for index in range(4)]
        with self.assertRaisesRegex(cap.CapacityError, "cap4"):
            with self.context(raw=census(workers)):
                self.fail("Cap exceeded")
        self.assertFalse(self.lock.exists())

    def test_pending_slots_count_without_active_process_and_session_never_reused(self):
        with self.context() as result:
            reservation = cap.read_json(result["reservation"]["path"])
        for index in range(3):
            value = {**reservation, "session_id": str(index + 1) * 32, "reservation_id": str(index + 1) * 32}
            cap.exclusive_json(self.registry / f"{index}.reservation.json", value)
        other_output = self.root / "other-output"
        other_output.mkdir()
        with self.assertRaisesRegex(cap.CapacityError, "already owns"):
            with cap.exclusive_capacity(self.lock, self.registry, BINDING, other_output, NOW,
                evidence_factory=self.evidence, collector=census):
                self.fail("Reservation replayed")
        self.output = other_output
        other = {**BINDING, "session_id": "c" * 32}
        with self.assertRaisesRegex(cap.CapacityError, "cap4"):
            with self.context(binding=other):
                self.fail("Pending slots ignored")

    def test_pending_active_same_session_count_once(self):
        with self.context() as result:
            reservation = cap.read_json(result["reservation"]["path"])
        analysis = cap.classify_processes([process(session=BINDING["session_id"])], NOW)
        other = {**BINDING, "session_id": "c" * 32}
        self.assertEqual(cap.pending_reservations(self.registry, other, analysis, fixture=True), set())
        self.assertFalse(reservation["verified"])

    def test_bad_hash_or_binding_or_current_census_in_evidence_refused(self):
        for wrong in ("hash", "binding", "census", "verdict"):
            with self.subTest(wrong=wrong):
                def factory(ref, analysis, wrong=wrong):
                    refs = self.evidence(ref, analysis)
                    key = "source_only_absence"
                    if wrong == "hash":
                        refs[key]["sha256"] = "f" * 64
                    else:
                        value = cap.read_json(refs[key]["path"])
                        field, bad = {"binding": ("session_id", "f" * 32), "census": ("private_full_census_sha256", "f" * 64),
                                      "verdict": ("verified", True)}[wrong]
                        value[field] = bad
                        refs[key] = cap.exclusive_json(self.root / (f"NEUTRAL-{wrong}-{self.factory_number}.json"), value)
                    return refs
                with self.assertRaises(cap.CapacityError):
                    with self.context(factory=factory):
                        self.fail("Unbound evidence admitted")
                self.assertEqual(list(self.registry.glob("*.reservation.json")), [])

    def test_malformed_or_duplicate_census_json_is_not_admitted(self):
        for raw in (b"[]", b"{}", b"not-json", b'[{"ProcessId":1,"ProcessId":2}]'):
            with self.subTest(raw=raw), self.assertRaises((cap.CapacityError, json.JSONDecodeError)):
                with self.context(raw=raw):
                    self.fail("Malformed census admitted")

    def test_no_lock_steal_or_silent_unlock(self):
        with self.assertRaisesRegex(cap.CapacityError, "ownership changed"):
            with self.context():
                self.lock.write_bytes(b"NEUTRAL-replaced-owner")
        self.assertEqual(self.lock.read_bytes(), b"NEUTRAL-replaced-owner")

    def test_evidence_callback_cannot_replace_lock_and_then_admit(self):
        def factory(ref, analysis):
            refs = self.evidence(ref, analysis)
            self.lock.write_bytes(b"NEUTRAL-replaced-owner")
            return refs
        with self.assertRaisesRegex(cap.CapacityError, "ownership changed"):
            with self.context(factory=factory):
                self.fail("Changed lock admitted before launch")
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.registry.glob("*.reservation.json")), [])

    def test_private_census_and_output_trees_must_be_disjoint(self):
        for path in (self.registry, self.registry / "private", self.root):
            path.mkdir(exist_ok=True)
            self.output = path
            with self.subTest(path=path), self.assertRaisesRegex(cap.CapacityError, "disjoint"):
                with self.context():
                    self.fail("Raw census could enter exported output")
        self.assertFalse(self.lock.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_private_junction_to_output_and_ancestor_junction_refused(self):
        private = self.registry / "private"
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(private), str(self.output)],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(cap.CapacityError, "junction"):
            with self.context():
                self.fail("Private junction leaked census")
        self.assertEqual(list(self.output.iterdir()), [])
        alias = self.root / "NEUTRAL-junction-ancestor"
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(self.registry)],
                       check=True, capture_output=True)
        self.registry = alias
        with self.assertRaisesRegex(cap.CapacityError, "junction"):
            with self.context():
                self.fail("Registry ancestor junction accepted")

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_private_junction_created_during_mkdir_refused_after_creation(self):
        original_mkdir = Path.mkdir
        private = self.registry / "private"

        def redirected_mkdir(path, *args, **kwargs):
            result = original_mkdir(path, *args, **kwargs)
            if path == private:
                path.rmdir()
                subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(path), str(self.output)],
                               check=True, capture_output=True)
            return result

        with patch.object(Path, "mkdir", redirected_mkdir), self.assertRaisesRegex(cap.CapacityError, "junction"):
            with self.context():
                self.fail("Postcreation redirect leaked census")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_typed_evidence_refuses_empty_payload_missing_binding_wrong_role_or_business(self):
        cases = ("empty", "binding", "schema", "business", "producer", "timestamp", "no-primary", "bad-primary")
        for case in cases:
            def factory(ref, analysis, case=case):
                refs = self.evidence(ref, analysis)
                name = "source_only_absence" if case == "timestamp" else "reservation_producer_review"
                value = cap.read_json(refs[name]["path"])
                if case == "empty":
                    value = {"verified": False, "private_full_census_sha256": ref["sha256"]}
                elif case == "binding":
                    del value["session_id"]
                elif case == "schema":
                    value["schema"] = cap.EVIDENCE_SCHEMAS["source_only_absence"]
                elif case == "business":
                    value["exclusive_lock_reviewed"] = False
                elif case == "producer":
                    value["reviewed_capacity_producer_sha256"] = "f" * 64
                elif case == "timestamp":
                    value["observed_at"] += 1
                elif case == "no-primary":
                    value["evidence_refs"] = []
                elif case == "bad-primary":
                    value["evidence_refs"][0]["sha256"] = "f" * 64
                refs[name] = cap.exclusive_json(self.root / f"NEUTRAL-malformed-{self.factory_number}.json", value)
                return refs
            with self.subTest(case=case), self.assertRaises(cap.CapacityError):
                with self.context(factory=factory):
                    self.fail("Untyped or unproven evidence admitted")
        self.assertEqual(list(self.registry.glob("*.reservation.json")), [])

    def test_fixture_owned_worker_receipt_matches_full_identity(self):
        with self.context(raw=census([process()])) as result:
            self.assertFalse(result["verified"])
            self.assertEqual(cap.read_json(result["lane"]["path"])["active_native_workers_before_start"], 1)

    def test_reconciliation_refuses_owned_receipt_missing_or_with_other_process_creation(self):
        for case in ("missing", "creation"):
            def factory(ref, analysis, case=case):
                refs = self.evidence(ref, analysis)
                name = "other_owned_worker_reconciliation"
                value = cap.read_json(refs[name]["path"])
                if case == "missing":
                    value["owned_worker_receipts"] = []
                else:
                    receipt = cap.read_json(value["owned_worker_receipts"][0]["path"])
                    receipt["processes"][0]["CreationDate"] = datetime.fromtimestamp(NOW - 59, UTC).isoformat()
                    value["owned_worker_receipts"] = [cap.exclusive_json(self.root / f"NEUTRAL-wrong-identity-{self.factory_number}.json", receipt)]
                refs[name] = cap.exclusive_json(self.root / f"NEUTRAL-reconcile-{self.factory_number}.json", value)
                return refs
            with self.subTest(case=case), self.assertRaises(cap.CapacityError):
                with self.context(raw=census([process()]), factory=factory):
                    self.fail("Unreconciled current native worker admitted")


class ClassificationFixtures(unittest.TestCase):
    def test_worker_modules_and_launcher_python_pair(self):
        for module in cap.WORKER_MODULES:
            with self.subTest(module=module):
                launcher = process(1, role="launcher")
                worker = process(2, parent=1, module=module)
                analysis = cap.classify_processes([launcher, worker], NOW)
                self.assertEqual(analysis["native_workers_count"], 1)
                self.assertEqual(len(analysis["private_native_groups"][0]), 2)

    def test_unknown_native_source_only_or_incomplete_identity_fail_closed(self):
        original = process()
        variants = [
            {**original, "CommandLine": original["CommandLine"].replace("matrix15_worker", "unknown_worker")},
            {**original, "CommandLine": original["CommandLine"] + " --kind source-only"},
            {**original, "CommandLine": original["CommandLine"] + " --kind source_only"},
            {**original, "CommandLine": None},
            {**original, "ExecutablePath": None}, {**original, "CreationDate": None},
            {**original, "CreationDate": datetime.fromtimestamp(NOW + 1, UTC).isoformat()},
            {**original, "CreationDate": "2026-01-01T00:00:00"},
            {**original, "CommandLine": original["CommandLine"] + " --session-id " + "f" * 32}]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(cap.CapacityError):
                cap.classify_processes([variant], NOW)

    def test_foreign_nonworker_codex_does_not_consume_native_hpc_slot(self):
        value = {**process(), "CommandLine": "C:\\NEUTRAL\\codex.exe app-server", "ExecutablePath": "C:\\NEUTRAL\\codex.exe"}
        self.assertEqual(cap.classify_processes([idle(), value], NOW)["native_workers_count"], 0)

    def test_contradictory_pair_and_duplicate_session_workers_fail_closed(self):
        for items in ([process(1, role="launcher"), process(2, parent=1, session="c" * 32)],
                      [process(1), process(2)],
                      [process(1, role="launcher"), process(2, parent=1), process(3, parent=1)]):
            with self.subTest(items=items), self.assertRaises(cap.CapacityError):
                cap.classify_processes(items, NOW)

    def test_reused_parent_pid_and_duplicate_full_identity_refused(self):
        launcher, worker = process(1, role="launcher"), process(2, parent=1)
        launcher["CreationDate"] = datetime.fromtimestamp(NOW - 59, UTC).isoformat()
        with self.assertRaisesRegex(cap.CapacityError, "created after"):
            cap.classify_processes([launcher, worker], NOW)
        with self.assertRaisesRegex(cap.CapacityError, "duplicate process"):
            cap.classify_processes([process(1), process(1, session="c" * 32)], NOW)


if __name__ == "__main__":
    unittest.main()
