"""Pure local immutable matrix15 statics; never create a qualification or admission."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

CURRENT = Path("C:/Users/nicol/Documents/Codex/2026-10-19/je-voudrais-que-tu-commit-et")
PARENT = CURRENT / "work/matrix15-admission-no-cycle-r2/project"
PARENT_OUTPUT = CURRENT / "outputs/HPC-Forest-Matrice15-Admission-r2"
QPACKAGE = CURRENT / "outputs/HPC-Forest-Q15-Pilote-Unique-r2/paquet"
OUTPUT = CURRENT / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r1"
SHARED_ARM = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared"
QPACKAGE_ARM = "/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01/package"
SOL = Path("C:/Users/nicol/Documents/Codex/2026-10-19/c-users-nicol-documents-codex-2026-4/outputs/HPC-Forest-R2-Reprise-20261019-r1/LIBERATION-SCIENTIFIQUE-SOL-COMPLETE.json")
NATIVE_ZIP_SHA = "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
PROTOCOL_SHA = "ae2ccbb8d10f54d022bb95248412d0fba8751b8f1c97196336e6e6b9f1fb08b2"
ORIGINAL_PREP_SHA = "829a1e96066218f08724f684f7f006935ba6f39c146141a7e918fc62e2f73963"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, digest=None):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or any(item.is_symlink() or getattr(item, "is_junction", lambda: False)()
                                                         for item in (path, *path.parents)):
        raise ValueError("Physical absolute input required: " + str(path))
    raw = path.read_bytes()
    if digest is not None and sha(raw) != digest:
        raise ValueError("Input SHA differs: " + str(path))
    return raw


def reference(path):
    return {"path": str(path), "sha256": sha(checked(path))}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    return reference(path)


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(checked(path))
    return result


def preparation_prefix(canonical):
    if not isinstance(canonical, str) or canonical.count("/preparation/") != 1:
        raise ValueError("Explicit original preparation path required")
    result = "preparation/" + canonical.split("/preparation/", 1)[1]
    path = PurePosixPath(result)
    if path.is_absolute() or str(path) != result or ".." in path.parts:
        raise ValueError("Unsafe preparation prefix")
    return result


def main():
    if OUTPUT.exists():
        raise FileExistsError("Preserve the existing static edition")
    original_runtime_raw = checked(PARENT_OUTPUT / "RUNTIME-PRIVE-LOCAL.json")
    original_runtime = json.loads(original_runtime_raw)
    if len(original_runtime) != 127 or inventory(PARENT) != original_runtime:
        raise ValueError("Reviewed native parent runtime differs")
    native_zip = PARENT_OUTPUT / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"
    checked(native_zip, NATIVE_ZIP_SHA)
    protocol_file = PARENT_OUTPUT / "PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"
    checked(protocol_file, PROTOCOL_SHA)
    original_preparation_file = QPACKAGE / "evidence/prepared-r1-manifest.json"
    original_preparation_raw = checked(original_preparation_file, ORIGINAL_PREP_SHA)
    original_preparation = json.loads(original_preparation_raw)
    qplan = json.loads(checked(QPACKAGE / "PLAN-Q15.json"))
    qoriginals = json.loads(checked(QPACKAGE / "LOCAL-ORIGINAL-REFERENCES.json"))
    original_refs = {row["package_member"]: row["original"] for row in qoriginals["files"]}
    sys.path.insert(0, str(PARENT / "src"))
    from hpc_forest import matrix15_contract as contract
    from hpc_forest import native_matrix15 as native
    from hpc_forest.core import digest

    native.verify_runtime(native_zip, PARENT_OUTPUT / "RUNTIME-PRIVE-LOCAL.json")
    native.verify_primes_release(SOL)
    OUTPUT.mkdir()
    shared = OUTPUT / "shared-windows"
    shared.mkdir()
    files, entries, by_canonical = {}, [], {}

    def copy_file(source, relative, *, canonical=None, arm=None, expected=None, alias=True):
        source = Path(source)
        raw = checked(source, expected)
        destination = shared.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(raw)
        files[relative] = sha(raw)
        canonical = str(source) if canonical is None else canonical
        arm = SHARED_ARM + "/" + relative if arm is None else arm
        if alias:
            if canonical in by_canonical:
                raise ValueError("Duplicate canonical static alias")
            entry = {"kind": "file", "canonical_path": canonical, "windows_path": str(destination),
                     "arm_path": arm, "sha256": sha(raw)}
            entries.append(entry)
            by_canonical[canonical] = entry
        return {"path": canonical, "sha256": sha(raw)}

    # The native runtime remains exactly127files; the Q derivative is never copied as native.
    for name, checksum in original_runtime.items():
        copy_file(PARENT / name, "project/" + name, expected=checksum, alias=False)
    native_zip_ref = copy_file(native_zip, "native-source.zip", expected=NATIVE_ZIP_SHA)
    runtime_ref = copy_file(PARENT_OUTPUT / "RUNTIME-PRIVE-LOCAL.json", "runtime-manifest.json")
    protocol_ref = copy_file(protocol_file, "protocol.json", expected=contract.PROTOCOL_SHA256)
    harness_ref = copy_file(PARENT / "examples/marathon22/harness-mixed.json", "harness-mixed.json",
                            expected=contract.HARNESS_SHA256)
    r1_ref = original_refs["evidence/contrats-reference.json"]
    r1_contracts_ref = copy_file(QPACKAGE / "evidence/contrats-reference.json", "r1-contracts.json",
                               canonical=r1_ref["path"], expected=contract.R1_CONTRACTS_SHA256)
    old_preparation_ref = original_refs["evidence/prepared-r1-manifest.json"]
    copy_file(original_preparation_file, "evidence/original-preparation.json",
              canonical=old_preparation_ref["path"], expected=ORIGINAL_PREP_SHA)
    statement_refs = {}
    for year in ("2020", "2021", "2022", "2023"):
        old_ref = original_refs["statements/" + year + ".txt"]
        statement_refs[year] = copy_file(QPACKAGE / ("statements/" + year + ".txt"), "statements/" + year + ".txt",
                                        canonical=old_ref["path"], expected=old_ref["sha256"])
    prepared_files, rows, prepared_contract_refs = {}, {}, {}
    for subject in contract.SUBJECTS:
        record = copy.deepcopy(original_preparation["records"][subject])
        if record["status"] != "ready":
            raise ValueError("Original R1 subject is not ready")
        source_path = PurePosixPath(record["prepared"]["source"])
        validation_path = PurePosixPath(record["prepared"]["validation"])
        if source_path.parent != validation_path.parent:
            raise ValueError("Original source/validation parents differ")
        rows[subject] = {"record": record, "official": str(source_path.parent)}
        for role in ("source", "validation"):
            prefix = preparation_prefix(record["prepared"][role])
            expected = {name[len(prefix) + 1:]: checksum for name, checksum in original_preparation["files"].items()
                        if name.startswith(prefix + "/")}
            package_root = QPACKAGE / qplan["subjects"][subject][role]
            if inventory(package_root) != expected:
                raise ValueError("Exact196 asset projection changed or contains extras: " + subject + "/" + role)
            for name, checksum in expected.items():
                prepared_files[prefix + "/" + name] = checksum
                if role == "validation" and name == "contract.json":
                    original_ref = qplan["subjects"][subject]["r1_contract_reference"]
                    prepared_contract_refs[subject] = copy_file(package_root / name,
                        "prepared/" + subject + "/validation/contract.json", canonical=original_ref["path"],
                        arm=QPACKAGE_ARM + "/prepared/" + subject + "/validation/contract.json", expected=original_ref["sha256"])
                else:
                    copy_file(package_root / name, "prepared/" + subject + "/" + role + "/" + name,
                              expected=checksum, alias=False)
    if len(prepared_files) != 196:
        raise ValueError("Exactly196 official source/validation assets required")
    projection = {"schema": "hpc-forest-matrix15-preparation-static-projection-v1",
                  "upstream_original_preparation": old_preparation_ref,
                  "projection_scope": "exact196official-source-validation-assets-only-no-builds-or-candidates",
                  "records": {subject: rows[subject]["record"] for subject in contract.SUBJECTS},
                  "files": prepared_files}
    preparation_path = shared / "preparation-196.json"
    preparation_ref = write_json(preparation_path, projection)
    files["preparation-196.json"] = preparation_ref["sha256"]
    entries.append({"kind": "file", "canonical_path": str(preparation_path), "windows_path": str(preparation_path),
                    "arm_path": SHARED_ARM + "/preparation-196.json", "sha256": preparation_ref["sha256"]})
    for subject in contract.SUBJECTS:
        for role, canonical in (("official", rows[subject]["official"]),
                                ("source", rows[subject]["record"]["prepared"]["source"]),
                                ("validation", rows[subject]["record"]["prepared"]["validation"])):
            prefix = preparation_prefix(canonical)
            subset = {name[len(prefix) + 1:]: checksum for name, checksum in prepared_files.items() if name.startswith(prefix + "/")}
            suffix = "" if role == "official" else "/" + role
            entries.append({"kind": "directory", "subject_id": subject, "role": role,
                "canonical_path": canonical, "windows_path": str(shared / "prepared" / subject) + suffix,
                "arm_path": QPACKAGE_ARM + "/prepared/" + subject + suffix,
                "inventory_prefix": prefix, "inventory_sha256": digest(subset)})
    sol_ref = copy_file(SOL, "evidence/sol/release.json", expected=native.SOL_PILOT_RELEASE_SHA256)
    sol = json.loads(checked(SOL))
    for number, proof in enumerate(sol["evidence_refs"], 1):
        copy_file(proof["path"], "evidence/sol/" + str(number).zfill(2) + "-" + Path(proof["path"]).name,
                  expected=proof["sha256"])
    external = next(proof for proof in sol["evidence_refs"] if proof["sha256"] == native.SOL_PILOT_EXTERNAL_AUDIT_SHA256)
    measurement = json.loads(checked(external["path"], external["sha256"]))
    copy_file(measurement["archive"]["path"], "evidence/sol/independent-measurement.tar.gz",
              expected=measurement["archive"]["sha256"])
    aliases = {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": contract.SCOPE,
               "source_zip_sha256": NATIVE_ZIP_SHA, "preparation_manifest_sha256": preparation_ref["sha256"],
               "entries": entries}
    native.validate_aliases(aliases, NATIVE_ZIP_SHA)
    aliases_path = shared / "artifact-aliases.json"
    aliases_ref = write_json(aliases_path, aliases)
    subjects = {}
    for subject in contract.SUBJECTS:
        original_config = json.loads(checked(QPACKAGE / qplan["subjects"][subject]["config"]))
        config = copy.deepcopy(original_config)
        config["codex"] = {"model": "{cell.model}", "reasoning_effort": "max", "transport": "codex-mailbox"}
        subjects[subject] = {"subject_id": subject, "official_preparation_path": rows[subject]["official"],
            "preparation_sha256": digest(rows[subject]["record"]), "r1_contract_ref": prepared_contract_refs[subject],
            "statement_ref": statement_refs[subject[:4]], "prepared_contract_ref": prepared_contract_refs[subject],
            "qualification_ref": None, "reception_ref": None, "config": config}
    plan = {"schema": "hpc-forest-matrix15-native-max-plan-v2", "scope_id": contract.SCOPE,
        "protocol": protocol_ref, "models": list(contract.MODELS), "efforts": [contract.EFFORT],
        "subjects": list(contract.SUBJECTS), "cells": copy.deepcopy(list(contract.REGISTERED_CELLS.values())),
        "subject_bindings": subjects, "source_zip_sha256": NATIVE_ZIP_SHA, "runtime_manifest": runtime_ref,
        "preparation_manifest": preparation_ref, "artifact_aliases": aliases_ref,
        "r1_contracts": r1_contracts_ref, "harness": harness_ref, "primes_release": sol_ref,
        "maximum_native_workers_total": 4, "maximum_cells_per_authorization": 1,
        "budgets_per_cell": copy.deepcopy(contract.BUDGETS), "target": copy.deepcopy(contract.TARGET),
        "automatic_extension": False, "scientific_contract": "exact-R1-harness-mixed-calibration-only-excluded",
        "exclusive_deadline_utc": "2026-10-31T23:00:00Z", "reception_audit_reserve_seconds": 10800}
    contract.validate_plan(plan)
    plan_path = shared / "plan-60-v2.json"
    plan_ref = write_json(plan_path, plan)
    native.validate_alias_dependencies(aliases, plan_ref, aliases_ref, [])
    static_artifacts = {"plan": plan_ref, "source_zip": native_zip_ref, "runtime_manifest": runtime_ref,
                        "preparation_manifest": preparation_ref, "r1_contracts": r1_contracts_ref,
                        "harness": harness_ref, "artifact_aliases": aliases_ref, "primes_release": sol_ref}
    write_json(OUTPUT / "STATICS.json", {"schema": "hpc-forest-matrix15-native-static-package-v1", "artifacts": static_artifacts})
    windows = {key: native.alias_reference(value, aliases, platform="windows") for key, value in static_artifacts.items()}
    arm = {key: native.alias_reference(value, aliases, platform="arm") for key, value in static_artifacts.items()}
    arm["plan"] = {"path": SHARED_ARM + "/plan-60-v2.json", "sha256": plan_ref["sha256"]}
    arm["artifact_aliases"] = {"path": SHARED_ARM + "/artifact-aliases.json", "sha256": aliases_ref["sha256"]}
    write_json(OUTPUT / "STATIC-ARTIFACTS-WINDOWS.json", windows)
    write_json(OUTPUT / "STATIC-ARTIFACTS-ARM.json", arm)
    first_cell = next(cell for cell in contract.REGISTERED_CELLS.values()
                      if cell["model"] == "gpt-6-luna" and cell["subject_id"] == "2020-quicksort")
    first = {"schema": "hpc-forest-matrix15-first-native-cell-preparation-v1", "cell": first_cell,
             "proposed_remote_root": "/gpfs/scratch/nimarano/" + contract.SCOPE + "-" + first_cell["session_id"],
             "shared_windows": str(shared), "shared_arm": SHARED_ARM, "job_id": None,
             "qualification_and_reception_ready": False, "native_authorization": False,
             "native_model_calls": 0, "jobs_submitted": 0}
    write_json(OUTPUT / "FIRST-CELL-PREPARATION.json", first)
    for host, upstream in (("WINDOWS", windows), ("ARM", arm)):
        draft = {"schema": "hpc-forest-matrix15-authorization-v1", "scope_id": contract.SCOPE, **first_cell,
            "verified": False, "expires_at": None, "user_messages": json.loads(checked(protocol_file))["human_messages"],
            "old_candidates_imported": False, "operator_algorithm_advice": False,
            "native_calls_started_at_authorization": 0, "job_id": None, "remote_root": first["proposed_remote_root"],
            "artifacts": {key: upstream.get(key) for key in native.ARTIFACTS}}
        write_json(OUTPUT / ("AUTHORIZATION-DRAFT-" + host + ".json"), draft)
    projection_receipt = {"schema": "hpc-forest-matrix15-static-preparation-projection-receipt-v1",
        "original_preparation": old_preparation_ref, "projection": preparation_ref,
        "original_records_identical": all(rows[s]["record"] == original_preparation["records"][s] for s in contract.SUBJECTS),
        "selected_records": list(contract.SUBJECTS), "included_asset_count": len(prepared_files),
        "included_files": prepared_files,
        "excluded_original_files": sorted(set(original_preparation["files"]) - set(prepared_files)),
        "Q_source_package": reference(CURRENT / "outputs/HPC-Forest-Q15-Pilote-Unique-r2/HPC-Forest-Q15-baseline-source-r1.tar.gz"),
        "Q_source_plan": reference(QPACKAGE / "PLAN-Q15.json"),
        "Q_source_assets_byte_identical": True, "actual_Q_cold_audit": None,
        "new_or_independently_requalified_content_claimed": False, "native_authorization": False}
    write_json(OUTPUT / "PROJECTION-PREPARATION-196.json", projection_receipt)
    for subject in contract.SUBJECTS:
        for role in ("official", "source", "validation"):
            canonical = rows[subject]["official"] if role == "official" else rows[subject]["record"]["prepared"][role]
            native.directory_artifact(canonical, subject_id=subject, role=role,
                preparation_manifest=projection, preparation_manifest_sha256=preparation_ref["sha256"],
                aliases=aliases, platform="windows", verify=True)
    native.verify_primes_release(Path(windows["primes_release"]["path"]),
                                read_ref=lambda value: native.artifact(value, aliases=aliases))
    if inventory(PARENT) != original_runtime or checked(original_preparation_file) != original_preparation_raw:
        raise ValueError("Preserved inputs changed")
    write_json(OUTPUT / "STATIC-PREPARATION-RECEIPT.json", {
        "schema": "hpc-forest-matrix15-static-operation-local-preparation-v1", "statics": reference(OUTPUT / "STATICS.json"),
        "first_cell": first_cell, "plan_sha256": plan_ref["sha256"], "aliases_sha256": aliases_ref["sha256"],
        "projection_sha256": preparation_ref["sha256"], "native_source_zip_sha256": NATIVE_ZIP_SHA,
        "runtime_files": 127, "prepared_assets": 196, "directory_aliases_verified_locally": 45,
        "static_aliases_upstream_only": True, "qualification_and_reception_refs_in_plan_all_null": True,
        "original_native_and_Q_sources_modified": False, "actual_Q_cold_audit": None,
        "qualification_or_admission_created": False, "remote_state_verified": False,
        "jobs_submitted": 0, "native_model_calls": 0, "launch_ready": False,
        "shared_local_file_inventory": inventory(shared)})
    print(json.dumps({"statics": str(OUTPUT / "STATICS.json"), "plan": plan_ref,
                      "aliases": aliases_ref, "projection": preparation_ref, "first_cell": first_cell}))


if __name__ == "__main__":
    main()
