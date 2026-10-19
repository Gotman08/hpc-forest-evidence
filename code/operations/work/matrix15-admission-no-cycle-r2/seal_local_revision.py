"""Package the reviewed private source, never a proposed operational admission."""
from __future__ import annotations

import difflib
import hashlib
import json
import stat
import zipfile
from xml.etree import ElementTree
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "project"
ORIGINAL = BASE / "work/matrix15-single-pilot-r1/project"
PREVIOUS = BASE / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1"
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Admission-r2"
IGNORED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", "venv"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()
            and not set(path.relative_to(root).parts).intersection(IGNORED)}


def write_json(name, value):
    path = OUTPUT / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = inventory(ORIGINAL)
    expected = json.loads((PREVIOUS / "RUNTIME-PRIVE-LOCAL.json").read_text(encoding="utf8"))
    original_manifest = {name: digest(raw) for name, raw in original.items()}
    if original_manifest != expected:
        raise RuntimeError("Preserved original project differs from its received revision manifest")
    files = inventory(PROJECT)
    manifest = {name: digest(raw) for name, raw in files.items()}
    runtime_ref = write_json("RUNTIME-PRIVE-LOCAL.json", manifest)
    archive = OUTPUT / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, raw in files.items():
            item = zipfile.ZipInfo("HPC-Forest/" + name, (1980, 1, 1, 0, 0, 0))
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(item, raw)
    changed = sorted(name for name in files if files[name] != original.get(name))
    removed = sorted(set(original) - set(files))
    if removed:
        raise RuntimeError("Unexpected source deletion")
    patch = []
    for name in changed:
        old = original.get(name, b"").decode("utf8").splitlines(keepends=True)
        new = files[name].decode("utf8").splitlines(keepends=True)
        patch.extend(difflib.unified_diff(old, new, fromfile="a/" + name, tofile="b/" + name))
    patch_path = OUTPUT / "ADMISSION-SANS-CYCLE.patch"
    patch_path.write_text("".join(patch), encoding="utf8")
    protocol = OUTPUT / "PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"
    protocol.write_bytes((PREVIOUS / protocol.name).read_bytes())
    value = {
        "schema": "hpc-forest-matrix15-private-admission-no-cycle-revision-v1",
        "original_project_preserved": str(ORIGINAL),
        "original_runtime_manifest": {"path": str(PREVIOUS / "RUNTIME-PRIVE-LOCAL.json"),
                                      "sha256": digest((PREVIOUS / "RUNTIME-PRIVE-LOCAL.json").read_bytes())},
        "original_inventory_still_identical": True,
        "private_project": str(PROJECT),
        "source_zip": {"path": str(archive), "sha256": digest(archive.read_bytes())},
        "runtime_manifest": runtime_ref,
        "protocol": {"path": str(protocol), "sha256": digest(protocol.read_bytes())},
        "patch": {"path": str(patch_path), "sha256": digest(patch_path.read_bytes())},
        "changed_files": changed,
        "removed_files": removed,
        "source_files": len(files),
        "plan_schema": "hpc-forest-matrix15-native-max-plan-v2",
        "plan_final_qualification_and_reception_refs_must_be_null": True,
        "authorization_carries_final_receipt_refs": True,
        "scientific_protocol_and_sixty_session_identities_unchanged": True,
        "operational_admission_created": False,
        "launch_ready": False,
        "native_model_calls": 0,
        "jobs_submitted": 0,
        "network_or_publication_performed": False,
    }
    write_json("REVISION-ADMISSION-SANS-CYCLE.json", value)
    report = OUTPUT / "TESTS-NEUTRES-FINAL-r2.xml"
    suites = ElementTree.parse(report).getroot().findall("testsuite")
    counts = {key: sum(int(suite.get(key, "0")) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 349, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Final neutral suite receipt is incomplete")
    write_json("VALIDATION-LOCALE.json", {
        "schema": "hpc-forest-matrix15-no-cycle-local-validation-v1",
        "source_zip": value["source_zip"], "runtime_manifest": runtime_ref,
        "pytest_report": {"path": str(report), "sha256": digest(report.read_bytes())},
        "pytest": counts,
        "ruff": "python -I -B -m ruff check src tests --no-cache: All checks passed",
        "verify_runtime_exact_zip_manifest_and_current_source_passed": True,
        "graph_tests": 29,
        "graph_test_external_pins_substituted": ["protocol", "R1 aggregate", "harness", "CLI_FILES", "primes gate"],
        "hash_path_qualification_reception_and_lane_checks_mocked": False,
        "host_projection_tests_are_local_metadata_only": True,
        "operational_subject_qualification_or_native_admission_proved": False,
        "native_model_calls": 0, "jobs_submitted": 0,
    })
    print(json.dumps({"source_zip_sha256": value["source_zip"]["sha256"],
                      "runtime_manifest_sha256": runtime_ref["sha256"], "source_files": len(files),
                      "changed_files": changed}, indent=2))


if __name__ == "__main__":
    main()
