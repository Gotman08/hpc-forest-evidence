"""NEUTRAL local artifacts only. No Slurm, transport, model, worker or operational emission."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bootstrap_extension as ext
import extension_gate as gate_module

ROOT = Path(__file__).resolve().parents[2]
SHARED_LOCAL = ROOT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2/shared-windows"
sys.path.insert(0, str(SHARED_LOCAL / "project/src"))
from hpc_forest import matrix15_first_batch as batch
from hpc_forest import native_matrix15 as native
from hpc_forest.core import InfrastructureError, digest


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = ext.load_helper(Path(__file__).with_name("sealed-bootstrap-helper.py").absolute())
        cls.plan_raw = (SHARED_LOCAL / "plan-60-v2.json").read_bytes()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve()
        self.mapping = {}
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def write(self, remote, value):
        self.counter += 1
        path = self.path / f"NEUTRAL-{self.counter}.json"
        raw = self.b.encode(value)
        path.write_bytes(raw)
        ref = {"path": remote, "sha256": self.b.sha(raw)}
        self.mapping[(remote, ref["sha256"])] = path
        return ref

    def resolver(self, ref):
        return self.mapping[(ref["path"], ref["sha256"])]

    def fixture(self):
        _plan, upstream = ext.registered_selection(self.b, self.plan_raw, ext.FIRST_CELL)
        binding = {**upstream, "job_id": "755999"}
        output = ext.FIRST_ROOT + "/results-755999"
        identity = {**binding, "protocol_id": "7" * 64}
        plan_ref = {"path": ext.SHARED + "/plan-60-v2.json", "sha256": ext.PLAN_SHA}
        self.mapping[(plan_ref["path"], plan_ref["sha256"])] = SHARED_LOCAL / "plan-60-v2.json"
        auth = json.loads((SHARED_LOCAL.parent / "AUTHORIZATION-DRAFT-ARM.json").read_text())
        auth.update({key: value for key, value in binding.items() if key in native.AUTHORIZATION_FIELDS})
        auth["verified"] = True
        auth["artifacts"]["plan"] = plan_ref
        request_ref = self.write(output + "/mailbox/NEUTRAL-request.json", {"nonce": "a" * 32})
        private = {key: "b" * 64 for key in ("invocation_sha256", "process_sha256", "argv_sha256",
                                             "skill_override_sha256", "task_cli_policy_sha256")}
        call = {"request": request_ref, "private_cli_records": private, "private_cli_review_required": True,
                "private_cli_argv_verified": False, "invocation": {"sha256": "c" * 64}, "process": {"sha256": "d" * 64}}
        outcome = {"status": "incorrect", "correct": False, "logs": ["NEUTRAL-preserved.log"]}
        evaluation_ref = self.write(output + "/evaluation.json", {**identity, "never_model_input": True,
            "experiment_id": "NEUTRAL-negative", "outcome": outcome})
        first = {**identity, "verified": True, "technical_errors_found": False, "invocation_unknown": False,
                 "first_normal_delivered_call": call, "all_started_calls_reconciled": [call],
                 "first_real_evaluation": {"experiment_id": "NEUTRAL-negative", "status": "incorrect", "outcome_sha256": digest(outcome)},
                 "private_cli_review_required": True, "private_cli_argv_verified": False,
                 "observation_mode": "command-stream-v1", "private_case_v2_claimed": False}
        first_ref = self.write(output + "/premier-demarrage-verifie.json", first)
        snapshot = {**identity, "first_start_receipt": first_ref, "evaluation_snapshot": evaluation_ref}
        snapshot_ref = self.write(output + "/premier-batch-en-attente.json", snapshot)
        audit = {"schema": "hpc-forest-matrix15-private-cli-audit-digest-projection-v1", **identity,
                 "verified": True, "first_start_receipt_sha256": first_ref["sha256"], "paused_snapshot_sha256": snapshot_ref["sha256"],
                 "call_bindings": {"a" * 32: {**private, "invocation_projection_sha256": "c" * 64, "process_projection_sha256": "d" * 64}},
                 "all_private_raws_received_and_hashed": True, "argv_matches_projections_and_local_policy": True,
                 "cli_diagnostics_clean": True, "raw_skill_paths_exported": False, "private_review_receipt_sha256": "e" * 64}
        audit_ref = self.write(output + "/audit-cli-prive-digest.json", audit)
        release = {"schema": "hpc-forest-matrix15-first-batch-release-v1", **identity, "verified": True,
                   "paused_snapshot": snapshot_ref, "first_start_receipt": first_ref, "evaluation_snapshot": evaluation_ref,
                   "private_cli_audit": audit_ref, "no_replay": True, "new_model_or_budget_authorized": False}
        release_ref = self.write(output + "/autorisation-apres-premier-batch.json", release)
        accepted = {"verified": True, **identity, "release": release_ref, "private_cli_audit": audit_ref,
                    "private_review_receipt_sha256": "e" * 64, "budget_or_chronology_reset": False, "replayed_claims": 0}
        accepted_ref = self.write(output + "/premier-batch-release-verifiee.json", accepted)
        proposal = {"schema": "hpc-forest-matrix15-first-batch-proposal-receipt-v1", "verified": True, **identity,
            "input": {"path": "C:/NEUTRAL/input.json", "sha256": "1" * 64, "bytes": 1},
            "private_audit": {"path": "C:/NEUTRAL/AUDIT-PRIVE.json", "sha256": "e" * 64, "bytes": 1},
            "projection": {"path": "C:/NEUTRAL/projection.json", "sha256": audit_ref["sha256"], "bytes": 1},
            "proposed_release": {"path": "C:/NEUTRAL/release.json", "sha256": release_ref["sha256"], "bytes": 1},
            "source127_validate_first_batch_release_passed": True, "release_installed": False,
            "upload_performed": False, "native_model_calls": 0, "no_replay": True,
            "new_model_or_budget_authorized": False, "existing_search_deadline": 1000}
        proposal_ref = self.write(ext.FIRST_ROOT + "-admission/first-batch-proposal-receipt.json", proposal)
        root_review = {"schema": "hpc-forest-matrix15-extension-first-batch-root-review-v1", "verified": True,
            "evidence_origin": "received", "first_binding": binding, "source_zip_sha256": self.b.SOURCE_SHA256,
            "plan_sha256": ext.PLAN_SHA, "all_private_raws_received_and_hashed": True, "actual_arm_release_received": True,
            "release_sha256": release_ref["sha256"], "engine_release_receipt_sha256": accepted_ref["sha256"],
            "private_review_receipt_sha256": "e" * 64, "proposal_receipt_sha256": proposal_ref["sha256"],
            "root_review_instruction": "NEUTRAL test fixture, never a production approval", "reviewed_at": 1,
            "automatic_extension": False}
        gate = {"schema": ext.GATE_SCHEMA if hasattr(ext, "GATE_SCHEMA") else gate_module.SCHEMA,
                "verified": True, "evidence_origin": "received", "source_zip_sha256": self.b.SOURCE_SHA256,
                "plan_sha256": ext.PLAN_SHA, "first_binding": binding,
                "authorization": self.write(ext.FIRST_ROOT + "-admission/authorization.json", auth),
                "paused_snapshot": snapshot_ref, "first_start_receipt": first_ref, "evaluation_snapshot": evaluation_ref,
                "release": release_ref, "private_cli_audit": audit_ref, "engine_release_receipt": accepted_ref,
                "proposal_receipt": proposal_ref,
                "root_reception_review": self.write(ext.FIRST_ROOT + "-admission/extension-first-batch-root-review.json", root_review)}
        return gate, root_review, accepted, release

    def validate(self, gate):
        return gate_module.validate_gate(gate, read_ref=self.resolver, native=native, batch=batch)

    def test_exact_sixty_cells_and_unique_roots(self):
        plan = self.b.read_json(self.plan_raw)
        roots = set()
        for cell in plan["cells"]:
            _plan, binding = ext.registered_selection(self.b, self.plan_raw, cell["cell_key"])
            self.assertEqual(binding["effort"], "max")
            self.assertTrue(binding["remote_root"].endswith(binding["session_id"]))
            roots.add(binding["remote_root"])
        self.assertEqual(len(roots), 60)
        with self.assertRaisesRegex(ValueError, "outside"):
            ext.registered_selection(self.b, self.plan_raw, "forest-r2/foreign/max/2020-quicksort/seed-23")

    def test_modified_plan_even_equivalent_bytes_refused(self):
        with self.assertRaisesRegex(ValueError, "Exact registered"):
            ext.registered_selection(self.b, self.plan_raw + b"\n", ext.FIRST_CELL)

    def test_template_without_real_gate_remains_closed(self):
        config = ext.build_cell_input(self.b, self.plan_raw, ext.FIRST_CELL, None)
        self.assertFalse(config["automatic_extension"])
        self.assertFalse(config["native_execution_authorized_by_this_input"])
        with self.assertRaisesRegex(ValueError, "gate absent"):
            ext.validate_input(self.b, config, self.plan_raw)

    def test_bound_input_cannot_change_identity_paths_or_limits(self):
        config = ext.build_cell_input(self.b, self.plan_raw, ext.FIRST_CELL, {"path": "NEUTRAL", "sha256": "a" * 64, "bytes": 1})
        ext.validate_input(self.b, config, self.plan_raw)
        for key, value in (("scientific_root", ext.FIRST_ROOT + "-wrong"), ("admission_root", ext.FIRST_ROOT),
                           ("shared_root", ext.SHARED + "-other"), ("maximum_admission_seconds", 601),
                           ("maximum_runner_seconds", 3300), ("scientific_wall_seconds", 1801),
                           ("automatic_extension", True), ("common_archive", {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                ext.validate_input(self.b, {**config, key: value}, self.plan_raw)
        changed = copy.deepcopy(config)
        changed["binding_without_job_id"]["session_id"] = "f" * 32
        with self.assertRaises(ValueError):
            ext.validate_input(self.b, changed, self.plan_raw)

    def test_sealed_helper_tamper_refused_before_import(self):
        path = self.path / "bad-helper.py"
        path.write_bytes(b"raise Exception('MUST NOT EXECUTE')")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            ext.load_helper(path)

    def test_neutral_actual_native_release_validator_positive(self):
        gate, *_rest = self.fixture()
        result = self.validate(gate)
        self.assertEqual(result["first_binding"]["job_id"], "755999")
        first = native.read_json(self.resolver(gate["first_start_receipt"]))
        self.assertEqual(first["first_real_evaluation"]["status"], "incorrect")

    def test_resolver_context_restored_on_success_and_failure(self):
        original_native, original_batch = native.artifact, batch.artifact
        gate, *_rest = self.fixture()
        self.validate(gate)
        self.assertIs(native.artifact, original_native)
        self.assertIs(batch.artifact, original_batch)
        gate["release"]["sha256"] = "0" * 64
        with self.assertRaises(KeyError):
            self.validate(gate)
        self.assertIs(native.artifact, original_native)
        self.assertIs(batch.artifact, original_batch)

    def test_prepared_foreign_plan_source_session_and_nontrue_verified_refused(self):
        original, *_rest = self.fixture()
        for key, value in (("evidence_origin", "prepared"), ("verified", 1), ("source_zip_sha256", "f" * 64),
                           ("plan_sha256", "f" * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate({**original, key: value})
        changed = copy.deepcopy(original)
        changed["first_binding"]["session_id"] = "f" * 32
        with self.assertRaisesRegex(ValueError, "Original Luna"):
            self.validate(changed)

    def test_missing_or_tampered_reference_never_becomes_proof(self):
        gate, *_rest = self.fixture()
        path = self.resolver(gate["engine_release_receipt"])
        path.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.validate(gate)

    def test_true_engine_consumption_not_only_proposed_release(self):
        original, _review, accepted, _release = self.fixture()
        for key, value in (("verified", False), ("budget_or_chronology_reset", True), ("replayed_claims", 1),
                           ("private_review_receipt_sha256", "f" * 64)):
            gate = copy.deepcopy(original)
            changed = {**accepted, key: value}
            gate["engine_release_receipt"] = self.write(original["engine_release_receipt"]["path"], changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Actual native engine"):
                self.validate(gate)

    def test_root_review_cannot_waive_received_release_or_admit_automatic_extension(self):
        original, review, *_rest = self.fixture()
        for key, value in (("evidence_origin", "prepared"), ("all_private_raws_received_and_hashed", False),
                           ("actual_arm_release_received", False), ("automatic_extension", True),
                           ("release_sha256", "f" * 64), ("reviewed_at", float("inf")),
                           ("root_review_instruction", "")):
            gate = copy.deepcopy(original)
            # JSON finite guard itself refuses inf; all other changes reach semantic validation.
            if key == "reviewed_at":
                with self.assertRaises(ValueError):
                    self.write(original["root_reception_review"]["path"], {**review, key: value})
                continue
            gate["root_reception_review"] = self.write(original["root_reception_review"]["path"], {**review, key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Explicit reviewed"):
                self.validate(gate)

    def test_source_validator_rejects_budget_change_even_with_rehashed_release(self):
        gate, _review, _accepted, release = self.fixture()
        gate["release"] = self.write(gate["release"]["path"], {**release, "new_model_or_budget_authorized": True})
        with self.assertRaisesRegex(InfrastructureError, "checkpoint"):
            self.validate(gate)

    def test_proposal_receipt_is_rehashed_and_references_actual_release(self):
        original, *_rest = self.fixture()
        raw = native.read_json(self.resolver(original["proposal_receipt"]))
        for key, value in (("private_audit", {**raw["private_audit"], "sha256": "0" * 64}),
                           ("projection", {**raw["projection"], "sha256": "0" * 64}),
                           ("proposed_release", {**raw["proposed_release"], "sha256": "0" * 64}),
                           ("source127_validate_first_batch_release_passed", False)):
            gate = copy.deepcopy(original)
            gate["proposal_receipt"] = self.write(original["proposal_receipt"]["path"], {**raw, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(gate)

    def test_exact_shared_inventory_checks_existing_files_without_writing(self):
        manifest_path = ROOT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2/SHARED-FILES-MANIFEST.json"
        manifest = self.b.read_json(manifest_path.read_bytes())
        with patch.object(ext, "SHARED", str(SHARED_LOCAL)):
            plan_raw, _source, _runtime = ext.verify_immutable_shared(self.b, SHARED_LOCAL, manifest)
            self.assertEqual(plan_raw, self.plan_raw)
            changed = copy.deepcopy(manifest)
            changed["files"]["plan-60-v2.json"]["sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "never repair"):
                ext.verify_immutable_shared(self.b, SHARED_LOCAL, changed)

    def test_preparer_is_closed_default_even_with_isolated_python(self):
        output = self.path / "prepared"
        argv = [sys.executable, "-I", "-B", str(Path(__file__).with_name("prepare_extension.py")),
                "--plan", str(SHARED_LOCAL / "plan-60-v2.json"), "--output", str(output)]
        process = subprocess.run(argv, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        receipt = json.loads((output / "PREPARATION.json").read_text())
        self.assertFalse(receipt["verified"])
        self.assertFalse(receipt["operational_files_emitted"])
        self.assertFalse(receipt["first_batch_actually_received_and_released"])
        self.assertEqual(len(receipt["registered_cells"]), 60)
        self.assertEqual({path.name for path in output.iterdir()}, {"PREPARATION.json", "INPUT-TEMPLATE-PREPARED.json"})

    def test_preparer_has_no_operational_emission_switch(self):
        output = self.path / "must-remain-absent"
        argv = [sys.executable, "-I", "-B", str(Path(__file__).with_name("prepare_extension.py")),
                "--plan", str(SHARED_LOCAL / "plan-60-v2.json"), "--output", str(output), "--produce-for-root-review"]
        process = subprocess.run(argv, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 2)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
