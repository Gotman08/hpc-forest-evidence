"""Offline fixtures for inert, lossless and fail-closed snapshot operations."""
import copy
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import full_snapshot as fs


class FullSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.first = self.base / "source-a"
        self.second = self.base / "source-b"
        self.first.mkdir()
        self.second.mkdir()
        (self.first / "empty-folder").mkdir()
        (self.first / "empty.bin").write_bytes(b"")
        (self.first / "boundary.bin").write_bytes(b"abcdefgh")
        (self.second / "duplicate.bin").write_bytes(b"abcdefgh")
        (self.second / "nine.bin").write_bytes(b"abcdefghi")
        (self.first / ".git").mkdir()
        (self.first / ".git" / "HEAD").write_bytes(b"ref: refs/heads/frozen\n")
        self.plan = {
            "schema": fs.PLAN_SCHEMA,
            "roots": [{"id": key, "path": str(path), "label": key, "exclude_prefixes": []}
                      for key, path in (("r1", self.first), ("r2", self.second))],
            "runtime_excluded_basenames": [], "exclude_directory_names": [],
            "chunk_bytes": 4, "created_at_utc": "2026-10-19T00:00:00Z",
        }
        self.plan_path = self.base / "plan.json"
        self.snapshot = self.base / "snapshot"

    def build(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        return fs.build(self.plan_path, self.snapshot)

    def manifest(self):
        index = json.loads((self.snapshot / "INVENTORY.json").read_text(encoding="utf-8"))
        return fs._read_inventory(self.snapshot, index)[0]

    def save(self, manifest):
        # Fixtures deliberately replace their own catalog pages to exercise the
        # verifier beyond the outer authenticated index, without touching sources.
        (self.snapshot / "INVENTORY.json").unlink()
        for path in (self.snapshot / "catalogs").iterdir():
            path.unlink()
        fs._write_inventory(self.snapshot, manifest)

    def test_roundtrip_dedup_empty_and_chunk_boundaries(self):
        counts = self.build()
        self.assertEqual(counts["files"], 5)
        self.assertEqual(counts["unique_objects"], 4)
        self.assertEqual(fs.verify(self.snapshot), counts)
        value = self.manifest()
        self.assertNotIn(str(self.first), json.dumps(value))
        eight = next(o for o in value["objects"] if o["bytes"] == 8)
        nine = next(o for o in value["objects"] if o["bytes"] == 9)
        self.assertEqual([p["bytes"] for p in eight["parts"]], [4, 4])
        self.assertEqual([p["bytes"] for p in nine["parts"]], [4, 4, 1])
        destination = self.base / "restored"
        result = fs.restore(self.snapshot, destination)
        self.assertEqual(result, {"restored_files": 5, "selected_roots": 2, "inert_links": 0})
        self.assertEqual((destination / "r1/boundary.bin").read_bytes(), b"abcdefgh")
        self.assertEqual((destination / "r2/duplicate.bin").read_bytes(), b"abcdefgh")
        self.assertEqual((destination / "r1/empty.bin").read_bytes(), b"")
        self.assertTrue((destination / "r1/empty-folder").is_dir())
        self.assertEqual((destination / "r1/.git/HEAD").read_bytes(), b"ref: refs/heads/frozen\n")
        self.assertFalse(json.loads((destination / "LINKS.json").read_text())["links_activated"])

    def test_selected_root_only_and_no_execution(self):
        marker = self.base / "executed"
        payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n".encode()
        (self.first / "do-not-run.py").write_bytes(payload)
        self.build()
        destination = self.base / "selected"
        result = fs.restore(self.snapshot, destination, ["r1"])
        self.assertEqual(result["selected_roots"], 1)
        self.assertFalse((destination / "r2").exists())
        self.assertEqual((destination / "r1/do-not-run.py").read_bytes(), payload)
        self.assertFalse(marker.exists())

    def test_explicit_exclusions_are_inventoried(self):
        (self.first / "dependencies").mkdir()
        (self.first / "dependencies/module.py").write_bytes(b"large dependency")
        (self.first / "worker.lock").write_bytes(b"runtime")
        (self.first / "private-build").mkdir()
        (self.first / "private-build/value").write_bytes(b"private")
        self.plan["exclude_directory_names"] = ["dependencies"]
        self.plan["runtime_excluded_basenames"] = ["worker.lock"]
        self.plan["roots"][0]["exclude_prefixes"] = ["private-build"]
        self.build()
        exclusions = {e["path"]: e["reason"] for e in self.manifest()["exclusions"]}
        self.assertEqual(exclusions, {"dependencies": "excluded-directory-name",
                                     "private-build": "excluded-prefix", "worker.lock": "runtime-excluded-basename"})
        self.assertIn(".git/HEAD", {f["path"] for f in self.manifest()["files"]})

    def test_corruption_and_existing_destination_leave_destination_untouched(self):
        self.build()
        obj = next(o for o in self.manifest()["objects"] if o["bytes"])
        part = self.snapshot / obj["parts"][0]["path"]
        part.write_bytes(b"!" + part.read_bytes()[1:])
        destination = self.base / "must-not-exist"
        with self.assertRaises(fs.SnapshotError):
            fs.restore(self.snapshot, destination)
        self.assertFalse(destination.exists())
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_existing_destination_and_snapshot_never_overwritten(self):
        self.build()
        destination = self.base / "existing"
        destination.mkdir()
        marker = destination / "keep.bin"
        marker.write_bytes(b"keep")
        with self.assertRaises(fs.SnapshotError):
            fs.restore(self.snapshot, destination)
        self.assertEqual(list(destination.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b"keep")
        before = (self.snapshot / "INVENTORY.json").read_bytes()
        with self.assertRaises(fs.SnapshotError):
            fs.build(self.plan_path, self.snapshot)
        self.assertEqual((self.snapshot / "INVENTORY.json").read_bytes(), before)

    def test_missing_or_orphan_files_are_rejected(self):
        self.build()
        orphan = self.snapshot / "unlisted.bin"
        orphan.write_bytes(b"orphan")
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)
        orphan.unlink()
        part = self.snapshot / self.manifest()["objects"][0]["parts"][0]["path"]
        part.unlink()
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_whole_aggregate_hash_is_checked_beyond_individual_parts(self):
        self.build()
        value = self.manifest()
        obj = next(o for o in value["objects"] if o["bytes"] == 8)
        original = obj["sha256"]
        replacement = "f" * 64 if original != "f" * 64 else "e" * 64
        obj["sha256"] = replacement
        for item in value["files"]:
            if item["sha256"] == original:
                item["sha256"] = replacement
        for index, part in enumerate(obj["parts"]):
            old = self.snapshot / part["path"]
            part["path"] = fs._part_path(replacement, index)
            new = self.snapshot / part["path"]
            new.parent.mkdir(exist_ok=True)
            old.rename(new)
        # Remove the now empty prefix directory to isolate the aggregate check.
        old.parent.rmdir()
        self.save(value)
        with self.assertRaisesRegex(fs.SnapshotError, "whole object"):
            fs.verify(self.snapshot)

    def test_manifest_traversal_case_collisions_counts_and_duplicate_json(self):
        self.build()
        original = self.manifest()
        for bad in ("../escape", "/absolute", "C:/absolute", "back\\slash", "a//b", "a/./b"):
            value = copy.deepcopy(original)
            value["files"][0]["path"] = bad
            self.save(value)
            with self.subTest(bad=bad), self.assertRaises(fs.SnapshotError):
                fs.verify(self.snapshot)
        value = copy.deepcopy(original)
        item = copy.deepcopy(value["files"][0])
        item["path"] = item["path"].upper()
        value["files"].append(item)
        value["counts"] = fs._counts(value)
        self.save(value)
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)
        value = copy.deepcopy(original)
        value["counts"]["files"] = False
        self.save(value)
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)
        (self.snapshot / "INVENTORY.json").write_text('{"schema":1,"schema":2}', encoding="utf8")
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_root_and_object_shapes_are_closed(self):
        self.build()
        original = self.manifest()
        mutations = [lambda v: v["roots"][0].update({"path": str(self.first)}),
                     lambda v: v["objects"][0].update({"unexpected": True}),
                     lambda v: v.update({"chunk_bytes": fs.MAX_CHUNK_BYTES + 1}),
                     lambda v: v["roots"].append(copy.deepcopy(v["roots"][0]))]
        for mutation in mutations:
            value = copy.deepcopy(original)
            mutation(value)
            self.save(value)
            with self.assertRaises(fs.SnapshotError):
                fs.verify(self.snapshot)

    def test_link_targets_are_metadata_and_never_activated(self):
        link = self.first / "outside-link"
        try:
            link.symlink_to(self.second, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(self.second), str(link))
            except (ImportError, OSError):
                self.skipTest("Local account cannot create links or junctions")
        self.build()
        value = self.manifest()
        self.assertEqual(value["counts"]["links"], 1)
        self.assertNotIn("outside-link/duplicate.bin", {f["path"] for f in value["files"]})
        destination = self.base / "links-restored"
        fs.restore(self.snapshot, destination)
        self.assertFalse((destination / "r1/outside-link").exists())
        metadata = json.loads((destination / "LINKS.json").read_text())["links"][0]
        self.assertTrue(Path(metadata["target"]).samefile(self.second))
        # Snapshot directory entries must never be links or junctions either.
        linked = self.snapshot / "linked-directory"
        try:
            linked.symlink_to(self.second, target_is_directory=True)
        except (OSError, NotImplementedError):
            import _winapi
            _winapi.CreateJunction(str(self.second), str(linked))
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_linked_object_file_is_rejected(self):
        probe = self.base / "link-permission-probe"
        try:
            probe.symlink_to(self.first / "boundary.bin")
        except (OSError, NotImplementedError):
            self.skipTest("Local account cannot create file symbolic links")
        self.build()
        value = self.manifest()
        ordinary = self.snapshot / value["objects"][0]["parts"][0]["path"]
        raw = ordinary.read_bytes()
        external = self.base / "external-part"
        external.write_bytes(raw)
        ordinary.unlink()
        ordinary.symlink_to(external)
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_restore_inside_source_or_snapshot_is_rejected_before_writing(self):
        self.build()
        for destination in (self.first / "new-restoration", self.snapshot / "new-restoration"):
            with self.subTest(destination=destination), self.assertRaises(fs.SnapshotError):
                fs.restore(self.snapshot, destination)
            self.assertFalse(destination.exists())
        try:
            alias = self.base / "alias"
            alias.symlink_to(self.first, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(fs.SnapshotError):
            fs.restore(self.snapshot, alias / "new-restoration")
        self.assertFalse((self.first / "new-restoration").exists())

    def test_source_mutation_is_refused_and_partial_snapshot_preserved(self):
        original_digest = fs._digest_file
        mutated = False

        def changing_digest(path):
            nonlocal mutated
            result = original_digest(path)
            if path == self.first / "boundary.bin" and not mutated:
                path.write_bytes(b"changed!")
                mutated = True
            return result

        self.plan_path.write_text(json.dumps(self.plan), encoding="utf8")
        with mock.patch.object(fs, "_digest_file", side_effect=changing_digest), self.assertRaises(fs.SnapshotError):
            fs.build(self.plan_path, self.snapshot)
        self.assertTrue(self.snapshot.is_dir())
        self.assertFalse((self.snapshot / "INVENTORY.json").exists())

    def test_source_addition_during_capture_is_refused(self):
        original_write = fs._write_parts
        mutated = False

        def changing_write(*args, **kwargs):
            nonlocal mutated
            result = original_write(*args, **kwargs)
            if not mutated:
                (self.first / "late-file").write_bytes(b"late")
                mutated = True
            return result

        self.plan_path.write_text(json.dumps(self.plan), encoding="utf8")
        with mock.patch.object(fs, "_write_parts", side_effect=changing_write), self.assertRaises(fs.SnapshotError):
            fs.build(self.plan_path, self.snapshot)
        self.assertFalse((self.snapshot / "INVENTORY.json").exists())

    def test_invalid_selection_is_rejected_before_destination_creation(self):
        self.build()
        for selected in ([], ["unknown"], ["r1", "r1"]):
            destination = self.base / "invalid-selection"
            with self.subTest(selected=selected), self.assertRaises(fs.SnapshotError):
                fs.restore(self.snapshot, destination, selected)
            self.assertFalse(destination.exists())

    def test_chunk_limit_is_enforced_before_output_creation(self):
        self.plan["chunk_bytes"] = fs.MAX_CHUNK_BYTES + 1
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf8")
        with self.assertRaises(fs.SnapshotError):
            fs.build(self.plan_path, self.snapshot)
        self.assertFalse(self.snapshot.exists())

    def test_catalog_page_boundary_and_tampering(self):
        self.plan["catalog_entries"] = 2
        self.build()
        index = json.loads((self.snapshot / "INVENTORY.json").read_text(encoding="utf8"))
        self.assertEqual([r["count"] for r in index["files"]], [2, 2, 1])
        self.assertEqual([r["count"] for r in index["objects"]], [2, 2])
        self.assertLess((self.snapshot / "INVENTORY.json").stat().st_size, fs.MAX_CATALOG_BYTES)
        first_page = self.snapshot / index["files"][0]["path"]
        raw = first_page.read_bytes()
        first_page.write_bytes(b"!" + raw[1:])
        with self.assertRaisesRegex(fs.SnapshotError, "catalog"):
            fs.verify(self.snapshot)

    def test_orphan_catalog_and_oversized_catalog_references(self):
        self.build()
        orphan = self.snapshot / "catalogs/orphan.json"
        orphan.write_bytes(b"[]")
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)
        orphan.unlink()
        index = json.loads((self.snapshot / "INVENTORY.json").read_text(encoding="utf8"))
        index["files"][0]["bytes"] = fs.MAX_CATALOG_BYTES + 1
        (self.snapshot / "INVENTORY.json").write_text(json.dumps(index), encoding="utf8")
        with self.assertRaises(fs.SnapshotError):
            fs.verify(self.snapshot)

    def test_catalog_byte_boundary_is_independent_of_entry_limit(self):
        for number in range(35):
            (self.first / (f"long-{number:02d}-" + "x" * 150)).write_bytes(b"same")
        with mock.patch.object(fs, "MAX_CATALOG_BYTES", 6000):
            self.build()
            index = json.loads((self.snapshot / "INVENTORY.json").read_text(encoding="utf8"))
            self.assertGreater(len(index["files"]), 1)
            self.assertTrue(all(r["bytes"] <= 6000 for table in fs.TABLES for r in index[table]))
            self.assertTrue(all(r["count"] < fs.DEFAULT_CATALOG_ENTRIES for r in index["files"]))
            fs.verify(self.snapshot)

    def test_windows_aliases_are_rejected_before_restore_creates_destination(self):
        self.build()
        original = self.manifest()
        aliases = ("file.", "dir ", "NUL.txt", "CON", "aux.data", "com1.py", "LPT9.log",
                   "COM¹.txt", "nested/PRN.csv", 'quote"name', "question?mark", "star*name",
                   "pipe|name", "left<name", "right>name")
        for alias in aliases:
            value = copy.deepcopy(original)
            value["files"][0]["path"] = alias
            self.save(value)
            destination = self.base / "alias-refused"
            with self.subTest(alias=alias), self.assertRaises(fs.SnapshotError):
                fs.restore(self.snapshot, destination)
            self.assertFalse(destination.exists())
        for alias in ("CON", "NUL.txt", "r1.", "LINKS.json", "LINKS.json."):
            value = copy.deepcopy(original)
            old_id = value["roots"][0]["id"]
            value["roots"][0]["id"] = alias
            for table in ("directories", "files", "links", "exclusions"):
                for item in value[table]:
                    if item["root"] == old_id:
                        item["root"] = alias
            self.save(value)
            destination = self.base / "root-alias-refused"
            with self.subTest(root_alias=alias), self.assertRaises(fs.SnapshotError):
                fs.restore(self.snapshot, destination)
            self.assertFalse(destination.exists())

    def test_oversized_index_is_rejected_before_reading_its_contents(self):
        self.build()
        index = self.snapshot / "INVENTORY.json"
        with index.open("r+b") as stream:
            stream.truncate(fs.MAX_CATALOG_BYTES + 1)
        destination = self.base / "oversized-index-refused"
        # Size rejection occurs before any read handle or JSON parser is used.
        with (mock.patch.object(fs.os, "open", side_effect=AssertionError("Must reject before read")),
              self.assertRaisesRegex(fs.SnapshotError, "oversized")):
            fs.restore(self.snapshot, destination)
        self.assertFalse(destination.exists())

    def test_inert_executable_extension_and_readonly_git_object_roundtrip(self):
        executable = self.first / "neutral-fixture.exe"
        executable.write_bytes(b"inert fixture bytes; never an executable\n")
        git_object = self.first / ".git/objects/aa/neutral-object"
        git_object.parent.mkdir(parents=True)
        git_object.write_bytes(b"inert readonly historical Git object\n")
        git_object.chmod(stat.S_IREAD)
        readonly_mode = git_object.stat().st_mode
        self.build()
        destination = self.base / "executable-extension-restored"
        fs.restore(self.snapshot, destination)
        self.assertEqual((destination / "r1/neutral-fixture.exe").read_bytes(), executable.read_bytes())
        self.assertEqual((destination / "r1/.git/objects/aa/neutral-object").read_bytes(), git_object.read_bytes())
        self.assertEqual(git_object.stat().st_mode, readonly_mode)
if __name__ == "__main__":
    unittest.main()
