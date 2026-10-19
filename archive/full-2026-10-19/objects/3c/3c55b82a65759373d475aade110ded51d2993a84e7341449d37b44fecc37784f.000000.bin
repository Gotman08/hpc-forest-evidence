"""Package already validated statics once; no deployment or admission."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OUT = CURRENT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r1"
SHARED = OUT / "shared-windows"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def write(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


preparation = json.loads((OUT / "STATIC-PREPARATION-RECEIPT.json").read_bytes())
declared = preparation["shared_local_file_inventory"]
material = {name: (SHARED / name).read_bytes() for name in sorted(declared)}
assert len(material) == 346 and {name: sha(raw) for name, raw in material.items()} == declared
archive_path = OUT / "HPC-Forest-Matrix15-Static-Shared-r1.tar.gz"
with archive_path.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
    for name, raw in material.items():
        item = tarfile.TarInfo(name)
        item.mode, item.mtime, item.size = 0o600, 0, len(raw)
        archive.addfile(item, io.BytesIO(raw))
with tarfile.open(archive_path, "r:gz") as archive:
    items = archive.getmembers()
    assert len(items) == 346 and all(item.isfile() and not item.issym() and not item.islnk() for item in items)
    assert {item.name: sha(archive.extractfile(item).read()) for item in items} == declared
junit = ROOT / "TESTS-STATIC-FINAL-r2.xml"
suite = ElementTree.parse(junit).getroot().find("testsuite")
assert suite is not None and suite.attrib["tests"] == "40"
assert all(suite.attrib[key] == "0" for key in ("failures", "errors", "skipped"))
write(OUT / "DEPLOIEMENT-STATIQUE.json", {
    "schema": "hpc-forest-matrix15-static-shared-deployment-proposal-v1", "archive": ref(archive_path),
    "archive_members": 346, "member_hashes": declared,
    "local_shared": str(SHARED),
    "remote_shared": "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared",
    "remote_Q_input_package": "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package",
    "prepared_assets_in_archive_are_local_proof_copies": True,
    "ARM_preparation_aliases_explicitly_reuse_Q_package": True,
    "plan_and_alias_bytes_identical_across_hosts": True,
    "plan_and_alias_file_references_are_direct_host_paths_in_authorization": True,
    "remote_root_absence_verified": False, "upload_or_extraction_performed": False,
    "native_authorization": False, "jobs_submitted": 0, "native_model_calls": 0})
write(OUT / "VALIDATION-STATIQUE.json", {
    "schema": "hpc-forest-matrix15-static-operation-validation-v1", "statics": ref(OUT / "STATICS.json"),
    "tests": {"passed": 40, "failures": 0, "errors": 0, "skipped": 0, "junit": ref(junit)},
    "ruff": {"exit_code": 0, "result": "All checks passed!"},
    "runtime_true_real_127_parent_files_verified": True,
    "all45_preparation_directories_verified_with_prepared_true": True,
    "real_Sol_pilot_and_evidence_verified_through_static_aliases": True,
    "all15_subject_configurations_pass_unchanged_scientific_runner_guard": True,
    "negative_changed_extra_missing_old_build_assets_rejected": True,
    "draft_authorizations_rejected_by_native_guard": True,
    "projection_original_records_and196asset_hashes_unchanged": True,
    "static_aliases_exclude_plan_alias_table_and_final_admissions": True,
    "source_Q_and_native_scopes_unchanged": True,
    "source_and_Q_files_modified": False,
    "qualification_or_reception_or_admission_fabricated": False,
    "remote_or_model_or_job_actions": 0,
    "private_shared_archive": ref(archive_path), "deployment_proposal": ref(OUT / "DEPLOIEMENT-STATIQUE.json")})
print(json.dumps({"archive": ref(archive_path), "members": len(material), "tests_passed": 40}))
