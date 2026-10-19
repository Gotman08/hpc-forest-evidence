"""Seal the reviewed pure input builder and its non-admitted example."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1"
PINS = {"build_inputs.py": "4d26cdab42a7b47cc8d326fbd638e9f44fbe404dbcac40ad64cf7dba42dd99d1",
        "test_build_inputs.py": "5cd86a65c2e226187bcec1923f5e9b3a3d0f0d12ad59012d7ff5b3c3b4cc2f5d"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as target:
        target.write(raw)
    return ref(path)


def main():
    for name, checksum in PINS.items():
        if sha((ROOT / name).read_bytes()) != checksum:
            raise RuntimeError("Reviewed builder changed")
    report = OUTPUT / "TESTS-r2.xml"
    suites = ElementTree.parse(report).getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 20, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Final test result absent")
    review = json.loads((ROOT / "REVUE-LECTURE-FRAICHE.json").read_bytes())
    if review.get("decision") != "SHIP" or review.get("reviewed_source_sha256") != PINS["build_inputs.py"]:
        raise RuntimeError("Actual independent source review absent")
    delivered = {name: write(OUTPUT / name, (ROOT / name).read_bytes()) for name in (
        *PINS, "LIRE-MOI.md", "REVUE-LECTURE-FRAICHE.json")}
    example = OUTPUT / "PREPARATION-FINALE-NON-ADMISE"
    prepared = json.loads((example / "PREPARED.json").read_bytes())
    bootstrap = json.loads((example / "INPUT-BOOTSTRAP.json").read_bytes())
    dynamic = json.loads((example / "INPUT-DYNAMIC-TEMPLATE.json").read_bytes())
    if (prepared.get("verified") is not False or bootstrap.get("first_batch_gate") is not None
            or dynamic.get("mode") != "PREPARE" or prepared.get("commands_to_execute") != []):
        raise RuntimeError("Default example promoted")
    revision = json.loads((BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json").read_bytes())
    inventory = json.loads(Path(revision["runtime_manifest"]["path"]).read_bytes())
    project = BASE / "work/matrix15-admission-no-cycle-r2/project"
    if len(inventory) != 127 or any(sha((project / name).read_bytes()) != checksum for name, checksum in inventory.items()):
        raise RuntimeError("Native source127 changed")
    value = {"schema": "hpc-forest-matrix15-extension-operation-builder-validation-v1", "mode": "PREPARE", "verified": False,
        "sources": delivered, "source_review": delivered["REVUE-LECTURE-FRAICHE.json"],
        "pytest": {"tests": 20, "junit_counts": counts, "report": ref(report)}, "ruff": "All checks passed using source127 configuration",
        "default_prepared": ref(example / "PREPARED.json"), "default_bootstrap": ref(example / "INPUT-BOOTSTRAP.json"),
        "default_dynamic_template": ref(example / "INPUT-DYNAMIC-TEMPLATE.json"),
        "locked_dynamic_sources": prepared["locked_sources"], "locked_bootstrap_sources": prepared["locked_bootstrap"],
        "historical_source_only_closure": prepared["closure_primary"], "first_batch_gate_received_by_this_delivery": False,
        "reservation_consumption_implemented": False, "registry_modified": False, "source127_files_rehashed": 127,
        "operational_roles_created": 0, "operational_authorizations_created": 0, "assemble_invoked": False,
        "capacity_observed": False, "executable_probes": 0, "native_model_calls": 0, "jobs_submitted": 0,
        "workers_started_or_stopped": 0, "network_operations": 0, "commands_to_execute": []}
    validation = write(OUTPUT / "VALIDATION-LOCALE.json", value)
    manifest = write(OUTPUT / "FILES.sha256.json", {p.relative_to(OUTPUT).as_posix(): sha(p.read_bytes())
        for p in sorted(OUTPUT.rglob("*")) if p.is_file()})
    print(json.dumps({"validation": validation, "manifest": manifest, "sources": PINS}))


if __name__ == "__main__":
    main()
