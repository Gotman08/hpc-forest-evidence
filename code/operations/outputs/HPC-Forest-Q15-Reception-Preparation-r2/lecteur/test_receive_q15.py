"""Offline adversarial tests of the local Q15 cold-reception reader.

All generated payloads are explicitly NEUTRAL fixtures, never scientific evidence.
These tests neither run received source nor contact an external service.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import receive_q15 as reader


NEUTRAL_MARKER = b'{"evidence_origin":"NEUTRAL_FIXTURE","purpose":"reader_test_only"}\n'
HERE = Path(__file__).resolve().parent


def neutral_tar(entries, *, format=tarfile.USTAR_FORMAT):
    """Build an archive in memory from (name, payload, type, attributes) tuples."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=format) as archive:
        for name, payload, kind, attributes in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(payload) if kind == tarfile.REGTYPE else 0
            for key, value in attributes.items():
                setattr(member, key, value)
            archive.addfile(member, io.BytesIO(payload) if kind == tarfile.REGTYPE else None)
    return stream.getvalue()


def regular(name="NEUTRAL/marker.json", payload=NEUTRAL_MARKER, **attributes):
    return name, payload, tarfile.REGTYPE, attributes


def neutral_transfer_wrapper():
    """A NEUTRAL-only MCP transfer observation, unrelated to any real job."""
    checksum = hashlib.sha256(NEUTRAL_MARKER).hexdigest()
    return {
        "isError": False,
        "structuredContent": {
            "ok": True,
            "verifie": True,
            "downloaded": "/NEUTRAL/data.tar",
            "to": "NEUTRAL/data.tar",
            "bytes": len(NEUTRAL_MARKER),
            "remote_sha256": checksum,
            "empreinte_locale": checksum,
            "empreinte_distante": checksum,
        },
    }


NEUTRAL_JOB_ID = "123456789"


def neutral_scheduler_wrappers():
    """Synthetic shape fixtures only; never evidence of an actual Slurm job."""
    common = {"ok": True, "job_id": NEUTRAL_JOB_ID, "state": "COMPLETED", "exit_code": "0:0"}
    status = {
        "isError": False,
        "structuredContent": {
            **common,
            "finished": True,
            "scheduler_completed": True,
            "scheduler_success_observed": True,
            "observation": {"source": "slurm", "current_state_observed": True, "observed_at": 1},
        },
    }
    efficiency = {
        "isError": False,
        "structuredContent": {**common, "found": True, "alloc_cpus": 4, "alloc_gpus": 0, "req_mem_mb": 16384},
    }
    return status, efficiency


