"""Verify historical bytes and coverage without importing archived programs."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.full_snapshot import SnapshotError
from tools.recompute import EvidenceError
from tools.verify import verify_source_trees

REPO = Path(__file__).resolve().parents[1]
GUIDE = "reproducibility/reexecution-r1-r2-r2"


class SourceTreesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.files = {}
        self.editions = []
        for name in ("r1-historical", "r1-comparison", "r2-native"):
            archive = name + ".zip"
            archive_path = GUIDE + "/archives/" + archive
            self.add_file(archive_path, ("inert archive bytes " + name).encode())
            self.add_file("code/" + name + "/historical.py", b"raise RuntimeError('never execute')\n")
            self.add_file("code/" + name + "/README.md", b"historical documentation\n")
            self.editions.append({"path": "code/" + name, "archive": archive,
                                  "archive_sha256": self.files[archive_path]["sha256"], "files": 2})
        self.add_file("code/operations/producer.py", b"raise RuntimeError('never execute producer')\n")
        self.add_file("code/operations/tests/test_preserved.py", b"# inert archived test\n")
        self.add_file(GUIDE + "/LIRE-MOI.md", b"restoration guide\n")
        (self.root / "code/README.md").write_bytes(b"current documentation, outside source inventory\n")
        self.data = {"schema": "hpc-forest-published-source-trees-v1", "experiments_paused": True,
                     "historical_editions": self.editions, "operation_files": 2,
                     "files": list(self.files.values()), "scope": "Inert byte copies only."}
        self.save()

    def add_file(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        self.files[name] = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def save(self, value=None):
        (self.root / "code/SOURCES.json").write_text(json.dumps(self.data if value is None else value), encoding="utf8")

    def test_published_source_inventory(self):
        self.assertEqual(verify_source_trees(REPO), {"files": 575, "code_files": 537,
                         "restoration_files": 38, "historical_editions": 3, "operation_files": 226})

    def test_neutral_fixture_hashes_and_counts_without_execution(self):
        self.assertEqual(verify_source_trees(self.root), {"files": 12, "code_files": 8,
                         "restoration_files": 4, "historical_editions": 3, "operation_files": 2})
        # The programs would raise immediately if imported or executed.
        (self.root / "code/README.md").write_bytes(b"editable current documentation\n")
        self.assertEqual(verify_source_trees(self.root)["files"], 12)

    def test_source_byte_change_and_unlisted_file_are_rejected(self):
        target = self.root / "code/r2-native/historical.py"
        original = target.read_bytes()
        target.write_bytes(b"changed historical source\n")
        with self.assertRaises(EvidenceError):
            verify_source_trees(self.root)
        target.write_bytes(original)
        (self.root / "code/operations/unlisted.py").write_bytes(b"unlisted\n")
        with self.assertRaisesRegex(EvidenceError, "coverage"):
            verify_source_trees(self.root)

    def test_forged_metadata_and_incomplete_inventory_are_rejected(self):
        mutations = [lambda v: v.update({"experiments_paused": False}),
                     lambda v: v.update({"operation_files": True}),
                     lambda v: v["historical_editions"][0].update({"files": 3}),
                     lambda v: v["historical_editions"][0].update({"archive_sha256": "0" * 64}),
                     lambda v: v["files"].pop(),
                     lambda v: v["files"][0].update({"bytes": False}),
                     lambda v: v["files"][0].update({"unexpected": "field"})]
        for mutation in mutations:
            value = copy.deepcopy(self.data)
            mutation(value)
            self.save(value)
            with self.assertRaises(EvidenceError):
                verify_source_trees(self.root)

    def test_paths_case_collisions_and_self_inventory_are_rejected(self):
        for bad in ("../escape", "code/r1-historical/CON.txt", "code/r1-historical/file.",
                    "code/README.md", "code/SOURCES.json", "README.md"):
            value = copy.deepcopy(self.data)
            value["files"][0]["path"] = bad
            self.save(value)
            with self.subTest(path=bad), self.assertRaises(EvidenceError):
                verify_source_trees(self.root)
        value = copy.deepcopy(self.data)
        item = copy.deepcopy(value["files"][-1])
        item["path"] = item["path"].upper()
        value["files"].append(item)
        self.save(value)
        with self.assertRaises(EvidenceError):
            verify_source_trees(self.root)

    def test_source_junction_or_symlink_is_rejected_without_traversal(self):
        external = self.root / "outside"
        external.mkdir()
        (external / "never-import.py").write_bytes(b"raise RuntimeError('outside')\n")
        link = self.root / "code/operations/linked"
        try:
            link.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(external), str(link))
            except (ImportError, OSError):
                self.skipTest("Local account cannot create links or junctions")
        with self.assertRaises((EvidenceError, SnapshotError)):
            verify_source_trees(self.root)


if __name__ == "__main__":
    unittest.main()
