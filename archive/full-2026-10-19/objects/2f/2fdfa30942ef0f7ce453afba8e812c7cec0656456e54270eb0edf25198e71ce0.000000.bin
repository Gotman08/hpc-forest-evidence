"""Neutral Q15 policy/source tests only; no compiler, runtime, Q, model or job."""
from __future__ import annotations

import ast
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare as p
import qualification_contract as q
import qualify15 as runner


def policy():
    return runner.policy_for(q.SUBJECTS[0], "999", "/NEUTRAL/Q15", "1" * 64, "2" * 64,
                             "3" * 64, q.PREP_SHA)


class QualificationPolicyTests(unittest.TestCase):
    def test_qualification_binding_is_explicit_and_has_no_native_cell_fields(self):
        value = policy()
        actual = q.qualification_command_stream_policy({"execution_provenance": value, "protocol": {}})
        self.assertEqual(actual, value)
        self.assertIsNot(actual, value)
        self.assertIs(actual["qualification_binding"]["native_authorization"], False)
        self.assertTrue(set(actual["qualification_binding"]).isdisjoint({"model", "effort", "session_id", "cell_key"}))
        self.assertIsNone(q.qualification_command_stream_policy({"protocol": {}}))

    def test_native_binding_false_authorization_seed_subject_and_hash_mutants_refused(self):
        for mutation in ("native", "authorization", "seed", "subject", "job", "scope", "hash", "case_v2"):
            with self.subTest(mutation=mutation):
                value = policy()
                protocol = {}
                if mutation == "native":
                    value["cell_binding"] = value.pop("qualification_binding")
                elif mutation == "authorization":
                    value["qualification_binding"]["native_authorization"] = True
                elif mutation == "seed":
                    value["qualification_binding"]["seed"] = True
                elif mutation == "subject":
                    value["qualification_binding"]["subject_id"] = "2020-primes"
                elif mutation == "job":
                    value["qualification_binding"]["job_id"] = "0"
                elif mutation == "scope":
                    value["qualification_binding"]["scope_id"] = "hpc-forest-matrix15-native-max-r2"
                elif mutation == "hash":
                    value["qualification_binding"]["prepared_manifest_sha256"] = "0" * 64
                else:
                    protocol["private_execution_audit"] = True
                with self.assertRaises(q.Refusal):
                    q.qualification_command_stream_policy({"execution_provenance": value, "protocol": protocol})

    def test_scientific_settings_are_retained_and_inactive_model_metadata_is_cleared(self):
        original = {"problem": q.SUBJECTS[0], "seed": 23, "backend": "codex",
            "protocol": {"confirmation_repetitions": 5, "environment": {"OMP_NUM_THREADS": "4"}},
            "harness": {"enabled": True, "NEUTRAL": True}, "budget": {"NEUTRAL": 1},
            "codex": {"transport": "codex-mailbox", "model": "NEUTRAL-OLD", "session_id": "NEUTRAL-OLD"},
            "compiler": {"path": "NEUTRAL-OLD"}, "target_id": "NEUTRAL-OLD"}
        before = copy.deepcopy(original)
        actual = runner.qualification_settings(original, policy(), "NEUTRAL-Q-TARGET")
        self.assertEqual(original, before)
        for name in ("problem", "seed", "backend", "protocol", "harness", "budget"):
            self.assertEqual(actual[name], original[name])
        self.assertEqual(actual["codex"], {"transport": "codex-mailbox", "model": None})
        self.assertNotIn("compiler", actual)


