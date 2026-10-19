"""NEUTRAL unit data only; tests never produce admission receipts."""
import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import produce_native as bridge


class JsonTests(unittest.TestCase):
    def test_duplicate_keys(self):
        with self.assertRaisesRegex(bridge.Refusal, "Duplicate"):
            bridge.parse(b'{"a":{"b":1,"b":2}}')

    def test_nonfinite(self):
        for raw in (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(bridge.Refusal):
                bridge.parse(raw)

    def test_boolean_size_is_not_integer(self):
        self.assertFalse(bridge.reference({"path": "NEUTRAL", "sha256": "0" * 64, "bytes": True}, sizes=True))

    def test_extra_reference_fields_rejected(self):
        self.assertFalse(bridge.reference({"path": "NEUTRAL", "sha256": "0" * 64, "other": 1}))

    def test_nonobject(self):
        with self.assertRaises(bridge.Refusal):
            bridge.parse(b'[]')


def neutral_tar(rows):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, kind, raw, pax in rows:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(raw)
            member.pax_headers = pax
            archive.addfile(member, io.BytesIO(raw) if kind == tarfile.REGTYPE else None)
    return stream.getvalue()


class ArchiveTests(unittest.TestCase):
    def test_regular_with_finite_pax_time(self):
        raw = neutral_tar([("NEUTRAL/a", tarfile.REGTYPE, b"a", {"mtime": "12.3"})])
        self.assertEqual(bridge.tar_members(raw, "NEUTRAL"), {"a": b"a"})

    def test_traversal_absolute_and_drive(self):
        for name in ("../x", "/x", "C:/x", "a/../x", "a\\x"):
            with self.subTest(name=name), self.assertRaises(bridge.Refusal):
                bridge.tar_members(neutral_tar([(name, tarfile.REGTYPE, b"a", {})]))

    def test_symlink_and_hardlink(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind), self.assertRaises(bridge.Refusal):
                bridge.tar_members(neutral_tar([("a", kind, b"", {})]))

    def test_duplicate_case_collision(self):
        with self.assertRaises(bridge.Refusal):
            bridge.tar_members(neutral_tar([("a", tarfile.REGTYPE, b"a", {}), ("A", tarfile.REGTYPE, b"b", {})]))

    def test_file_parent_collision(self):
        with self.assertRaises(bridge.Refusal):
            bridge.tar_members(neutral_tar([("a", tarfile.REGTYPE, b"a", {}), ("a/b", tarfile.REGTYPE, b"b", {})]))

    def test_nonfinite_pax(self):
        with self.assertRaises(bridge.Refusal):
            bridge.tar_members(neutral_tar([("a", tarfile.REGTYPE, b"a", {"mtime": "nan"})]))

    def test_unsafe_pax(self):
        with self.assertRaises(bridge.Refusal):
            bridge.tar_members(neutral_tar([("a", tarfile.REGTYPE, b"a", {"linkpath": "x"})]))

    def test_prefix(self):
        with self.assertRaises(bridge.Refusal):
            bridge.tar_members(neutral_tar([("other/a", tarfile.REGTYPE, b"a", {})]), "NEUTRAL")


def neutral_aliases():
    return {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": bridge.NSCOPE,
        "source_zip_sha256": "0" * 64, "preparation_manifest_sha256": "1" * 64,
        "entries": [{"kind": "file", "canonical_path": "C:/NEUTRAL/a", "windows_path": "C:/NEUTRAL/local/a",
                     "arm_path": "/NEUTRAL/a", "sha256": "2" * 64}]}


class AliasTests(unittest.TestCase):
    def test_valid_shape(self):
        value = neutral_aliases()
        self.assertIs(bridge.aliases_valid(value, "0" * 64, "1" * 64), value)

    def test_cross_entry_ambiguity(self):
        value = neutral_aliases()
        value["entries"].append({**value["entries"][0], "canonical_path": "C:/NEUTRAL/b"})
        with self.assertRaisesRegex(bridge.Refusal, "Ambiguous"):
            bridge.aliases_valid(value, "0" * 64, "1" * 64)

    def test_wrong_preparation(self):
        with self.assertRaises(bridge.Refusal):
            bridge.aliases_valid(neutral_aliases(), "0" * 64, "3" * 64)

    def test_alias_digest_mismatch(self):
        with self.assertRaises(bridge.Refusal):
            bridge.file_alias({"path": "/NEUTRAL/a", "sha256": "3" * 64}, neutral_aliases())

    def test_missing_alias(self):
        with self.assertRaises(bridge.Refusal):
            bridge.file_alias({"path": "/NEUTRAL/b", "sha256": "2" * 64}, neutral_aliases())


class FailClosedTests(unittest.TestCase):
    def test_unverified_neutral_and_prepared_audits_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "NEUTRAL-audit.json"
            for mutation in ({"verified": False}, {"NEUTRAL": True}, {"baseline_qualification_only": False}):
                audit = {"schema": "hpc-forest-Q15-baseline-cold-audit-v1", "scope_id": bridge.QSCOPE,
                         "verified": True, "NEUTRAL": False, "neutral_fixture_checks_passed": False,
                         "baseline_qualification_only": True, **mutation}
                path.write_bytes(bridge.data(audit))
                config = {"q_audit": {"path": str(path), "sha256": bridge.sha(path.read_bytes()), "bytes": path.stat().st_size}}
                with self.subTest(mutation=mutation), self.assertRaisesRegex(bridge.Refusal, "Verified real"):
                    bridge.q_baselines(config, bridge.Snapshots(), None)

    def test_template_cannot_produce(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "NEUTRAL-input.json"
            config = {"schema": bridge.SCHEMA, "prepared": False, "verified": False,
                      "native_statics": None, "q_audit": None, "q_reader_receipt": None,
                      "reviewed_q_reader_sha256": None, "output_directory": str(root / "out"), "target_output_root": None}
            path.write_bytes(bridge.data(config))
            with self.assertRaises(bridge.Refusal):
                bridge.produce(path, bridge.sha(path.read_bytes()))
            self.assertFalse((root / "out").exists())

    def test_stale_input_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "NEUTRAL.json"
            path.write_bytes(b'{}')
            with self.assertRaisesRegex(bridge.Refusal, "Changed"):
                bridge.produce(path, "0" * 64)

    def test_snapshot_detects_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "NEUTRAL.json"
            path.write_bytes(b'{}')
            snapshots = bridge.Snapshots()
            snapshots.read({"path": str(path), "sha256": bridge.sha(path.read_bytes())})
            path.write_bytes(b'{"a":1}')
            with self.assertRaisesRegex(bridge.Refusal, "Input changed"):
                snapshots.stable()

    def test_inventory_detects_extra_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshots = bridge.Snapshots()
            snapshots.inventory(root)
            (root / "NEUTRAL-extra").write_bytes(b"x")
            with self.assertRaises(bridge.Refusal):
                snapshots.stable()

    def test_arm_target_canonical(self):
        for value in (None, "C:/NEUTRAL", "/NEUTRAL/../x", "/NEUTRAL//x", "/NEUTRAL\\x"):
            with self.subTest(value=value), self.assertRaises(bridge.Refusal):
                bridge.target_root(value)

    def test_literals_are_not_executed(self):
        self.assertEqual(bridge.literals(b"X = 1\nY = __import__('not_a_module')\n"), {"X": 1})


class NativeSchemaTests(unittest.TestCase):
    def test_qualification_exact_nineteen_fields_and_false_limits(self):
        subject = bridge.SUBJECTS[0]
        row = {"r1_contract_ref": {"path": "C:/NEUTRAL/contract", "sha256": "1" * 64},
               "prepared_contract_ref": {"path": "C:/NEUTRAL/contract", "sha256": "1" * 64},
               "official_preparation_path": "/NEUTRAL/official"}
        refs = {key: {"path": "/NEUTRAL/" + key, "sha256": "0" * 64} for key in ("source_zip", "plan", "preparation_manifest")}
        audit = {"allocation": {"job_id": "0", "machine": "aarch64"}}
        _, record = bridge.build_records(subject, refs, {"subject_bindings": {subject: row}},
            {"source/NEUTRAL": "2" * 64}, audit, {}, {}, [])
        self.assertEqual(set(record), bridge.QFIELDS)
        self.assertEqual(len(record), 19)
        self.assertTrue(all(record[key] is False for key in bridge.LIMITS))
        self.assertEqual(record["allocation"], {"job_id": "0", "architecture": "aarch64", **bridge.RESOURCES})
        self.assertNotIn("model", record)
        self.assertNotIn("cell_key", record)

    def test_real_native_static_data_only_if_present(self):
        path = next((parent / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r1/STATICS.json"
                     for parent in Path(__file__).resolve().parents
                     if (parent / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r1/STATICS.json").is_file()), None)
        if path is None:
            self.skipTest("Original native statics unavailable")
        snapshots = bridge.Snapshots()
        _, plan, prep, _, _, projections = bridge.native_static({"path": str(path), "sha256": bridge.sha(path.read_bytes())}, snapshots)
        self.assertEqual(len(prep["files"]), 196)
        self.assertEqual(len(plan["cells"]), 60)
        self.assertEqual(len(projections), 15)
        snapshots.stable()


if __name__ == "__main__":
    unittest.main()
