"""Neutral local checks only: never invoke Slurm, ARM native code or a model."""
from __future__ import annotations

import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bootstrap_native as boot
import prepare_bootstrap as prep


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def tar(self, members, *, format_=tarfile.USTAR_FORMAT):
        path = self.root / ("archive-" + str(len(list(self.root.iterdir()))) + ".tar.gz")
        with tarfile.open(path, "w:gz", format=format_) as archive:
            for name, raw, kind, pax in members:
                info = tarfile.TarInfo(name)
                info.size, info.type, info.pax_headers = len(raw), kind, pax
                if kind == tarfile.SYMTYPE:
                    info.linkname = "other"
                archive.addfile(info, io.BytesIO(raw) if info.isfile() else None)
        return path

    def manifest(self, material):
        return {"schema": "hpc-forest-matrix15-shared-files-v1",
                "files": {name: {"sha256": boot.sha(raw), "bytes": len(raw)} for name, raw in material.items()}}

    def config(self):
        binding = {"scope_id": boot.SCOPE, "cell_key": boot.CELL_KEY, "subject_id": "2020-quicksort",
                   "model": "gpt-6-luna", "effort": "max", "session_id": boot.SESSION,
                   "remote_root": boot.SCIENTIFIC_ROOT, "source_zip_sha256": boot.SOURCE_SHA256,
                   "plan_sha256": "a" * 64, "preparation_manifest_sha256": "b" * 64,
                   "r1_contract_sha256": "c" * 64}
        return {"schema": "hpc-forest-matrix15-bootstrap-input-v1", "evidence_origin": "operator-prepared",
                "native_execution_authorized_by_this_input": False, "shared_root": boot.SHARED_ROOT,
                "scientific_root": boot.SCIENTIFIC_ROOT, "admission_root": boot.SCIENTIFIC_ROOT + "-admission",
                "python": boot.PYTHON, "shared_archive": {}, "shared_files_manifest": {},
                "binding_without_job_id": binding, "source_zip_relative": "native-source.zip",
                "runtime_manifest_relative": "runtime-manifest.json", "plan_relative": "plan-60-v2.json",
                "maximum_admission_seconds": 600, "maximum_runner_seconds": 2700,
                "scientific_wall_seconds": 1800, "confirmation_seconds": 120, "collection_reserve_seconds": 180}

    def env(self):
        return {"SLURM_JOB_ID": "755999", "SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
                "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}

    def test_safe_archive_and_exclusive_extraction(self):
        material = {"project/a.py": b"zero models\n", "plan.json": b"{}"}
        path = self.tar([(name, raw, tarfile.REGTYPE, {}) for name, raw in material.items()])
        manifest = self.manifest(material)
        received = boot.read_archive(path, manifest)
        target = self.root / "new"
        boot.extract_shared(target, received, manifest["files"])
        self.assertEqual(boot.inventory(target), manifest["files"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            boot.extract_shared(target, received, manifest["files"])
        self.assertEqual((target / "project/a.py").read_bytes(), b"zero models\n")

    def test_unsafe_archive_paths(self):
        for name in ("../escape", "/absolute", "a/../b", "a\\b", "a:b", "a//b", ".git/config", "a/./b", "a\x00b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                boot.canonical_member(name)

    def test_unknown_member_and_tampering(self):
        path = self.tar([("known", b"changed", tarfile.REGTYPE, {})])
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            boot.read_archive(path, self.manifest({"known": b"original"}))
        with self.assertRaisesRegex(ValueError, "Unknown"):
            boot.read_archive(path, self.manifest({"other": b"changed"}))

    def test_links_directories_duplicate_and_casefold_refused(self):
        cases = [[("link", b"", tarfile.SYMTYPE, {})], [("dir", b"", tarfile.DIRTYPE, {})],
                 [("a", b"1", tarfile.REGTYPE, {}), ("a", b"1", tarfile.REGTYPE, {})],
                 [("a", b"1", tarfile.REGTYPE, {}), ("A", b"1", tarfile.REGTYPE, {})]]
        for members in cases:
            material = {name: raw for name, raw, *_ in members}
            with self.subTest(members=members), self.assertRaises(ValueError):
                boot.read_archive(self.tar(members), self.manifest(material))

    def test_pax_refused(self):
        path = self.tar([("a", b"1", tarfile.REGTYPE, {"comment": "unexpected"})], format_=tarfile.PAX_FORMAT)
        with self.assertRaisesRegex(ValueError, "regular"):
            boot.read_archive(path, self.manifest({"a": b"1"}))

    def test_manifest_self_reference_and_missing_member_refused(self):
        path = self.tar([("a", b"1", tarfile.REGTYPE, {})])
        with self.assertRaisesRegex(ValueError, "itself"):
            boot.read_archive(path, self.manifest({"SHARED-FILES-MANIFEST.json": b"1"}))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            boot.read_archive(path, self.manifest({"a": b"1", "b": b"2"}))

    def test_bounded_file_reference(self):
        path = self.root / "value"
        path.write_bytes(b"value")
        ref = {"path": str(path), "sha256": boot.sha(b"value"), "bytes": 5}
        self.assertEqual(boot.read_ref(ref), b"value")
        for field, value in (("sha256", "f" * 64), ("bytes", 6), ("bytes", True)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                boot.read_ref({**ref, field: value})

    def test_json_duplicate_and_nonfinite_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                boot.read_json(raw)

    def test_config_exact_bounds_identity_and_prepared_only(self):
        config = self.config()
        self.assertIs(boot.validate_input(config), config)
        for key, value in (("scientific_wall_seconds", 1801), ("maximum_admission_seconds", 601),
                           ("maximum_runner_seconds", 2701), ("native_execution_authorized_by_this_input", True),
                           ("python", "/usr/bin/python"), ("plan_relative", "other.json")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                boot.validate_input({**config, key: value})
        changed = {**config, "binding_without_job_id": {**config["binding_without_job_id"], "model": "gpt-6-astra"}}
        with self.assertRaisesRegex(ValueError, "binding changed"):
            boot.validate_input(changed)

    def test_actual_arm_allocation_and_restart_guards(self):
        kwargs = {"env": self.env(), "system": "Linux", "machine": "aarch64", "affinity": [1, 2, 3, 4], "now": 1792400000}
        actual = boot.allocation_guard(**kwargs)
        self.assertEqual(actual["affinity_cpu_count"], 4)
        for key, value in (("SLURM_RESTART_COUNT", "1"), ("SLURM_GPUS", "1"), ("SLURM_CPUS_PER_TASK", "8")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                boot.allocation_guard(**{**kwargs, "env": {**self.env(), key: value}})
        for key, value in (("machine", "x86_64"), ("affinity", [1, 2, 3]), ("now", boot.DEADLINE - 14400)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                boot.allocation_guard(**{**kwargs, key: value})

    def write_commit(self, raw=b'{"authorization":"NEUTRAL"}\n'):
        path = self.root / "authorization.json"
        path.write_bytes(raw)
        boot.save(self.root / "authorization.sha256.json", {"authorization": str(path), "sha256": boot.sha(raw), "bytes": len(raw)})
        return path

    def test_auth_commit_and_tampering(self):
        path = self.write_commit()
        self.assertEqual(boot.read_authorization_commit(self.root)[0], path)
        path.write_bytes(b"replaced")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            boot.read_authorization_commit(self.root)

    def test_wait_uses_original_clock_and_never_restarts(self):
        ticks = iter([500.0, 599.0, 600.0])
        waits = []
        with self.assertRaisesRegex(ValueError, "Original600s"):
            boot.wait_for_authorization(self.root, 0.0, monotonic=lambda: next(ticks), sleep=waits.append)
        self.assertEqual(waits, [2.0, 1.0])

    def test_commit_received_after_expiry_refused(self):
        self.write_commit()
        with self.assertRaisesRegex(ValueError, "Original600s"):
            boot.wait_for_authorization(self.root, 0.0, monotonic=lambda: 600.0, sleep=lambda _: self.fail("must not sleep"))

    def test_valid_commit_is_read_without_native_execution(self):
        path = self.write_commit()
        self.assertEqual(boot.wait_for_authorization(self.root, 5.0, monotonic=lambda: 12.0)[0], path)

    def test_marker_observes_absence_and_original_clock(self):
        binding = {**self.config()["binding_without_job_id"], "job_id": "755999", "remote_root": str(self.root / "scientific")}
        value = boot.marker(binding, {"job_id": "755999"}, str(self.root / "admission"), 1000, 4600, now=1010)
        self.assertEqual(value["admission_deadline"], 1600)
        self.assertEqual(value["execution_deadline"], 4300)
        self.assertTrue(value["scientific_mailbox_observed_absent"])
        self.assertFalse((self.root / "scientific").exists())
        (self.root / "scientific").mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            boot.marker(binding, {}, str(self.root / "admission"), 1000, 4600, now=1010)

    def test_actual_scheduler_epoch_saved(self):
        env = {**self.env(), "SLURM_JOB_END_TIME": "4000"}
        self.assertEqual(boot.allocation_outer_deadline({"job_id": "755999"}, self.root, env=env, now=1000), 4000)
        proof = json.loads((self.root / "scheduler-deadline-observation.json").read_text())
        self.assertEqual(proof["origin"], "SLURM_JOB_END_TIME")

    def test_scheduler_text_exact_job_limit_offset_and_dates(self):
        now = 1792400400.0
        from datetime import datetime, timedelta, timezone
        zone = timezone(timedelta(hours=2))
        start = datetime.fromtimestamp(now - 60, zone).replace(tzinfo=None).isoformat(timespec="seconds")
        end = datetime.fromtimestamp(now + 3540, zone).replace(tzinfo=None).isoformat(timespec="seconds")
        raw = f"JobId=755999 StartTime={start} EndTime={end} TimeLimit=01:00:00"
        self.assertEqual(boot.parse_scontrol_deadline(raw, "+0200", "755999", now), now + 3540)
        for other in (raw.replace("755999", "755998"), raw.replace("01:00:00", "00:55:00"), raw + " EndTime=Unknown"):
            with self.subTest(raw=other), self.assertRaises(ValueError):
                boot.parse_scontrol_deadline(other, "+0200", "755999", now)
        with self.assertRaises(ValueError):
            boot.parse_scontrol_deadline(raw, "unknown", "755999", now)

    def test_argv_and_shell_preserve_max_science_and_no_once(self):
        argv = boot.runner_argv(self.config(), Path("authorization.json"))
        self.assertIn("-B", argv)
        self.assertNotIn("-I", argv)
        self.assertNotIn("--once", argv)
        body = prep.shell_body("a" * 64, {"bootstrap_native.py": {"sha256": "b" * 64}})
        self.assertIn("--cpus-per-task=4", body)
        self.assertIn("3310s", body)
        self.assertIn("OMP_DYNAMIC=FALSE", body)
        self.assertIn("-I -B", body)
        self.assertNotIn("--once", body)

    def test_runtime_tamper_and_extra_file_refused_without_import(self):
        shared = self.root / "shared"
        project = shared / "project"
        project.mkdir(parents=True)
        runtime = {}
        for index in range(127):
            name = f"file{index}.py"
            raw = ("NEUTRAL NEVER EXECUTE " + str(index)).encode()
            (project / name).write_bytes(raw)
            runtime[name] = boot.sha(raw)
        source_raw, plan_raw, runtime_raw = b"NEUTRAL ZIP PIN", b"{}", boot.encode(runtime)
        (shared / "native-source.zip").write_bytes(source_raw)
        (shared / "runtime-manifest.json").write_bytes(runtime_raw)
        (shared / "plan-60-v2.json").write_bytes(plan_raw)
        config = self.config()
        config["binding_without_job_id"]["plan_sha256"] = boot.sha(plan_raw)
        with patch.object(boot, "SOURCE_SHA256", boot.sha(source_raw)), patch.object(boot, "RUNTIME_MANIFEST_SHA256", boot.sha(runtime_raw)):
            boot.verify_sources(shared, config)
            (project / "file1.py").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                boot.verify_sources(shared, config)
            (project / "file1.py").write_bytes(b"NEUTRAL NEVER EXECUTE 1")
            (project / "extra.py").write_bytes(b"must not import")
            with self.assertRaisesRegex(ValueError, "inventory differs"):
                boot.verify_sources(shared, config)

    def test_timeout_only_signals_new_owned_process_group_once(self):
        class Process:
            pid = 24680

            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def wait(self, timeout=None):
                self.calls.append(timeout)
                if len(self.calls) <= 2:
                    raise subprocess.TimeoutExpired(["NEUTRAL"], timeout)
                return -9

        process = Process()
        # create=True keeps this portable on Windows; the production guard requires ARM Linux.
        with patch.object(boot.subprocess, "Popen", return_value=process) as popen, \
                patch.object(boot.os, "killpg", create=True) as killpg, \
                patch.object(boot.signal, "SIGKILL", 9, create=True):
            with self.assertRaises(subprocess.TimeoutExpired):
                boot.run_native(["NEUTRAL"], {}, None, None, 2400)
            self.assertEqual(popen.call_count, 1)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            self.assertEqual(process.calls, [2400, 10, None])
            self.assertEqual([call.args[0] for call in killpg.call_args_list], [24680, 24680])
        for seconds in (0, 2701, float("inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                boot.run_native(["NEUTRAL"], {}, None, None, seconds)


if __name__ == "__main__":
    unittest.main()
