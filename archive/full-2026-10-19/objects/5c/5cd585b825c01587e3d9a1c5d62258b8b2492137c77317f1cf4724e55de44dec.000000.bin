"""Record actual source readback and refusal to overwrite either restored copy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(relative, raw):
    path = OUTPUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(raw)
    return {"path": str(path), "sha256": sha(path)}


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}


def main():
    specification = importlib.util.spec_from_file_location("restore_catalogue", OUTPUT / "preparer_copie.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    checks = []
    for edition, folder in (("r1-harnais-9a68", "verification-R1-neuve"), ("r2-matrice15-b79", "verification-R2-neuve")):
        destination = ROOT / folder
        before = inventory(destination)
        refused = False
        try:
            module.prepare(OUTPUT, edition, destination)
        except ValueError as error:
            if "Destination neuve" not in str(error):
                raise
            refused = True
        after = inventory(destination)
        entry, files, declared = module.validate(OUTPUT, edition)
        if not refused or before != after or inventory(destination / "project") != declared:
            raise RuntimeError("Refus d'ecrasement ou relecture invalide")
        original_zip = Path(entry["original_source_zip"])
        if sha(original_zip) != entry["source_zip"]["sha256"]:
            raise RuntimeError("Archive historique originale modifiee")
        receipt = create("verifications/RESTAURATION-" + edition + ".json", (destination / "RESTAURATION.json").read_bytes())
        checks.append({"edition": edition, "source_file_count": len(files), "readback_exact": True,
                       "existing_destination_refused": refused, "existing_destination_byte_identical_after_refusal": before == after,
                       "original_archive_still_matches": entry["source_zip"]["sha256"], "actual_restoration_receipt": receipt})
    value = {"schema": "hpc-forest-private-r1-r2-local-restore-validation-v1", "checks": checks,
        "catalogue_sha256": sha(OUTPUT / "CATALOGUE.json"), "restore_script_sha256": sha(OUTPUT / "preparer_copie.py"),
        "independent_read_only_review": {"decision": "SHIP", "reviewer": "r1_archive_audit",
                                         "scope": "restore source, catalogue, guide, archive manifests and associated document hashes",
                                         "project_code_or_tests_executed_by_reviewer": False},
        "project_test_suites_executed": 0, "scientific_runs_started": 0,
        "native_model_calls": 0, "jobs_submitted": 0, "network_used": False,
        "private_local_only": True, "historical_archives_not_modified": True}
    validation = create("VALIDATION-RESTAURATION.json", (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
    manifest = inventory(OUTPUT)
    manifest_ref = create("FILES.sha256.json", (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"validation": validation, "manifest": manifest_ref}))


if __name__ == "__main__":
    main()
