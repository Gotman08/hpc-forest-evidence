"""Seal only this r3 preparation; no operational audit or transport is invoked."""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
AUDIT = ROOT / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r3"
COLLECTION = ROOT / "outputs/HPC-Forest-Matrice15-Premier-Batch-Collecte-Preparation-r3"
OLD = {
    "first_batch_audit.py": (ROOT / "work/matrix15-first-batch-audit-r2/first_batch_audit.py",
                             "2bfc7140e336710f5db32cb7e379730c92e2dcc688535e41a85b1baa95da1539"),
    "collect_inputs.py": (ROOT / "work/matrix15-first-batch-collection-r2/collect_inputs.py",
                          "89312abd7038e8212b91c2361a429f94dad644448bb3f8b792cae4c9adafab3c"),
}


def ref(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8"))


def copy_exact(source, dest):
    if dest.exists():
        assert dest.read_bytes() == source.read_bytes(), "Existing candidate differs: " + str(dest)
    else:
        shutil.copyfile(source, dest)
    return ref(dest)


def functions(path):
    result = {}

    def visit(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + child.name
                if not isinstance(child, ast.ClassDef):
                    result[name] = ast.dump(child, include_attributes=False)
                visit(child, name + ".")
            else:
                visit(child, prefix)
    visit(ast.parse(path.read_bytes()))
    return result


def report(path):
    suites = ET.parse(path).getroot()
    rows = [suites] if suites.tag == "testsuite" else list(suites)
    counts = {key: sum(int(row.attrib.get(key, 0)) for row in rows)
              for key in ("tests", "failures", "errors", "skipped")}
    assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
    return counts


def main():
    assert WORK.name == "matrix15-first-batch-shared-shell-r3"
    assert AUDIT.is_dir() and COLLECTION.is_dir()
    for dest in (AUDIT, COLLECTION):
        assert not any(p.is_symlink() or p.is_junction() for p in (dest, *dest.parents))
        assert not (dest / "VALIDATION-LOCALE.json").exists()
    preserved = {}
    changes = {}
    patch = []
    for name, (original, checksum) in OLD.items():
        preserved[name] = ref(original)
        assert preserved[name]["sha256"] == checksum
        before, after = functions(original), functions(WORK / name)
        assert before.keys() == after.keys()
        changes[name] = sorted(key for key in before if before[key] != after[key])
        patch.extend(difflib.unified_diff(original.read_text().splitlines(True),
                     (WORK / name).read_text().splitlines(True),
                     fromfile="r2/" + name, tofile="r3/" + name))
    assert changes == {"first_batch_audit.py": ["Evidence.external_copies"], "collect_inputs.py": []}
    runtime = ROOT / "outputs/HPC-Forest-Matrice15-Admission-r2/RUNTIME-PRIVE-LOCAL.json"
    assert ref(runtime)["sha256"] == "91684ae8d3d0457d81d049bf6e096c02601fdbdc67fc762fdf697bdc23c35f2b"
    inventory = json.loads(runtime.read_bytes())
    assert len(inventory) == 127
    project = ROOT / "work/matrix15-admission-no-cycle-r2/project"
    assert all(ref(project / name)["sha256"] == checksum for name, checksum in inventory.items())
    archive = ROOT / "outputs/HPC-Forest-Matrice15-Admission-r2/HPC-FOREST-MATRIX15-ADMISSION-r2.zip"
    assert ref(archive)["sha256"] == "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
    assert (WORK / "RUFF-r3.txt").read_text().strip() == "All checks passed!"
    roles = [
        (AUDIT, "audit", "first_batch_audit.py", "test_first_batch_audit.py", "TESTS-AUDIT-r3-FINAL.xml", 72),
        (COLLECTION, "collection", "collect_inputs.py", "test_collect_inputs.py", "TESTS-COLLECTION-r3.xml", 21),
    ]
    for dest, role, source, tests, xml, cases in roles:
        source_dest = dest / ("lecteur/first_batch_audit.py" if role == "audit" else source)
        counts = report(WORK / xml)
        assert counts["tests"] == cases
        delivered = copy_exact(WORK / source, source_dest)
        delivered_tests = copy_exact(WORK / tests, dest / tests)
        delivered_xml = copy_exact(WORK / xml, dest / "TESTS-NEUTRES.xml")
        ruff = copy_exact(WORK / "RUFF-r3.txt", dest / "RUFF.txt")
        patch_path = dest / "DELTA-r2-r3.patch"
        with patch_path.open("x", encoding="utf8", newline="\n") as stream:
            stream.write("".join(patch))
        value = {
            "schema": "hpc-forest-matrix15-historical-shell-reader-preparation-v1",
            "edition": "r3", "role": role, "verified": False, "prepared_only": True,
            "observed_local_seal_at": time.time(), "independent_review_status": "pending",
            "source": ref(WORK / source), "delivered_source": delivered,
            "tests": {**counts, "source": ref(WORK / tests), "delivered_source": delivered_tests,
                      "report": delivered_xml, "fixtures_are_scientific_evidence": False},
            "ruff_passed": True, "ruff_output": ruff, "readme": ref(dest / "LIRE-MOI.md"),
            "delta": ref(patch_path), "changed_function_ASTs": changes,
            "preserved_r2_sources": preserved, "native_source_files_rehashed": 127,
            "native_runtime_manifest": ref(runtime), "native_archive": ref(archive),
            "historical_manifest_sha256": "43d5f925c0f2a81acc69d0bbcd35497464eb2b795292fdb288d83223ecf01b79",
            "historical_content_binding_job": "755562", "historical_exporter_job": "755597",
            "content_provenance_is_current_execution_proof": False,
            "current_binding_command_stream_and_deadline_checks_unchanged": True,
            "historical_receipts_modified": False, "release_installed": False,
            "production_external_copy_created": False, "current_admission_or_audit_produced": False,
            "actual_codex_cli_calls": 0, "actual_model_calls": 0, "actual_transfers": 0,
            "jobs_submitted": 0, "registry_actions": 0,
        }
        write(dest / "VALIDATION-LOCALE.json", value)
        files = {str(path.relative_to(dest)).replace("\\", "/"): ref(path)
                 for path in sorted(dest.rglob("*")) if path.is_file()}
        write(dest / "FILES.sha256.json", files)
        print(json.dumps({"role": role, "validation": ref(dest / "VALIDATION-LOCALE.json"),
                          "manifest": ref(dest / "FILES.sha256.json")}))


if __name__ == "__main__":
    main()
