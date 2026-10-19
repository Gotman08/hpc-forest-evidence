"""Exercise only the stdlib restorer, never any restored project source."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PACKAGE = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r2"
ORIGINAL = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r1"
WORK = Path(__file__).resolve().parent / "restaurations-r2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}


def invoke(arguments):
    command = [sys.executable, "-I", "-B", str(PACKAGE / "preparer_copie.py"), *arguments]
    done = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    return {"argv": command, "returncode": done.returncode, "stdout": done.stdout, "stderr": done.stderr,
            "result": json.loads(done.stdout)}


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    assert not WORK.exists()
    WORK.mkdir()
    old_before = tree(ORIGINAL)
    catalogue = json.loads((PACKAGE / "CATALOGUE.json").read_text(encoding="utf-8"))
    copied = {}
    for name in ("archives", "manifestes", "documents"):
        for source in (ORIGINAL / name).rglob("*"):
            if source.is_file():
                relative = source.relative_to(ORIGINAL)
                actual = PACKAGE / relative
                assert actual.is_file() and sha(source) == sha(actual)
                copied[relative.as_posix()] = sha(actual)
    results = []
    restores = []
    for edition, count in (("r1-resultats-748259-cd769", 90), ("r1-harnais-9a68", 94), ("r2-matrice15-b79", 127)):
        verification = invoke(["--edition", edition, "--verify-only"])
        assert verification["returncode"] == 0 and verification["result"]["archive_verified"] is True
        assert verification["result"]["source_file_count"] == count and verification["result"]["source_executed"] is False
        results.append(verification)
        destination = WORK / edition
        restoration = invoke(["--edition", edition, "--destination", str(destination)])
        assert restoration["returncode"] == 0 and restoration["result"]["restored_source_verified"] is True
        assert restoration["result"]["source_file_count"] == count and restoration["result"]["scientific_run_started"] is False
        manifest_ref = catalogue["editions"][edition]["runtime_manifest"]
        manifest_path = PACKAGE / manifest_ref["path"]
        assert sha(manifest_path) == manifest_ref["sha256"]
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert tree(destination / "project") == declared
        restoration["independent_rehashed_file_count"] = len(declared)
        restores.append(restoration)
    existing = WORK / "r1-resultats-748259-cd769"
    existing_before = tree(existing)
    refusal = invoke(["--edition", "r1-resultats-748259-cd769", "--destination", str(existing)])
    assert refusal["returncode"] == 2 and refusal["result"]["restored_source_verified"] is False
    assert "Destination neuve" in refusal["result"]["error"]
    assert tree(existing) == existing_before
    assert tree(ORIGINAL) == old_before
    value = {"schema": "hpc-forest-private-three-source-restore-validation-v2", "verified": True,
             "verify_only": results, "fresh_restores": restores, "existing_destination_refusal": refusal,
             "existing_destination_unchanged": True, "predecessor_tree_unchanged": True,
             "predecessor_files_rehashed": len(old_before), "original_copied_files_byte_identical": copied,
             "source_counts": [90, 94, 127], "restored_source_files_independently_rehashed": 311,
             "historical_project_code_executed": False, "models_called": 0, "jobs_submitted": 0, "network_calls": 0,
             "only_executed_tool": "stdlib preparer_copie.py", "historical_campaign_replayed": False}
    report = PACKAGE / "VALIDATION-RESTAURATION.json"
    write(report, value)
    manifest = {path.relative_to(PACKAGE).as_posix(): sha(path) for path in PACKAGE.rglob("*") if path.is_file()}
    write(PACKAGE / "FILES.sha256.json", manifest)
    print(json.dumps({"verified": True, "verify_only_passed": 3, "fresh_restore_passed": 3,
                      "source_counts": [90, 94, 127], "independently_rehashed": 311, "existing_destination_refused_without_changes": True,
                      "predecessor_unchanged": True, "validation_sha256": sha(report), "manifest_sha256": sha(PACKAGE / "FILES.sha256.json"),
                      "catalogue_sha256": sha(PACKAGE / "CATALOGUE.json"), "guide_sha256": sha(PACKAGE / "LIRE-MOI.md")}))


if __name__ == "__main__":
    main()
