"""Seal the reviewed Windows venv capacity derivative; no operational actions."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Admission-Extension-Preparation-r3"
EXPECTED = {
    "dynamic_admission.py": "4d4216536ebf31079d208a9f6fa4a45ce1c0df3b972f4c3baafeba6204d97bda",
    "capacity.py": "a4f9121ef769ae98524f179a92b2ea27ea2a139e3ccc8c8982280f26c74b1a1d",
    "selection.py": "a0d03ff5a5be74a9feef2be50c9aae6ea34a19c3eefd0decc5ae0b0769bf4a15",
    "extension_gate.py": "e8e8ee7e69ccced5d15054f1a61f3970e0019a282e7c20f8cdbc4db77aa9eb30",
    "VENV-RUNTIME-IDENTITY.json": "049c5c1602814ec3541fcaa414f9c70dec4ecebbee9017414fbca9510be72f88",
}
ORIGINALS = {
    "work/matrix15-dynamic-admission-r1/dynamic_admission.py": "ec17f8be95869eae0e5059d6d99b08b03baaeab22c7b9d7ec642f1d38101d55e",
    "work/matrix15-dynamic-admission-r2/dynamic_admission.py": "806bb6bea6e0bb6141b66fd6170f230c91b18dd54e71d99ed78aa1e35759f132",
    "work/matrix15-dynamic-admission-extension-r2/dynamic_admission.py": "ec9a9cc1f5c9530dc31262c7add127f24395178c7519b25ecd6adff2f58f7740",
    "work/matrix15-dynamic-admission-r1/capacity.py": "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b",
    "work/matrix15-dynamic-admission-extension-r2/capacity.py": "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b",
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
            raise RuntimeError("Reviewed source changed")
    for name, pin in ORIGINALS.items():
        if sha((BASE / name).read_bytes()) != pin:
            raise RuntimeError("An original producer changed")
    revision = json.loads((BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json").read_bytes())
    inventory = json.loads(Path(revision["runtime_manifest"]["path"]).read_bytes())
    project = BASE / "work/matrix15-admission-no-cycle-r2/project"
    if len(inventory) != 127 or any(sha((project / name).read_bytes()) != pin for name, pin in inventory.items()):
        raise RuntimeError("Source127 changed")
    prefix = BASE / "outputs/HPC-Forest-Matrice15-Bootstrap-Extension-Preparation-r3/lecteur/job_prefix.py"
    if sha(prefix.read_bytes()) != "ed7c7ad59aa06d905f259e97a0bd83f2af3ed9be006d977bef3c46e92512db16":
        raise RuntimeError("Reviewed post-srun prefix changed")
    report = OUTPUT / "TESTS-NEUTRES-r1.xml"
    suites = ElementTree.parse(report).getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 326, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError("Complete final tests absent")
    review_path = ROOT / "REVUE-LECTURE-FRAICHE.json"
    review = json.loads(review_path.read_bytes())
    if review.get("decision") != "SHIP" or review.get("reviewed_source_sha256") != EXPECTED:
        raise RuntimeError("Exact independent reviewed pins absent")
    names = (*EXPECTED, "test_dynamic_admission.py", "test_capacity.py", "test_observed_guards.py", "test_selection.py",
             "test_extension.py", "test_venv_capacity.py", "LIRE-MOI.md", "REVUE-LECTURE-FRAICHE.json")
    delivered = {name: write(OUTPUT / name, (ROOT / name).read_bytes()) for name in names}
    spec = importlib.util.spec_from_file_location("capacity_offline_replay", OUTPUT / "capacity.py")
    capacity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capacity)
    sample_path = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/worker-launch-r1/CIM-IDENTITES-REELLES-r1.json"
    sample_ref = ref(sample_path)
    if sample_ref["sha256"] != "840f1c77fe6f438575fffe795e88346a5358de0d52bba3887a2b944713a492aa":
        raise RuntimeError("ROOT primary sample changed")
    sample = json.loads(sample_path.read_bytes())
    identity = capacity.load_venv_identity()  # file checks only; no census/lock/admission
    result = capacity.classify_processes(sample["processes"], sample["observed_at"], venv_identity=identity)
    pair_pids = [[item["ProcessId"] for item in group] for group in result["private_native_groups"]]
    if len(sample["processes"]) != 3 or result["native_workers_count"] != 1 or pair_pids != [[36144, 57576]]:
        raise RuntimeError("Received pair replay differs")
    replay = write(OUTPUT / "REJEU-ECHANTILLON-PARTIEL.json", {
        "schema": "hpc-forest-windows-venv-pair-offline-replay-v1", "mode": "REPLAY_PARTIAL_PRIMARY_SAMPLE",
        "verified": False, "full_census": False, "capacity_admitted": False, "primary_sample": sample_ref,
        "runtime_identity": delivered["VENV-RUNTIME-IDENTITY.json"], "capacity_producer": delivered["capacity.py"],
        "input_rows": 3, "native_groups": 1, "group_pids_child_then_parent": pair_pids,
        "new_census_collected": False, "authorization_created": False, "executable_probes": 0})
    value = {"schema": "hpc-forest-matrix15-dynamic-extension-venv-preparation-validation-v1",
        "mode": "PREPARE", "verified": False, "sources": delivered, "source_review": delivered["REVUE-LECTURE-FRAICHE.json"],
        "pytest": {"tests": 282, "subtests": 44, "new_venv_tests": 51, "junit_counts": counts, "report": ref(report)},
        "ruff": "All checks passed using source127 configuration", "offline_partial_replay": replay,
        "post_srun_prefix_separate_dependency": ref(prefix), "original_producers_sha256": ORIGINALS,
        "native_source_127_modified": False, "source_127_files_rehashed": len(inventory),
        "first_batch_gate_received_by_this_preparation": False, "automatic_extension": False,
        "actual_cli_observed": False, "capacity_real_observed": False, "operational_authorizations_created": 0,
        "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0, "workers_started_or_stopped": 0,
        "prepared_inputs": ref(OUTPUT / "PREPARATION-NON-ADMISE/ENTREES-A-RENSEIGNER.json"),
        "arm_runtime_or_native_cell_execution_validated": False}
    validation = write(OUTPUT / "VALIDATION-LOCALE.json", value)
    manifest = write(OUTPUT / "FILES.sha256.json", {p.relative_to(OUTPUT).as_posix(): sha(p.read_bytes())
        for p in sorted(OUTPUT.rglob("*")) if p.is_file()})
    print(json.dumps({"validation": validation, "manifest": manifest, "sources": EXPECTED}))


if __name__ == "__main__":
    main()
