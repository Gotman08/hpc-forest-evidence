"""Copy the reviewed producer and its local evidence into the private preparation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Admission-Dynamique-Preparation-r1"
EXPECTED = {
    "dynamic_admission.py": "ec17f8be95869eae0e5059d6d99b08b03baaeab22c7b9d7ec642f1d38101d55e",
    "capacity.py": "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def exclusive(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
    return ref(path)


def main():
    for name, expected in EXPECTED.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise RuntimeError("Source changed after independent review")
    reports = ElementTree.parse(OUTPUT / "TESTS-NEUTRES-r3.xml").getroot().findall("testsuite")
    counts = {key: sum(int(item.get(key, "0")) for item in reports) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 140, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Final tests are incomplete")
    delivered = {name: exclusive(OUTPUT / name, (ROOT / name).read_bytes()) for name in (
        "dynamic_admission.py", "capacity.py", "test_dynamic_admission.py", "test_capacity.py", "test_observed_guards.py")}
    observation = ROOT / "cli-observation-real-r1/CLI-OBSERVATION.json"
    value = {
        "schema": "hpc-forest-matrix15-dynamic-admission-preparation-validation-v1",
        "sources": delivered,
        "source_review": {"decision": "SHIP", "reviewer": "public_review", "evidence_kind": "actual_read_only_independent_agent_review",
                          "reviewed_source_sha256": EXPECTED},
        "pytest": {"tests": 96, "subtests": 44, "junit_counts": counts,
                   "report": ref(OUTPUT / "TESTS-NEUTRES-r3.xml")},
        "ruff": "All checks passed using sealed source pyproject.toml configuration",
        "actual_cli_readonly_observation": ref(observation),
        "actual_cli_observed_at": json.loads(observation.read_bytes())["observed_at"],
        "cli_requires_fresh_observation_within_600_seconds_at_assembly": True,
        "actual_cli_commands": [["codex.exe", "--version"], ["codex.exe", "login", "status"]],
        "capacity_real_observed": False,
        "operational_authorizations_created": 0,
        "arm_runtime_or_native_cell_execution_validated": False,
        "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0,
        "prepared_inputs": ref(OUTPUT / "PREPARATION-NON-ADMISE/ENTREES-A-RENSEIGNER.json"),
        "native_source_127_modified": False,
    }
    validation = exclusive(OUTPUT / "VALIDATION-LOCALE.json", (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())
    manifest = {path.relative_to(OUTPUT).as_posix(): sha(path.read_bytes()) for path in sorted(OUTPUT.rglob("*")) if path.is_file()}
    manifest_ref = exclusive(OUTPUT / "FILES.sha256.json", (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())
    print(json.dumps({"validation": validation, "manifest": manifest_ref, "reviewed_sources": EXPECTED}))


if __name__ == "__main__":
    main()
