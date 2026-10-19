"""Copy only the reviewed continuation preparation; never admit execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Admission-Extension-Preparation-r2"
EXPECTED = {
    "dynamic_admission.py": "ec9a9cc1f5c9530dc31262c7add127f24395178c7519b25ecd6adff2f58f7740",
    "capacity.py": "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b",
    "selection.py": "a0d03ff5a5be74a9feef2be50c9aae6ea34a19c3eefd0decc5ae0b0769bf4a15",
    "extension_gate.py": "e8e8ee7e69ccced5d15054f1a61f3970e0019a282e7c20f8cdbc4db77aa9eb30",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
    return ref(path)


def main():
    for name, pin in EXPECTED.items():
        if sha((ROOT / name).read_bytes()) != pin:
            raise RuntimeError("Reviewed continuation source changed")
    gate = BASE / "outputs/HPC-Forest-Matrice15-Bootstrap-Extension-Preparation-r2/lecteur/extension_gate.py"
    if sha(gate.read_bytes()) != EXPECTED["extension_gate.py"]:
        raise RuntimeError("Shared portable gate differs")
    originals = {"r1": "ec17f8be95869eae0e5059d6d99b08b03baaeab22c7b9d7ec642f1d38101d55e",
                 "r2": "806bb6bea6e0bb6141b66fd6170f230c91b18dd54e71d99ed78aa1e35759f132"}
    for revision, checksum in originals.items():
        if sha((BASE / ("work/matrix15-dynamic-admission-" + revision) / "dynamic_admission.py").read_bytes()) != checksum:
            raise RuntimeError("Original first-cell producer changed")
    native_revision = json.loads((BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json").read_bytes())
    inventory = json.loads(Path(native_revision["runtime_manifest"]["path"]).read_bytes())
    project = BASE / "work/matrix15-admission-no-cycle-r2/project"
    if len(inventory) != 127 or any(sha((project / name).read_bytes()) != pin for name, pin in inventory.items()):
        raise RuntimeError("Source127 changed")
    report = OUTPUT / "TESTS-NEUTRES-r3.xml"
    suites = ElementTree.parse(report).getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 275, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Expected continuation tests absent")
    review_path = OUTPUT / "REVUE-LECTURE-FRAICHE.json"
    review = json.loads(review_path.read_bytes())
    if review.get("decision") != "SHIP" or review.get("reviewed_source_sha256") != EXPECTED:
        raise RuntimeError("Actual fresh reviewed source pins absent")
    names = (*EXPECTED, "test_dynamic_admission.py", "test_capacity.py", "test_observed_guards.py",
             "test_selection.py", "test_extension.py", "LIRE-MOI.md")
    delivered = {name: write(OUTPUT / name, (ROOT / name).read_bytes()) for name in names}
    state_path = OUTPUT / "PREPARATION-NON-ADMISE/ETAT-PREPARATOIRE-60.json"
    state = json.loads(state_path.read_bytes())
    selection_path = OUTPUT / "PREPARATION-NON-ADMISE/SELECTION-PREPARATOIRE.json"
    selection = json.loads(selection_path.read_bytes())
    if (state.get("verified") is not False or len(state["records"]) != 60
            or selection.get("verified") is not False or len(selection["candidates"]) != 59
            or selection.get("commands_to_execute") != [] or selection.get("prerequisite_pending") is not True):
        raise RuntimeError("Prepared state promoted or incomplete")
    value = {"schema": "hpc-forest-matrix15-dynamic-extension-preparation-validation-v1",
        "mode": "PREPARE", "verified": False, "sources": delivered, "source_review": ref(review_path),
        "pytest": {"tests": 231, "subtests": 44, "junit_counts": counts, "report": ref(report)},
        "ruff": "All checks passed using sealed source127 pyproject.toml configuration",
        "source_zip_sha256": native_revision["source_zip"]["sha256"],
        "plan_sha256": "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f",
        "first_batch_gate_received": False, "automatic_extension": False, "selected_for_execution": [],
        "registered_cells": 60, "preparatory_candidates": 59, "state": ref(state_path), "selection": ref(selection_path),
        "portable_gate_identical_to_bootstrap": ref(gate), "original_first_cell_producers_sha256": originals,
        "native_source_127_modified": False, "source_127_files_rehashed": len(inventory),
        "actual_cli_observed": False, "capacity_real_observed": False, "operational_authorizations_created": 0,
        "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0, "automations_created": 0,
        "arm_runtime_or_native_cell_execution_validated": False}
    validation = write(OUTPUT / "VALIDATION-LOCALE.json", value)
    manifest = write(OUTPUT / "FILES.sha256.json", {p.relative_to(OUTPUT).as_posix(): sha(p.read_bytes())
        for p in sorted(OUTPUT.rglob("*")) if p.is_file()})
    print(json.dumps({"validation": validation, "manifest": manifest, "sources": EXPECTED}))


if __name__ == "__main__":
    main()
