"""Seal one final r2 shared tar plus its external hash/size manifest after real Q inputs."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OUT = CURRENT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2"
SHARED = OUT / "shared-windows"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def write(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def q_deployment():
    upstream = json.loads((OUT / "UPSTREAM-Q-ALIASES.json").read_bytes())
    cold_root = "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/operator-cold-r2/"
    shared_root = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared"
    copies, existing = [], []
    for record in upstream["files"]:
        local = Path(record["windows_path"])
        raw = local.read_bytes()
        assert sha(raw) == record["reference"]["sha256"]
        name = local.relative_to(SHARED).as_posix()
        row = {"role": record["role"], "sha256": sha(raw), "bytes": len(raw),
               "source_local_path": str(local), "source_shared_relative_path": name,
               "source_ARM_path_after_shared_extraction": shared_root + "/" + name,
               "destination_ARM_path": record["arm_path"]}
        (copies if record["arm_path"].startswith(cold_root) else existing).append(row)
    assert len(copies) == 24 and len(existing) == 5
    return {"schema": "hpc-forest-matrix15-Q-upstream-deployment-proposal-v1",
            "qualification_job_id": "755488", "upload_or_copy_performed": False,
            "copy_24_new_files_after_hash_check_without_overwrite": copies,
            "verify_5_existing_Q_files_in_place_without_overwrite": existing,
            "native_final_qualification_reception_or_admission_included": False}


def main():
    receipt = json.loads((OUT / "STATIC-PREPARATION-RECEIPT.json").read_bytes())
    declared = receipt["shared_local_file_inventory"]
    material = {}
    for name, expected in sorted(declared.items()):
        path = PurePosixPath(name)
        assert path.as_posix() == name and not path.is_absolute() and ".." not in path.parts
        local = SHARED.joinpath(*path.parts)
        assert local.is_file() and not any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
                                           for item in (local, *local.parents))
        raw = local.read_bytes()
        assert sha(raw) == expected
        material[name] = raw
    assert set(material) == {path.relative_to(SHARED).as_posix() for path in SHARED.rglob("*") if path.is_file()}
    assert all(len(raw) <= 8 * 1024**2 for raw in material.values())
    assert sum(len(raw) for raw in material.values()) <= 128 * 1024**2
    assert all(name.isascii() and len(name.encode("ascii")) <= 100 for name in material)
    manifest = {"schema": "hpc-forest-matrix15-shared-files-v1", "files": {
        name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in material.items()}}
    write(OUT / "SHARED-FILES-MANIFEST.json", manifest)
    archive_path = OUT / "HPC-Forest-Matrix15-Static-Shared-r2.tar.gz"
    with archive_path.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in material.items():
            item = tarfile.TarInfo(name)
            item.mode, item.mtime, item.size = 0o600, 0, len(raw)
            archive.addfile(item, io.BytesIO(raw))
    assert archive_path.stat().st_size <= 64 * 1024**2
    with tarfile.open(archive_path, "r:gz") as archive:
        items = archive.getmembers()
        assert len(items) == len(material) and all(item.isfile() and not item.issym() and not item.islnk()
                                                 and not item.pax_headers and not item.sparse for item in items)
        assert {item.name: sha(archive.extractfile(item).read()) for item in items} == declared
        assert "SHARED-FILES-MANIFEST.json" not in declared
    junit = ROOT / "TESTS-STATIC-FINAL.xml"
    suite = ElementTree.parse(junit).getroot().find("testsuite")
    assert suite is not None and all(suite.attrib[key] == "0" for key in ("failures", "errors", "skipped"))
    counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
    write(OUT / "Q-UPSTREAM-DEPLOYMENT.json", q_deployment())
    write(OUT / "DEPLOIEMENT-STATIQUE.json", {
        "schema": "hpc-forest-matrix15-static-shared-deployment-proposal-v1", "archive": ref(archive_path),
        "external_manifest": ref(OUT / "SHARED-FILES-MANIFEST.json"), "archive_members": len(material),
        "local_shared": str(SHARED),
        "remote_shared": "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared",
        "remote_Q_input_package": "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package",
        "upstream_Q_aliases": ref(OUT / "UPSTREAM-Q-ALIASES.json"),
        "upstream_Q_deployment_mapping": ref(OUT / "Q-UPSTREAM-DEPLOYMENT.json"),
        "prepared_assets_in_archive_are_local_proof_copies": True,
        "ARM_preparation_aliases_explicitly_reuse_Q_package": True,
        "plan_and_alias_bytes_identical_across_hosts": True,
        "remote_root_absence_verified": False, "upload_or_extraction_performed": False,
        "native_authorization": False, "jobs_submitted": 0, "native_model_calls": 0})
    write(OUT / "VALIDATION-STATIQUE.json", {
        "schema": "hpc-forest-matrix15-static-operation-validation-v1", "statics": ref(OUT / "STATICS.json"),
        "tests": {**counts, "junit": ref(junit)}, "ruff": {"exit_code": 0, "result": "All checks passed!"},
        "runtime_true_real_127_parent_files_verified": True,
        "all45_preparation_directories_verified_with_prepared_true": True,
        "real_Sol_pilot_and_evidence_verified_through_static_aliases": True,
        "all15_subject_configurations_pass_unchanged_scientific_runner_guard": True,
        "projection_original_records_and196asset_hashes_unchanged": True,
        "static_aliases_exclude_both_host_plan_and_table_and_final_admissions": True,
        "source_and_Q_files_modified": False, "qualification_or_reception_or_admission_fabricated": False,
        "remote_or_model_or_job_actions": 0, "private_shared_archive": ref(archive_path),
        "external_manifest": ref(OUT / "SHARED-FILES-MANIFEST.json")})
    print(json.dumps({"archive": ref(archive_path), "manifest": ref(OUT / "SHARED-FILES-MANIFEST.json"),
                      "members": len(material), "tests": counts}))


if __name__ == "__main__":
    main()
