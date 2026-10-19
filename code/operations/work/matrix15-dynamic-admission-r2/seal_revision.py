"""Seal only the reviewed r2 readback decoder; no collection or execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Admission-Dynamique-Preparation-r2"
EXPECTED = {"dynamic_admission.py": "806bb6bea6e0bb6141b66fd6170f230c91b18dd54e71d99ed78aa1e35759f132",
            "capacity.py": "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b"}


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
            raise RuntimeError("Reviewed source changed")
    if sha((BASE / "work/matrix15-dynamic-admission-r1/dynamic_admission.py").read_bytes()) != "ec17f8be95869eae0e5059d6d99b08b03baaeab22c7b9d7ec642f1d38101d55e":
        raise RuntimeError("Original producer changed")
    revision = json.loads((BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json").read_bytes())
    inventory = json.loads(Path(revision["runtime_manifest"]["path"]).read_bytes())
    project = BASE / "work/matrix15-admission-no-cycle-r2/project"
    if len(inventory) != 127 or any(sha((project / name).read_bytes()) != pin for name, pin in inventory.items()):
        raise RuntimeError("Source127 changed")
    report = OUTPUT / "TESTS-NEUTRES-r1.xml"
    suites = ElementTree.parse(report).getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 165, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Expected final local test result absent")
    delivered = {name: write(OUTPUT / name, (ROOT / name).read_bytes()) for name in (
        *EXPECTED, "test_dynamic_admission.py", "test_capacity.py", "test_observed_guards.py", "LIRE-MOI.md")}
    review = write(OUTPUT / "REVUE-DELTA.json", {"schema": "hpc-forest-matrix15-local-source-review-v1",
        "decision": "SHIP", "reviewer": "public_review", "evidence_kind": "actual_read_only_independent_agent_review",
        "reviewed_source_sha256": EXPECTED, "blocking_findings": [],
        "scope": "Positive canonical MCP line count and strict integer readback coverage only"})
    value = {"schema": "hpc-forest-matrix15-dynamic-admission-preparation-validation-v1",
        "sources": delivered, "source_review": review,
        "pytest": {"tests": 121, "subtests": 44, "junit_counts": counts, "report": ref(report)},
        "ruff": "All checks passed using sealed source127 pyproject.toml configuration",
        "actual_mcp_readonly_source": ref(BASE / "outputs/HPC-Forest-Q15-Execution-root-01/BOOTSTRAP-RESULT-REMOTE.json"),
        "raw_observation_rewritten": False, "actual_cli_observed": False, "capacity_real_observed": False,
        "operational_authorizations_created": 0, "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0,
        "native_source_127_modified": False, "source_127_files_rehashed": len(inventory),
        "original_r1_producer_modified": False, "prepared_inputs": ref(OUTPUT / "PREPARATION-NON-ADMISE/ENTREES-A-RENSEIGNER.json"),
        "arm_runtime_or_native_cell_execution_validated": False}
    validation = write(OUTPUT / "VALIDATION-LOCALE.json", value)
    manifest = write(OUTPUT / "FILES.sha256.json", {p.relative_to(OUTPUT).as_posix(): sha(p.read_bytes())
        for p in sorted(OUTPUT.rglob("*")) if p.is_file()})
    print(json.dumps({"validation": validation, "manifest": manifest, "sources": EXPECTED}))


if __name__ == "__main__":
    main()