class SourceDerivativeTests(unittest.TestCase):
    def test_only_guard_and_two_schema_names_change_in_neutral_observer(self):
        raw = (b'CONTEXT_SCHEMA = "NEUTRAL-OLD-CONTEXT"\nEXECUTION_SCHEMA = "NEUTRAL-OLD-EXECUTION"\n'
               b'def command_stream_policy(config):\n    return None\n'
               b'def observe_command(value):\n    return ("NEUTRAL TIMER UNCHANGED", value)\n')
        changed, receipt = p.qualifier_observer(raw)
        self.assertTrue(receipt["other_function_source_unchanged"])
        self.assertIs(receipt["native_authorization"], False)
        text = changed.decode()
        self.assertIn('return ("NEUTRAL TIMER UNCHANGED", value)', text)
        self.assertIn("qualification_command_stream_policy", text)
        self.assertIn("qualification-command-context-v1", text)
        self.assertEqual(len([node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)]), 2)

    def test_unknown_observer_shape_or_unsafe_preparation_prefix_refused(self):
        with self.assertRaises(q.Refusal):
            p.qualifier_observer(b"def only_other_function():\n    return None\n")
        for remote in ("/NEUTRAL/no-preparation", "/NEUTRAL/preparation/../escape", "/preparation/a/preparation/b"):
            with self.subTest(remote=remote), self.assertRaises(q.Refusal):
                p.prepared_prefix(remote)
        self.assertEqual(p.prepared_prefix("/NEUTRAL/prepared/preparation/subject/frozen/source"),
                         "preparation/subject/frozen/source")

    def test_runner_never_instantiates_controller_mother_backend_or_worker(self):
        source = Path(runner.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        names = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertTrue({"create_workspace", "Registry", "Evaluator"} <= names)
        self.assertTrue(names.isdisjoint({"Controller", "Mother", "MotherContext", "CodexBackend", "OllamaBackend",
                                         "install_identity", "initialize_channel", "verify_worker"}))

    def test_source_packaging_skips_caches_without_deleting_or_importing_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "neutral.py").write_bytes(b"# NEUTRAL NEVER IMPORTED")
            (root / "__pycache__").mkdir()
            cache = root / "__pycache__/neutral.pyc"
            cache.write_bytes(b"NEUTRAL CACHE NEVER EXECUTED")
            self.assertEqual(p.source_files(root), {"neutral.py": b"# NEUTRAL NEVER IMPORTED"})
            self.assertTrue(cache.exists())

    def test_case_count_uses_real_fingerprint_capture_pairs(self):
        rows = [{"input_fingerprint": "a", "capture_files": []}, {"input_fingerprint": "a", "capture_files": []},
                {"input_fingerprint": "b", "capture_files": []}]
        self.assertEqual(len(p.case_keys(rows)), 2)


class AllocationGuardTests(unittest.TestCase):
    def guard(self, **kwargs):
        env = {"SLURM_JOB_ID": "999", "SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
               "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}
        env.update(kwargs.pop("env", {}))
        return q.allocation_guard(600, env=env, system=kwargs.pop("system", "Linux"),
            machine=kwargs.pop("machine", "aarch64"), affinity=kwargs.pop("affinity", [0, 1, 2, 3]),
            now=kwargs.pop("now", q.DEADLINE - 20000), **kwargs)

    def test_allocated_resources_are_exact_without_file_effects(self):
        actual = self.guard()
        self.assertEqual(actual["job_id"], "999")
        self.assertEqual(actual["gpus"], 0)
        self.assertEqual(actual["affinity_cpu_ids"], [0, 1, 2, 3])

    def test_wrong_architecture_resources_restart_gpu_or_deadline_refused(self):
        for kwargs in ({"system": "Windows"}, {"machine": "x86_64"}, {"affinity": [0, 1, 2]},
                       {"env": {"SLURM_CPUS_PER_TASK": "8"}}, {"env": {"SLURM_MEM_PER_NODE": "8192"}},
                       {"env": {"SLURM_RESTART_COUNT": "1"}}, {"env": {"SLURM_GPUS": "1"}},
                       {"now": q.DEADLINE - 600 - 120 - 10800}):
            with self.subTest(kwargs=kwargs), self.assertRaises(q.Refusal):
                self.guard(**kwargs)

    def test_nonallocated_run_refuses_before_package_or_runtime_reads(self):
        before = set(sys.modules)
        with patch.object(runner, "allocation_guard", side_effect=q.Refusal("NEUTRAL NO ALLOCATION")):
            with self.assertRaisesRegex(q.Refusal, "NO ALLOCATION"):
                runner.run({"path": "NEUTRAL NEVER READ", "sha256": "0" * 64},
                           Path("NEUTRAL NEVER READ"), Path("NEUTRAL NEVER CREATED"), 600)
        self.assertFalse(any(name == "hpc_forest" or name.startswith("hpc_forest.") for name in set(sys.modules) - before))


if __name__ == "__main__":
    unittest.main()
