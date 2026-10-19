"""Inspect the new local package as data, then emit concrete inputs for ROOT."""
from __future__ import annotations

import hashlib
import json
import shlex
import tarfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OUT = CURRENT / "outputs/HPC-Forest-Q15-Pilote-Unique-r1"
PACKAGE = OUT / "paquet"
OLD = Path("C:/Users/nicol/Documents/Codex/2026-10-19/c-users-nicol-documents-codex-2026-4")
OLD_PACKAGE = OLD / "outputs/HPC-Forest-R2-Matrice15-Qualification-Preparation-r1/edition-r2/paquet"
PROJECT = CURRENT / "work/matrix15-single-pilot-r1/project"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def write(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


receipt = json.loads((OUT / "PREPARATION-Q15.json").read_bytes())
archive_path = Path(receipt["archive"]["path"])
assert sha(archive_path.read_bytes()) == receipt["archive"]["sha256"]
with tarfile.open(archive_path, "r:gz") as archive:
    rows = archive.getmembers()
    assert len(rows) == 353
    material = {}
    for row in rows:
        path = PurePosixPath(row.name)
        assert row.isfile() and not row.issym() and not row.islnk()
        assert path.as_posix() == row.name and not path.is_absolute() and ".." not in path.parts
        assert "\\" not in row.name and ":" not in row.name and row.name not in material
        stream = archive.extractfile(row)
        assert stream is not None
        raw = stream.read()
        assert len(raw) == row.size
        material[row.name] = raw
assert len({name.casefold() for name in material}) == len(material)
manifest = json.loads(material["PACKAGE-MANIFEST.json"])
actual = {name: sha(raw) for name, raw in material.items() if name != "PACKAGE-MANIFEST.json"}
assert actual == manifest["files"]
assert all((PACKAGE / name).read_bytes() == raw for name, raw in material.items())
plan = json.loads(material["PLAN-Q15.json"])
old_plan = json.loads((OLD_PACKAGE / "PLAN-Q15.json").read_bytes())
scientific = dict(plan)
binding = scientific.pop("source_bindings")
assert scientific == old_plan
assert binding["parent_runtime_manifest_sha256"] == sha(material["ORIGINAL-RUNTIME-MANIFEST.json"])
assert binding["q_runtime_manifest_sha256"] == sha(material["RUNTIME-Q-MANIFEST.json"])
parent = json.loads(material["ORIGINAL-RUNTIME-MANIFEST.json"])
assert len(parent) == 126 and all(sha((PROJECT / name).read_bytes()) == digest for name, digest in parent.items())
runtime = json.loads(material["RUNTIME-Q-MANIFEST.json"])
assert len(runtime) == 127
assert all(sha(material["project-q/" + name]) == digest for name, digest in runtime.items())

historical = []
for subject in plan["subject_order"]:
    contract_name = plan["subjects"][subject]["validation"] + "/contract.json"
    contract = json.loads(material[contract_name])
    config_name = plan["subjects"][subject]["config"]
    config = json.loads(material[config_name])
    historical.append({"subject": subject, "historical_reference_seconds": contract["benchmark"]["reference_seconds"],
                       "timeout_seconds_per_command": config["protocol"]["timeout_seconds"],
                       "confirmation_repetitions": config["protocol"]["confirmation_repetitions"],
                       "warmups": config["protocol"]["warmups"],
                       "contract": {"package_member": contract_name, "sha256": sha(material[contract_name])}})
reference_sum = sum(row["historical_reference_seconds"] for row in historical)
write(OUT / "REFERENCES-TEMPS-R1-HISTORIQUES.json", {
    "schema": "hpc-forest-Q15-historical-budget-context-v1", "rows": historical,
    "sum_historical_reference_seconds": reference_sum,
    "six_times_sum_historical_reference_seconds": reference_sum * 6,
    "new_measurements": False, "runtime_sufficiency_proved": False,
    "interpretation": "Historical benchmark values only; compilation, correctness folds, provenance, I/O and current machine costs remain outside this simple sum.",
})
remote_root = "/scratch_p/nimarano/hpc-forest-q15-single-pilot-20261019-r1-" + receipt["archive"]["sha256"][:12]
remote_package = remote_root + "/package"
remote_output = remote_root + "/result-Q15"
python = "/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python"
argv = [python, "-B", remote_package + "/qualify15.py", "--package", remote_package,
        "--plan", remote_package + "/PLAN-Q15.json", "--plan-sha256", receipt["plan"]["sha256"],
        "--output", remote_output, "--maximum-seconds", "1800"]
command = ("set -euo pipefail\n"
           "export PYTHONDONTWRITEBYTECODE=1\n"
           "export PYTHONPYCACHEPREFIX=" + shlex.quote(remote_root + "/no-pycache-before-Q") + "\n"
           "export OPENBLAS_NUM_THREADS=1\nexport OMP_NUM_THREADS=4\n"
           + shlex.join(argv) + "\n")
with (OUT / "COMMANDE-QUALIFICATION-ARM.sh").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(command)
write(OUT / "INPUTS-QUALIFICATION-ARM.json", {
    "schema": "hpc-forest-Q15-single-pilot-root-reviewed-inputs-v1", "status": "prepared_only_not_transferred_or_submitted",
    "local_archive": receipt["archive"], "local_plan": receipt["plan"],
    "package_manifest": receipt["package_manifest"], "source_bindings": binding,
    "member_count": 353, "remote_root": remote_root, "remote_package": remote_package,
    "remote_output": remote_output, "remote_archive_upload_proposal": "/scratch_p/nimarano/HPC-Forest-Q15-single-pilot-" + receipt["archive"]["sha256"][:12] + ".tar.gz",
    "remote_roots_absent_proved": False, "remote_upload_verified": False,
    "python_existing_historical_path": python,
    "environment_recipe": ["romeo_load_armgpu_env", "spack load /zrtbeqke25s2vbqo4yrhsowjz7mg3pjf"],
    "environment_recipe_note": "Historical zrt spec is Python3.12.5; it is not a GCC spec. Actual compiler must be observed in the allocation.",
    "argv": argv, "command": ref(OUT / "COMMANDE-QUALIFICATION-ARM.sh"),
    "resources": {"architecture": "aarch64", "nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0},
    "qualification_maximum_seconds_shared_across_fifteen": 1800,
    "collection_reserve_seconds": 120, "proposed_job_seconds": 2100,
    "reception_audit_reserve_seconds": 10800, "exclusive_deadline_utc": "2026-10-31T23:00:00Z",
    "qualification_guard_allowed_seconds_unchanged": [60, 7200],
    "external_execution_timeout_required_seconds": 1920,
    "external_timeout_or_scheduler_control_in_command": False,
    "timeout_note": "ROOT must bound the command externally and preserve logs, intent and negative on timeout; runner alone does not enforce collection120s.",
    "environment_and_file_hashes_still_need_live_verification": True,
    "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0,
})
tests_path = ROOT / "TESTS-Q15-NEUTRES-r1.xml"
suite = ElementTree.parse(tests_path).getroot().find("testsuite")
assert suite is not None
counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
write(OUT / "VALIDATION-PAQUET-LOCAL.json", {
    "schema": "hpc-forest-Q15-single-pilot-package-local-validation-v1", "archive": receipt["archive"],
    "plan": receipt["plan"], "package_manifest": receipt["package_manifest"],
    "exact_archive_and_disk_members": 353, "regular_unique_safe_members_verified": True,
    "package_manifest_hashes_verified": True, "runtime_Q_files": 127, "parent_source_files": 126,
    "parent_private_source_rehashed_unchanged": True,
    "scientific_plan_fields_identical_to_previous_edition": True,
    "sole_new_plan_field": "source_bindings", "source_bindings_verified_before_runtime_import": True,
    "tests": {**counts, "junit": ref(tests_path), "subtests_passed": 19},
    "ruff": {"exit_code": 0, "result": "All checks passed!", "scope": "five Q prepare/runner/contract/test files"},
    "instructions": ref(OUT / "INPUTS-QUALIFICATION-ARM.json"),
    "qualification_executed": False, "qualification_ready": False, "native_authorization": False,
    "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0,
})
print(json.dumps({"archive": receipt["archive"], "plan": receipt["plan"], "remote_root": remote_root,
                  "historical_reference_seconds_sum": reference_sum, "tests": counts}))