class StrictJsonTests(unittest.TestCase):
    def test_accepts_neutral_object(self):
        self.assertEqual(reader.parse_json(NEUTRAL_MARKER)["purpose"], "reader_test_only")

    def test_rejects_duplicate_root_key(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":1,"NEUTRAL":2}')

    def test_rejects_duplicate_nested_key(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":{"marker":1,"marker":2}}')

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":NaN}')

    def test_rejects_positive_infinity(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":Infinity}')

    def test_rejects_negative_infinity(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":-Infinity}')

    def test_rejects_positive_numeric_overflow(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":{"nested":[1e999]}}')

    def test_rejects_negative_numeric_overflow(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":-1e999}')

    def test_rejects_root_array(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'[{"NEUTRAL":true}]')

    def test_rejects_root_scalar(self):
        for payload in (b'null', b'1', b'true', b'"NEUTRAL"'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                reader.parse_json(payload)

    def test_rejects_invalid_utf8(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":"\xff"}')

    def test_rejects_trailing_document(self):
        with self.assertRaises(ValueError):
            reader.parse_json(b'{"NEUTRAL":true}{"NEUTRAL":false}')


class SecureTarTests(unittest.TestCase):
    def test_neutral_round_trip_without_prefix(self):
        self.assertEqual(
            reader.safe_tar(neutral_tar([regular()]), None),
            {"NEUTRAL/marker.json": NEUTRAL_MARKER},
        )

    def test_neutral_round_trip_with_prefix(self):
        self.assertEqual(
            reader.safe_tar(neutral_tar([regular()]), "NEUTRAL"),
            {"marker.json": NEUTRAL_MARKER},
        )

    def test_rejects_absolute_name(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("/NEUTRAL/marker.json")]), None)

    def test_rejects_parent_traversal(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL/../marker.json")]), None)

    def test_rejects_current_directory_alias(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL/./marker.json")]), None)

    def test_rejects_windows_drive(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("C:/NEUTRAL/marker.json")]), None)

    def test_rejects_backslash(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL\\marker.json")]), None)

    def test_rejects_empty_path_component(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL//marker.json")]), None)

    def test_rejects_symbolic_link(self):
        attack = ("NEUTRAL/marker.json", b"", tarfile.SYMTYPE, {"linkname": "../outside"})
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([attack]), None)

    def test_rejects_hard_link(self):
        attack = ("NEUTRAL/marker.json", b"", tarfile.LNKTYPE, {"linkname": "NEUTRAL/data"})
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL/data"), attack]), None)

    def test_rejects_fifo(self):
        attack = ("NEUTRAL/fifo", b"", tarfile.FIFOTYPE, {})
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([attack]), None)

    def test_rejects_character_device(self):
        attack = ("NEUTRAL/device", b"", tarfile.CHRTYPE, {"devmajor": 1, "devminor": 3})
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([attack]), None)

    def test_rejects_block_device(self):
        attack = ("NEUTRAL/device", b"", tarfile.BLKTYPE, {"devmajor": 1, "devminor": 3})
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([attack]), None)

    def test_rejects_duplicate_members(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular(), regular(payload=b'NEUTRAL duplicate')]), None)

    def test_rejects_pax_path_override_traversal(self):
        archive = neutral_tar(
            [regular(pax_headers={"path": "../NEUTRAL-outside.json"})],
            format=tarfile.PAX_FORMAT,
        )
        with self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_rejects_pax_link_override(self):
        archive = neutral_tar(
            [regular(pax_headers={"linkpath": "../NEUTRAL-outside.json"})],
            format=tarfile.PAX_FORMAT,
        )
        with self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_rejects_prefix_confusion(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(neutral_tar([regular("NEUTRAL-sibling/marker.json")]), "NEUTRAL")

    def test_rejects_truncated_member(self):
        header = tarfile.TarInfo("NEUTRAL/marker.json")
        header.size = 100000
        archive = gzip.compress(header.tobuf(format=tarfile.USTAR_FORMAT) + b"NEUTRAL")
        with self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_rejects_unbounded_declared_member(self):
        header = tarfile.TarInfo("NEUTRAL/marker.json")
        header.size = 1 << 40
        archive = gzip.compress(header.tobuf(format=tarfile.GNU_FORMAT) + b"NEUTRAL")
        with self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_rejects_non_tar_bytes(self):
        with self.assertRaises(ValueError):
            reader.safe_tar(NEUTRAL_MARKER, None)

    def test_enforces_compressed_archive_bound(self):
        archive = neutral_tar([regular()])
        with patch.object(reader, "MAX_ARCHIVE", len(archive) - 1), self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_enforces_member_size_bound(self):
        archive = neutral_tar([regular()])
        with patch.object(reader, "MAX_MEMBER", len(NEUTRAL_MARKER) - 1), self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_enforces_total_expanded_size_bound(self):
        archive = neutral_tar([regular(), regular("NEUTRAL/second.json")])
        with patch.object(reader, "MAX_TOTAL", 2 * len(NEUTRAL_MARKER) - 1), self.assertRaises(ValueError):
            reader.safe_tar(archive, None)

    def test_enforces_member_count_bound(self):
        archive = neutral_tar([regular(), regular("NEUTRAL/second.json")])
        with patch.object(reader, "MAX_MEMBERS", 1), self.assertRaises(ValueError):
            reader.safe_tar(archive, None)


class ReaderSourceSafetyTests(unittest.TestCase):
    def test_reader_does_not_execute_received_source(self):
        source = Path(reader.__file__).read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=reader.__file__)
        forbidden_imports = {"subprocess", "importlib"}
        forbidden_calls = {"exec", "eval", "__import__"}
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.name.split(".")[0] in forbidden_imports:
                        violations.append((node.lineno, "import " + name.name))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in forbidden_imports:
                    violations.append((node.lineno, "from " + (node.module or "")))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    violations.append((node.lineno, node.func.id))
                elif isinstance(node.func, ast.Attribute) and node.func.attr in {"exec", "eval", "system", "popen"}:
                    violations.append((node.lineno, node.func.attr))
        self.assertEqual(violations, [], f"Unsafe execution surface: {violations}")


class ReceptionOriginTests(unittest.TestCase):
    def test_production_rejects_neutral_fixture_even_with_matching_digest(self):
        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-", dir=HERE) as directory:
            path = Path(directory) / "NEUTRAL-input.json"
            config = {key: None for key in reader.INPUT_KEYS}
            config.update(schema=reader.INPUT_SCHEMA, evidence_origin="NEUTRAL")
            payload = json.dumps(config, sort_keys=True).encode()
            path.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, "cannot be promoted"):
                reader.receive(path, hashlib.sha256(payload).hexdigest())

    def test_input_digest_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-", dir=HERE) as directory:
            path = Path(directory) / "NEUTRAL-input.json"
            path.write_bytes(NEUTRAL_MARKER)
            with self.assertRaises(ValueError):
                reader.receive(path, "0" * 64, neutral_fixture=True)


class InvalidProofShapeTests(unittest.TestCase):
    def test_transfer_rejects_absent_wrapper(self):
        with self.assertRaises(ValueError):
            reader.validate_transfer(None, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER)

    def test_transfer_rejects_array_wrapper(self):
        with self.assertRaises(ValueError):
            reader.validate_transfer([], "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER)

    def test_transfer_rejects_empty_wrapper(self):
        with self.assertRaises(ValueError):
            reader.validate_transfer({}, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER)

    def test_transfer_rejects_mcp_error(self):
        wrapper = {"isError": True, "content": [{"type": "text", "text": "NEUTRAL fixture error"}]}
        with self.assertRaises(ValueError):
            reader.validate_transfer(wrapper, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER)

    def test_transfer_rejects_non_text_mcp_content(self):
        wrapper = {"isError": False, "content": [{"type": "image", "mimeType": "image/png", "data": "TkVVVFJBTA=="}]}
        with self.assertRaises(ValueError):
            reader.validate_transfer(wrapper, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER)

    def test_scheduler_rejects_absent_status(self):
        with self.assertRaises(ValueError):
            reader.validate_scheduler(None, {}, NEUTRAL_JOB_ID)

    def test_scheduler_rejects_absent_efficiency(self):
        with self.assertRaises(ValueError):
            reader.validate_scheduler({}, None, NEUTRAL_JOB_ID)

    def test_scheduler_rejects_empty_proofs(self):
        with self.assertRaises(ValueError):
            reader.validate_scheduler({}, {}, NEUTRAL_JOB_ID)


class TransferProofTests(unittest.TestCase):
    def test_accepts_neutral_transfer_shape(self):
        wrapper = neutral_transfer_wrapper()
        self.assertEqual(
            reader.validate_transfer(wrapper, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", NEUTRAL_MARKER),
            wrapper["structuredContent"],
        )

    def assert_transfer_rejected(self, wrapper, raw=NEUTRAL_MARKER):
        with self.assertRaises(ValueError):
            reader.validate_transfer(wrapper, "/NEUTRAL/data.tar", "NEUTRAL/data.tar", raw)

    def test_rejects_mcp_success_flag_integer(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["isError"] = 0
        self.assert_transfer_rejected(wrapper)

    def test_rejects_operation_not_ok(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["ok"] = False
        self.assert_transfer_rejected(wrapper)

    def test_rejects_embedded_error_despite_success_flags(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["error"] = "NEUTRAL error"
        self.assert_transfer_rejected(wrapper)

    def test_rejects_structured_content_error_despite_success_flags(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["isError"] = True
        self.assert_transfer_rejected(wrapper)

    def test_rejects_missing_transfer_verification(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["verifie"] = False
        self.assert_transfer_rejected(wrapper)

    def test_rejects_wrong_remote_identity(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["downloaded"] = "/NEUTRAL/wrong.tar"
        self.assert_transfer_rejected(wrapper)

    def test_rejects_wrong_local_identity(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["to"] = "NEUTRAL/wrong.tar"
        self.assert_transfer_rejected(wrapper)

    def test_rejects_size_mismatch(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["bytes"] += 1
        self.assert_transfer_rejected(wrapper)

    def test_rejects_boolean_size(self):
        wrapper = neutral_transfer_wrapper()
        wrapper["structuredContent"]["bytes"] = True
        self.assert_transfer_rejected(wrapper)

    def test_rejects_each_missing_digest(self):
        for key in ("remote_sha256", "empreinte_locale", "empreinte_distante"):
            with self.subTest(key=key):
                wrapper = neutral_transfer_wrapper()
                del wrapper["structuredContent"][key]
                self.assert_transfer_rejected(wrapper)

    def test_rejects_each_wrong_digest(self):
        for key in ("remote_sha256", "empreinte_locale", "empreinte_distante"):
            with self.subTest(key=key):
                wrapper = neutral_transfer_wrapper()
                wrapper["structuredContent"][key] = "0" * 64
                self.assert_transfer_rejected(wrapper)

    def test_rejects_changed_bytes_with_original_proof(self):
        self.assert_transfer_rejected(neutral_transfer_wrapper(), NEUTRAL_MARKER + b"NEUTRAL mutation")


class SchedulerProofTests(unittest.TestCase):
    def test_accepts_neutral_scheduler_shape(self):
        status, efficiency = neutral_scheduler_wrappers()
        self.assertIsNone(reader.validate_scheduler(status, efficiency, NEUTRAL_JOB_ID))

    def assert_scheduler_rejected(self, status, efficiency, job_id=NEUTRAL_JOB_ID):
        with self.assertRaises(ValueError):
            reader.validate_scheduler(status, efficiency, job_id)

    def test_rejects_nonconcrete_job_identifier(self):
        for job_id in ("NEUTRAL", "0", "01", "-1", "1.0", "1;anything", 123456789, True):
            with self.subTest(job_id=job_id):
                self.assert_scheduler_rejected(*neutral_scheduler_wrappers(), job_id=job_id)

    def test_rejects_wrong_job_in_each_observation(self):
        for position in (0, 1):
            with self.subTest(position=position):
                wrappers = neutral_scheduler_wrappers()
                wrappers[position]["structuredContent"]["job_id"] = "123456790"
                self.assert_scheduler_rejected(*wrappers)

    def test_rejects_nonterminal_or_failed_state(self):
        for state in ("PENDING", "RUNNING", "FAILED", "CANCELLED", "TIMEOUT"):
            for position in (0, 1):
                with self.subTest(state=state, position=position):
                    wrappers = neutral_scheduler_wrappers()
                    wrappers[position]["structuredContent"]["state"] = state
                    self.assert_scheduler_rejected(*wrappers)

    def test_rejects_nonzero_exit_code(self):
        for position in (0, 1):
            with self.subTest(position=position):
                wrappers = neutral_scheduler_wrappers()
                wrappers[position]["structuredContent"]["exit_code"] = "1:0"
                self.assert_scheduler_rejected(*wrappers)

    def test_rejects_missing_success_observation(self):
        for flag in ("finished", "scheduler_completed", "scheduler_success_observed"):
            with self.subTest(flag=flag):
                status, efficiency = neutral_scheduler_wrappers()
                status["structuredContent"][flag] = False
                self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_non_slurm_observation(self):
        status, efficiency = neutral_scheduler_wrappers()
        status["structuredContent"]["observation"]["source"] = "NEUTRAL_claim_only"
        self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_state_not_actually_observed(self):
        status, efficiency = neutral_scheduler_wrappers()
        status["structuredContent"]["observation"]["current_state_observed"] = False
        self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_invalid_observation_timestamp(self):
        for stamp in (0, -1, True, "1", float("nan"), float("inf")):
            with self.subTest(stamp=stamp):
                status, efficiency = neutral_scheduler_wrappers()
                status["structuredContent"]["observation"]["observed_at"] = stamp
                self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_malformed_observation_object(self):
        for observation in (None, [], "NEUTRAL", True):
            with self.subTest(observation=observation):
                status, efficiency = neutral_scheduler_wrappers()
                status["structuredContent"]["observation"] = observation
                self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_efficiency_not_found(self):
        status, efficiency = neutral_scheduler_wrappers()
        efficiency["structuredContent"]["found"] = False
        self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_wrong_cpu_count(self):
        for count in (0, 1, 3, 5, 64, "4", 4.0, True):
            with self.subTest(count=count):
                status, efficiency = neutral_scheduler_wrappers()
                efficiency["structuredContent"]["alloc_cpus"] = count
                self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_gpu_allocation(self):
        for count in (1, "0", 0.0, False):
            with self.subTest(count=count):
                status, efficiency = neutral_scheduler_wrappers()
                efficiency["structuredContent"]["alloc_gpus"] = count
                self.assert_scheduler_rejected(status, efficiency)

    def test_rejects_wrong_memory(self):
        for memory in (0, 8192, 16383, 16385, "16384", True, float("inf")):
            with self.subTest(memory=memory):
                status, efficiency = neutral_scheduler_wrappers()
                efficiency["structuredContent"]["req_mem_mb"] = memory
                self.assert_scheduler_rejected(status, efficiency)


@unittest.skipUnless(os.environ.get("Q15_NEUTRAL_SOURCE_PACKAGE"), "Optional NEUTRAL integration needs explicit read-only source package path")
class NeutralIntegratedReceptionTests(unittest.TestCase):
    def test_rejects_actual_orphans_in_subject_command_log_root(self):
        for suffix in ("orphan.log", "orphan.log.command-stream.json"):
            with self.subTest(member=suffix):
                def transform(files):
                    files["2023-count/logs/" + suffix] = b"NEUTRAL actual orphan command evidence\n"
                self.assert_semantic_mutation_rejected(transform, "Unreferenced/orphan command log or sidecar")
    def assert_no_verified_artifacts(self, destination):
        for path in destination.glob("*.json"):
            with self.subTest(artifact=path.name):
                artifact = json.loads(path.read_bytes())
                self.assertIsNot(artifact.get("verified"), True)
                self.assertIsNot(artifact.get("native_authorization"), True)

    def assert_semantic_mutation_rejected(self, transform, expected_message):
        import neutral_fixture_q15 as fixture

        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-rejection-", dir=HERE) as directory:
            prepared = fixture.build_fixture(directory, os.environ["Q15_NEUTRAL_SOURCE_PACKAGE"])
            fixture.reseal_fixture(prepared, transform)
            config = json.loads(prepared["input_path"].read_bytes())
            archive = prepared["archive_path"].read_bytes()
            announcement_path = Path(config["archive_announcement"]["path"])
            reader.validate_transfer(
                json.loads(Path(config["archive_transfer"]["path"]).read_bytes()),
                fixture.REMOTE_OUTPUT + ".tar.gz", prepared["archive_path"], archive,
            )
            reader.validate_transfer(
                json.loads(Path(config["announcement_transfer"]["path"]).read_bytes()),
                fixture.REMOTE_OUTPUT + "-archive.json", announcement_path, announcement_path.read_bytes(),
            )
            files = reader.safe_tar(archive, "output")
            manifest = json.loads(files["OUTPUT-MANIFEST.json"])
            self.assertEqual(manifest["files"], {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items() if name != "OUTPUT-MANIFEST.json"})
            with self.assertRaisesRegex(ValueError, expected_message):
                reader.receive(prepared["input_path"], prepared["input_sha256"], neutral_fixture=True)
            self.assert_no_verified_artifacts(prepared["reception_directory"])

    def test_rejects_four_confirmation_times_after_coherent_reseal(self):
        import neutral_fixture_q15 as fixture

        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            first = result["subjects"][result["qualified_subjects"][0]]
            first["confirmation"]["times"] = first["confirmation"]["times"][:4]
            files["RESULT-Q15.json"] = fixture.json_bytes(result)

        self.assert_semantic_mutation_rejected(transform, "Five positive finite baseline times required")

    def test_rejects_native_model_call_after_coherent_reseal(self):
        import neutral_fixture_q15 as fixture

        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            result["native_model_calls"] = 1
            files["RESULT-Q15.json"] = fixture.json_bytes(result)

        self.assert_semantic_mutation_rejected(transform, "Q result contains native activity")

    def test_rejects_wrong_qualification_policy_after_coherent_reseal(self):
        import neutral_fixture_q15 as fixture

        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            first = result["subjects"][result["qualified_subjects"][0]]
            first["policy"]["qualification_protocol_sha256"] = "0" * 64
            files["RESULT-Q15.json"] = fixture.json_bytes(result)

        self.assert_semantic_mutation_rejected(transform, "Q subject policy/contract differs")

    def test_rejects_nonzero_db_tokens_even_with_consistent_costs(self):
        import neutral_fixture_q15 as fixture

        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            subject = result["qualified_subjects"][0]
            first = result["subjects"][subject]
            first["costs"].update(tokens_used=1, tokens_reserved=1, exact_tokens_used=1)
            connection = sqlite3.connect(":memory:")
            try:
                connection.deserialize(files[subject + "/registry.sqlite3"])
                connection.execute("UPDATE slots SET tokens_used=1, tokens_reserved=1")
                connection.commit()
                files[subject + "/registry.sqlite3"] = connection.serialize()
            finally:
                connection.close()
            files["RESULT-Q15.json"] = fixture.json_bytes(result)

        self.assert_semantic_mutation_rejected(transform, "Q slots contain nonzero/unknown/model usage")

    def test_rejects_empty_argument_inventories_after_coherent_reseal(self):
        import neutral_fixture_q15 as fixture

        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            subject = result["qualified_subjects"][0]
            summary = result["subjects"][subject]["precheck_command_streams"][0]
            proof_name = PurePosixPath(summary["path"]).relative_to(fixture.REMOTE_OUTPUT).as_posix()
            proof = json.loads(files[proof_name])
            context_name = PurePosixPath(proof["context"]["path"]).relative_to(fixture.REMOTE_OUTPUT).as_posix()
            context = json.loads(files[context_name])
            context["argument_files_before"] = []
            files[context_name] = fixture.json_bytes(context)
            proof["argument_files_before"] = []
            proof["argument_files_after"] = []
            proof["context"] = fixture.reference(proof["context"]["path"], files[context_name])
            files[proof_name] = fixture.json_bytes(proof)
            summary.update(fixture.reference(summary["path"], files[proof_name]))
            files["RESULT-Q15.json"] = fixture.json_bytes(result)

        self.assert_semantic_mutation_rejected(transform, "Incomplete command argument file observation")

    def test_rejects_duplicate_sqlite_metadata_key_after_coherent_reseal(self):
        def transform(files):
            result = json.loads(files["RESULT-Q15.json"])
            subject = result["qualified_subjects"][0]
            connection = sqlite3.connect(":memory:")
            try:
                connection.deserialize(files[subject + "/registry.sqlite3"])
                connection.execute("INSERT INTO metadata VALUES ('qualification_only', 'true')")
                connection.commit()
                files[subject + "/registry.sqlite3"] = connection.serialize()
            finally:
                connection.close()

        self.assert_semantic_mutation_rejected(transform, "Duplicate SQLite metadata key")

    def test_rejects_input_changed_after_first_subject_before_receipt(self):
        import neutral_fixture_q15 as fixture

        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-changing-input-", dir=HERE) as directory:
            prepared = fixture.build_fixture(directory, os.environ["Q15_NEUTRAL_SOURCE_PACKAGE"])
            original = reader.validate_subject
            calls = []

            def validate_then_change_input(*args, **kwargs):
                answer = original(*args, **kwargs)
                calls.append(args[0])
                if len(calls) == 1:
                    raw = prepared["input_path"].read_bytes()
                    prepared["input_path"].write_bytes(raw + b"\n")
                return answer

            with patch.object(reader, "validate_subject", side_effect=validate_then_change_input):
                with self.assertRaisesRegex(ValueError, "Reception INPUT bytes changed while auditing"):
                    reader.receive(prepared["input_path"], prepared["input_sha256"], neutral_fixture=True)
            self.assertEqual(len(calls), 15)
            destination = prepared["reception_directory"]
            self.assert_no_verified_artifacts(destination)
            self.assertFalse((destination / "RECU-LECTEUR-Q15.json").exists())
            self.assertFalse((destination / "AUDIT-Q15-BASELINES.json").exists())
            refusal = json.loads((destination / "REFUS-Q15.json").read_bytes())
            self.assertIs(refusal["verified"], False)

    def test_production_rejects_rewritten_origin_when_neutral_wrappers_remain(self):
        import neutral_fixture_q15 as fixture

        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-promotion-", dir=HERE) as directory:
            prepared = fixture.build_fixture(directory, os.environ["Q15_NEUTRAL_SOURCE_PACKAGE"])
            config = json.loads(prepared["input_path"].read_bytes())
            config["evidence_origin"] = "received"
            raw = fixture.json_bytes(config)
            prepared["input_path"].write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "(?i)neutral|synthetic|fixture"):
                reader.receive(prepared["input_path"], hashlib.sha256(raw).hexdigest())
            self.assert_no_verified_artifacts(prepared["reception_directory"])

    def test_all_fifteen_subjects_stay_unverified_and_cannot_be_promoted(self):
        import neutral_fixture_q15 as fixture

        with tempfile.TemporaryDirectory(prefix="NEUTRAL-q15-integration-", dir=HERE) as directory:
            prepared = fixture.build_fixture(directory, os.environ["Q15_NEUTRAL_SOURCE_PACKAGE"])
            self.assertEqual(prepared["subject_count"], 15)
            self.assertTrue(prepared["NEUTRAL"])
            with self.assertRaisesRegex(ValueError, "cannot be promoted"):
                reader.receive(prepared["input_path"], prepared["input_sha256"])
            audit = reader.receive(prepared["input_path"], prepared["input_sha256"], neutral_fixture=True)
            self.assertIs(audit["verified"], False)
            self.assertIs(audit["NEUTRAL"], True)
            self.assertIs(audit["neutral_fixture_checks_passed"], True)
            self.assertIs(audit["native_authorization"], False)
            self.assertIs(audit["native_research_admitted"], False)
            self.assertIs(audit["scientific_gain_claimed"], False)
            self.assertEqual(audit["received_programs_or_scripts_executed"], 0)
            self.assertEqual(audit["native_model_calls"], 0)
            self.assertEqual(audit["confirmation_samples"], 75)
            self.assertEqual(len(audit["subject_order"]), 15)
            self.assertEqual(audit["restoration_inventory_sha256_before"], audit["restoration_inventory_sha256_after"])
            self.assertIs(audit["source_package_inventory_unchanged"], True)
            destination = prepared["reception_directory"]
            reflogs = list((destination / "restauration-neuve").glob("*/repo/.git/logs/HEAD"))
            self.assertEqual(len(reflogs), 15)
            self.assertTrue(all(b"NEUTRAL" in path.read_bytes() for path in reflogs))
            references = sorted(destination.glob("*-baseline-reference.json"))
            self.assertEqual(len(references), 15)
            for path in references:
                with self.subTest(subject=path.name):
                    reference = json.loads(path.read_bytes())
                    self.assertIs(reference["verified"], False)
                    self.assertIs(reference["NEUTRAL"], True)
                    self.assertIs(reference["native_authorization"], False)
                    self.assertIs(reference["native_research_admitted"], False)
                    self.assertEqual(reference["confirmation_seconds"], fixture.TIMES)
                    self.assertEqual(reference["costs"]["tokens_used"], 0)
            receipt = json.loads((destination / "RECU-LECTEUR-Q15.json").read_bytes())
            self.assertIs(receipt["verified"], False)
            self.assertIs(receipt["NEUTRAL"], True)
            self.assertIs(receipt["native_authorization"], False)
            self.assertEqual(len(receipt["outputs"]), 15)
            self.assertFalse((destination / "REFUS-Q15.json").exists())


class CommandLogNamespaceTests(unittest.TestCase):
    def test_command_root_is_distinct_from_git_reflogs(self):
        self.assertTrue(reader.command_log_member("2023-count/logs/e1/baseline-e1/search/attempt-001/build.log"))
        self.assertTrue(reader.command_log_member("2023-count/logs/orphan.log.command-stream.json"))
        self.assertFalse(reader.command_log_member("2023-count/repo/.git/logs/HEAD"))
        self.assertFalse(reader.command_log_member("2023-count/repo/.git/logs/refs/heads/main"))
        self.assertFalse(reader.command_log_member("2023-count/trusted/logs/placeholder"))
        self.assertFalse(reader.command_log_member("unknown-subject/logs/orphan.log"))


if __name__ == "__main__":
    unittest.main()
