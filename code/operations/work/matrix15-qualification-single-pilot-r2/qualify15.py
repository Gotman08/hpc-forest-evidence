"""Allocated baseline-only Q15: no Controller instance, Mother, worker or model."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import tarfile
import time
from dataclasses import asdict
from pathlib import Path

from qualification_contract import (
    SCOPE,
    SUBJECTS,
    allocation_guard,
    artifact,
    data,
    need,
    read,
    sha,
    verify_source_bindings,
)


def save(path, value):
    with Path(path).open("xb") as stream:
        stream.write(data(value))
    return {"path": str(path), "sha256": sha(Path(path).read_bytes())}


def inventory(root):
    rows = {}
    for path in sorted(Path(root).rglob("*")):
        need(not path.is_symlink(), "Linked qualification source/evidence member refused")
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return rows


def policy_for(subject, job, root, plan_sha, runtime_sha, contract_sha, preparation_sha):
    return {"mode": "command-stream-v1", "qualification_binding": {
        "schema": "hpc-forest-matrix15-qualification-binding-v1", "scope_id": SCOPE,
        "subject_id": subject, "job_id": job, "remote_root": str(root), "seed": 23,
        "prepared_manifest_sha256": preparation_sha, "r1_contract_sha256": contract_sha,
        "native_authorization": False}, "source_runtime_sha256": runtime_sha,
        "subject_contract_sha256": contract_sha, "qualification_protocol_sha256": plan_sha}


def qualification_settings(original, policy, target):
    settings = json.loads(json.dumps(original))
    need(settings.get("problem") == policy["qualification_binding"]["subject_id"]
         and settings.get("seed") == 23 and settings.get("backend") == "codex"
         and settings.get("protocol", {}).get("confirmation_repetitions") == 5,
         "Paired R1 subject/seed/backend/five-confirmation precondition differs")
    # Only inactive model/deployment metadata and explicit Q observability differ.
    settings["codex"] = {"transport": "codex-mailbox", "model": None}
    settings["target_id"] = target
    settings.pop("compiler", None)  # create_workspace records this allocation's actual compiler.
    settings["execution_provenance"] = policy
    return settings


def run(plan_ref, package, output, maximum_seconds):
    allocation = allocation_guard(maximum_seconds)
    package, output = Path(package), Path(output)
    need(package.is_absolute() and package.resolve(strict=True) == package and package.is_dir(),
         "Canonical qualification package directory required")
    need(output.is_absolute() and output.parent.resolve(strict=True) == output.parent and not output.exists()
         and not output.is_relative_to(package), "Unique disjoint qualification output required")
    plan_path, plan_raw = artifact(plan_ref)
    need(plan_path == package / "PLAN-Q15.json", "Exact package plan path required")
    plan = read(plan_raw)
    need(plan.get("schema") == "hpc-forest-matrix15-baseline-qualification-plan-v1"
         and plan.get("scope_id") == SCOPE and plan.get("subject_order") == list(SUBJECTS)
         and plan.get("native_authorization") is False and plan.get("native_model_calls") == 0,
         "Closed baseline-only qualification plan required")
    manifest_raw = (package / "PACKAGE-MANIFEST.json").read_bytes()
    manifest = read(manifest_raw)
    expected = dict(manifest["files"])
    actual = inventory(package)
    actual.pop("PACKAGE-MANIFEST.json")
    need(actual == expected, "Qualification package changed or contains extra files/cache")
    runtime = package / "project-q"
    runtime_manifest_raw = (package / "RUNTIME-Q-MANIFEST.json").read_bytes()
    source_binding = verify_source_bindings(plan,
        (package / "ORIGINAL-RUNTIME-MANIFEST.json").read_bytes(), runtime_manifest_raw)
    need(inventory(runtime) == read(runtime_manifest_raw), "Dedicated Q runtime source inventory changed")
    need(plan.get("asset_counts") == {"source": 46, "validation": 150, "total": 196},
         "Exactly196R1whitelisted assets required")
    output.mkdir(exist_ok=False)
    save(output / "INTENT-ONE-Q15.json", {"schema": "hpc-forest-matrix15-baseline-qualification-intent-v1",
         "scope_id": SCOPE, "allocation": allocation, "plan": plan_ref,
         "maximum_seconds": maximum_seconds, "native_authorization": False,
         "native_model_calls": 0, "attempt": 1, "retry": False})
    result = {"schema": "hpc-forest-matrix15-baseline-qualification-result-v1", "scope_id": SCOPE,
        "allocation": allocation, "plan": plan_ref, "qualification_complete": False, "qualified_subjects": [],
        "source_bindings": source_binding,
        "subjects": {}, "native_authorization": False, "native_model_calls": 0,
        "Controller_instances": 0, "Mother_instances": 0, "native_workers_started": 0,
        "individual_case_provenance_verified": False, "independent_raw_stdout_per_candidate_verified": False,
        "independent_performance_audit_verified": False, "scientific_gain_claimed": False,
        "old_candidates_or_reference_binaries_imported": False}
    started = time.time()
    saved_prefix, saved_bytecode = sys.pycache_prefix, sys.dont_write_bytecode
    try:
        cache = output / "pycache-must-remain-absent"
        need(not cache.exists(), "Fresh absent cache prefix required")
        sys.dont_write_bytecode, sys.pycache_prefix = True, str(cache)
        os.environ.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache),
                          GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                          GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT="0")
        need(not any(name == "hpc_forest" or name.startswith("hpc_forest.") for name in sys.modules),
             "Qualification requires a fresh interpreter before verified runtime imports")
        sys.path.insert(0, str(runtime / "src"))
        need(importlib.metadata.version("treequest") == "0.3.2", "Existing R1TreeQuest0.3.2 required")
        from hpc_forest.controller import create_workspace
        from hpc_forest.core import protected_manifest
        from hpc_forest.evaluator import Evaluator
        from hpc_forest.matrix15_provenance import command_stream_provenance
        from hpc_forest.registry import Registry

        for subject in SUBJECTS:
            need(time.time() < started + maximum_seconds, "Qualification deadline reached; no restart/reset")
            row = plan["subjects"][subject]
            original = read((package / row["config"]).read_bytes())
            source, validation = package / row["source"], package / row["validation"]
            contract = validation / "contract.json"
            need(sha(contract.read_bytes()) == row["r1_contract_sha256"], "Exact paired R1 checker contract changed")
            policy = policy_for(subject, allocation["job_id"], output, plan_ref["sha256"],
                                sha(runtime_manifest_raw), row["r1_contract_sha256"], plan["preparation_sha256"])
            settings = qualification_settings(original, policy,
                "romeo:slurm-" + allocation["job_id"] + ":Q15-baseline-cpu4")
            campaign = output / subject
            create_workspace(campaign, settings, source, validation)
            db = Registry(campaign / "registry.sqlite3")
            try:
                settings = db.get("config")
                db.set("started", started)
                db.set("deadline", started + maximum_seconds)
                db.set("qualification_only", True)
                epoch = db.one("SELECT * FROM epochs WHERE id=1")
                commit, protocol_id = epoch["base_commit"], db.get("protocol_id")
                evaluator = Evaluator(campaign, settings, protected_manifest(campaign / "trusted"),
                                      protocol_id, started + maximum_seconds)
                precheck = asdict(evaluator.precheck("baseline-e1", 1, campaign / "repo", commit))
                db.record_evaluation("baseline-e1", 1, "qualification_precheck", precheck)
                need(precheck["status"] == "development_valid" and precheck["correct"] is True
                     and precheck["times"] == [], "Official baseline research-fold precheck failed")
                precheck_proof = command_stream_provenance(precheck, "baseline-e1",
                    expected_policy=policy, protocol_id=protocol_id)
                db.reserve("confirmation", "Q15 official baseline only; zero model tokens", 0)
                confirmed = evaluator.confirm([{"id": "baseline-e1", "worktree": str(campaign / "repo"),
                                                "commit": commit, "baseline": True}], 1)
                outcome = asdict(confirmed["baseline-e1"])
                db.record_evaluation("baseline-e1", 1, "confirmation", outcome)
                need(outcome["status"] == "valid" and outcome["correct"] is True
                     and len(outcome["times"]) == 5 and all(type(t) in {int, float} and math.isfinite(t) and t > 0
                                                           for t in outcome["times"]), "Official baseline five-confirmation failed")
                confirmation_proof = command_stream_provenance(outcome, "baseline-e1",
                    expected_policy=policy, protocol_id=protocol_id)
                costs = db.costs()
                need(costs["tokens_used"] == costs["tokens_reserved"] == costs["unknown_usage_calls"] == 0,
                     "Qualification must have zero model usage")
                result["subjects"][subject] = {"baseline_qualified": True, "policy": policy, "protocol_id": protocol_id,
                    "precheck": precheck, "confirmation": outcome, "precheck_command_streams": precheck_proof,
                    "confirmation_command_streams": confirmation_proof, "costs": costs,
                    "r1_contract_sha256": row["r1_contract_sha256"], "case_counts": row["case_counts"]}
                result["qualified_subjects"].append(subject)
            finally:
                db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.close()
        need(not cache.exists(), "Python bytecode cache unexpectedly materialized")
        need(inventory(package) == {**expected, "PACKAGE-MANIFEST.json": sha(manifest_raw)},
             "Qualification input package mutated")
        result["qualification_complete"] = result["qualified_subjects"] == list(SUBJECTS)
    except Exception as exc:  # noqa: BLE001 - Preserve actual allocated negatives without repair/replay.
        result.update(error_type=type(exc).__name__, error=str(exc), qualification_complete=False)
    finally:
        sys.pycache_prefix, sys.dont_write_bytecode = saved_prefix, saved_bytecode
    result["elapsed_seconds"] = time.time() - started
    save(output / "RESULT-Q15.json", result)
    save(output / "OUTPUT-MANIFEST.json", {"schema": "hpc-forest-matrix15-Q-private-output-files-v1", "files": inventory(output)})
    archive_path = output.parent / (output.name + ".tar.gz")
    need(not archive_path.exists(), "Qualification result archive already exists; no replay")
    with archive_path.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for path in sorted(output.rglob("*")):
            need(not path.is_symlink(), "Linked qualification result member refused")
            if path.is_file():
                archive.add(path, arcname=output.name + "/" + path.relative_to(output).as_posix(), recursive=False)
    save(output.parent / (output.name + "-archive.json"), {"schema": "hpc-forest-matrix15-Q-archive-v1",
        "path": str(archive_path), "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "private_audit_only_never_model_context": True, "native_model_calls": 0})
    return result["qualification_complete"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, required=True)
    args = parser.parse_args()
    return 0 if run({"path": str(args.plan), "sha256": args.plan_sha256}, args.package,
                    args.output, args.maximum_seconds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
