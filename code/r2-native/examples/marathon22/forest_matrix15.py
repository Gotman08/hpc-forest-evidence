"""One explicitly admitted subject/model/MAX cell of the future R2 Forest matrix.

This preparation is fail-closed until the single audited Sol primes pilot and this
subject's actual allocated qualification/reception have been bound and reviewed.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import socket
import sys
import tarfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hpc_forest.core import InfrastructureError, atomic_json, digest, file_digest  # noqa: E402
from hpc_forest.matrix15_contract import assert_r1_pair_contract, resolve_subject, validate_cell  # noqa: E402
from hpc_forest.matrix15_first_batch import reconcile_after_batch, wait_first_batch_release  # noqa: E402
from hpc_forest.matrix15_first_start import evaluation_provenance, first_start_receipt  # noqa: E402
from hpc_forest.native_matrix15 import (  # noqa: E402
    EFFORT,
    allocation_guard,
    artifact,
    cell_binding,
    directory_artifact,
    install_identity,
    read_json,
    same_artifact_reference,
    selected_identity,
    validate_aliases,
)

MIXED_HARNESS = {"enabled": True, "max_attempts": 3, "call_token_ceiling": 196608,
                 "research": {"enabled": True, "corpus": None, "corpus_sha256": None,
                              "allowed_hosts": ["gcc.gnu.org", "www.openmp.org", "raw.githubusercontent.com"]}}
SCIENTIFIC_ENVIRONMENT = {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE",
                          "CUDA_VISIBLE_DEVICES": ""}


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shared", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--cell-key", required=True)
    return parser


def _need(condition, message):
    if not condition:
        raise InfrastructureError(message)


def bound_ref(path):
    return {"path": str(Path(path).resolve()), "sha256": file_digest(Path(path))}


def settings_for_cell(declared, prepared, harness, binding, channel, target, runtime_sha256):
    """Validate the complete declared R1 settings; vary only declared operator/deployment data."""
    settings = copy.deepcopy(declared)
    _need(harness == MIXED_HARNESS and settings.get("harness") == MIXED_HARNESS,
          "The exact R1 mixed scientific/documentation harness is required")
    _need(settings.get("problem") == binding["subject_id"] and settings.get("backend") == "codex"
          and settings.get("method") == "H" and type(settings.get("seed")) is int and settings["seed"] == 23
          and settings.get("roles") == ["A", "B", "C"] and settings.get("minimum_gain") == 0.03,
          "Declared subject/search/seed/minimum-gain differs from the paired R1 contract")
    _need(settings.get("schedule") == {"cycles": 1, "trials_per_role_per_cycle": 2, "integrations_per_cycle": 2},
          "Exactly eight program missions and two separately charged mother episodes required")
    required_budget = {"search_slots": 11, "confirmation_slots": 3, "wall_seconds": 1800,
        "tokens": 1500000, "mission_tokens": 589824, "max_workers": 1, "max_depth": 6,
        "generation_seconds": 600, "infrastructure_retries": 0, "confirmation_seconds": 120}
    budget = settings.get("budget", {})
    _need(all(type(budget.get(key)) is int and budget[key] == value for key, value in required_budget.items()),
          "Declared scientific cell budget differs from archive_matrix")
    admission = {"schema": "hpc-forest-full-generation-window-v1", "minimum_episode_seconds": 600.0}
    _need(set(budget) <= {*required_budget, "generation_admission"}
          and budget.get("generation_admission", admission) == admission,
          "Undeclared budget/admission changes are forbidden")
    protocol = settings.get("protocol", {})
    expected_protocol = {"build": ["{python}", "{trusted}/contract_tool.py", "build", "{worktree}", "{build}"],
        "check": ["{python}", "{trusted}/contract_tool.py", "check", "{binary}", "{phase}"],
        "benchmark": ["/bin/sh", "{trusted}/benchmark.sh", "{binary}"], "repetitions": 3,
        "confirmation_repetitions": 5, "warmups": 1, "timeout_seconds": prepared["protocol_timeout_seconds"],
        "build_timeout_seconds": 120, "environment": SCIENTIFIC_ENVIRONMENT}
    _need(protocol == expected_protocol, "R1 commands, timing, checker, options or environment changed")
    codex = settings.get("codex", {})
    validate_cell({key: binding[key] for key in ("cell_key", "subject_id", "model", "effort", "session_id")})
    _need(codex.get("model") == "{cell.model}" and codex.get("reasoning_effort") == EFFORT
          and codex.get("transport") == "codex-mailbox", "Declared native model/MAX/transport differs")
    _need("execution_provenance" not in settings, "Operator provenance must be bound once to the actual cell")
    settings["codex"].update(model=binding["model"], mailbox_dir=str(channel), session_id=binding["session_id"])
    settings["target_id"] = target
    settings["budget"]["generation_admission"] = admission
    settings["execution_provenance"] = {"mode": "command-stream-v1", "cell_binding": copy.deepcopy(binding),
        "source_runtime_sha256": runtime_sha256, "cell_contract_sha256": binding["r1_contract_sha256"],
        "protocol_plan_sha256": binding["plan_sha256"]}
    return settings


def verify_shared_inputs(shared, authorization, cell_key):
    """Read only immutable source/preparation/contract material, never another campaign."""
    shared = Path(shared).resolve(strict=True)
    plan = read_json(artifact(authorization["artifacts"]["plan"]))
    subject = resolve_subject(plan, cell_key)
    binding = cell_binding(authorization)
    _need(cell_key == binding["cell_key"] and subject["subject_id"] == binding["subject_id"]
          and all(subject[key] == binding[key] for key in ("model", "effort", "session_id")),
          "Runner selection differs from the exact authorized plan cell")
    runtime_ref = authorization["artifacts"]["runtime_manifest"]
    prepared_ref = authorization["artifacts"]["preparation_manifest"]
    def same_ref(left, right):
        return same_artifact_reference(left, right)
    _need(same_ref(runtime_ref, plan["runtime_manifest"]) and same_ref(prepared_ref, plan["preparation_manifest"])
          and same_ref(authorization["artifacts"]["harness"], plan["harness"]),
          "Shared references differ from the same explicit immutable plan artifacts")
    runtime_path, prepared_path = artifact(runtime_ref), artifact(prepared_ref)
    _need(runtime_path.resolve().is_relative_to(shared) and prepared_path.resolve().is_relative_to(shared),
          "Shared manifests are outside the explicitly owned shared deployment")
    runtime = read_json(runtime_path)
    _need(isinstance(runtime, dict) and bool(runtime), "A nonempty immutable runtime manifest is required")
    for name, expected in runtime.items():
        path = shared / "project" / name
        _need(not path.is_symlink() and path.resolve().is_relative_to(shared / "project")
              and path.is_file() and file_digest(path) == expected, "Immutable matrix runtime changed: " + name)
    manifest = read_json(prepared_path)
    _need(isinstance(manifest.get("files"), dict) and bool(manifest["files"]), "Prepared file bindings missing")
    record = manifest["records"].get(binding["subject_id"], {})
    _need(record.get("status") == "ready" and isinstance(record.get("prepared"), dict),
          "The admitted subject is not independently prepared and ready")
    prepared = copy.deepcopy(record["prepared"])
    aliases = validate_aliases(read_json(artifact(authorization["artifacts"]["artifact_aliases"])), binding["source_zip_sha256"])
    official_root, _ = directory_artifact(subject["official_preparation_path"], subject_id=binding["subject_id"],
        role="official", preparation_manifest=manifest, preparation_manifest_sha256=prepared_ref["sha256"], aliases=aliases)
    for key in ("source", "validation"):
        path, _ = directory_artifact(prepared[key], subject_id=binding["subject_id"], role=key,
            preparation_manifest=manifest, preparation_manifest_sha256=prepared_ref["sha256"], aliases=aliases)
        _need(path.resolve().is_relative_to(official_root.resolve()),
              "Prepared source/validation alias is outside its owned official subject")
        prepared[key] = str(path)
    contract_path = Path(prepared["validation"]) / "contract.json"
    _need(contract_path.resolve() == artifact(subject["prepared_contract_ref"]).resolve(),
          "Prepared contract differs from the explicit subject alias")
    _need(subject["r1_contract_ref"]["sha256"] == binding["r1_contract_sha256"], "R1 contract binding differs")
    assert_r1_pair_contract(read_json(artifact(subject["r1_contract_ref"])), read_json(contract_path))
    _need(digest(record) == subject["preparation_sha256"], "Subject preparation record digest differs")
    harness = read_json(artifact(authorization["artifacts"]["harness"]))
    _need(harness == MIXED_HARNESS, "The exact R1 mixed harness file is required")
    statement = artifact(subject["statement_ref"])
    _need(statement.resolve() == shared / "statements" / (binding["subject_id"][:4] + ".txt"),
          "Hash-bound official statement is outside its exact shared year path")
    return plan, subject, prepared, harness, statement


def confirmation_receipt(controller, best, binding):
    """Verify the five real interleaved confirmations; retain a reference winner as a negative gain."""
    epoch = controller.epoch()["id"]
    rows = controller.db.evaluations("confirmation", epoch)
    baseline = [row for row in rows if row["experiment_id"] == f"baseline-e{epoch}"]
    _need(len(baseline) == 1, "Current reference confirmation missing")
    selected = [row for row in rows if row["experiment_id"] == best["experiment_id"]]
    _need(len(selected) == 1, "Selected confirmed result missing")
    proofs = {}
    for row in rows:
        outcome = row["outcome"]
        if outcome.get("correct") is True:
            _need(outcome.get("status") == "valid" and len(outcome.get("times", [])) == 5,
                  "Correct final outcome must contain exactly five actual measurements")
        proofs[row["experiment_id"]] = evaluation_provenance(outcome, row["experiment_id"],
            policy=controller.config["execution_provenance"], protocol_id=controller.db.get("protocol_id"), phase="confirmation")
    _need(baseline[0]["outcome"].get("correct") is True and selected[0]["outcome"].get("correct") is True,
          "Reference/selected official correctness confirmation failed")
    return {"schema": "hpc-forest-matrix15-final-confirmations-v1", **binding,
            "protocol_id": controller.db.get("protocol_id"), "verified": True,
            "confirmation_repetitions": 5, "interleaving_owner": "unchanged-Evaluator.confirm",
            "evaluation_digests": {row["experiment_id"]: digest(row["outcome"]) for row in rows},
            "command_stream_provenance": proofs, "best_confirmed": best,
            "algorithmic_negative_preserved": best["is_baseline"] is True,
            "private_case_v2_claimed": False, "independent_raw_stdout_per_candidate_verified": False,
            "independent_performance_audit_verified": False}


def main(argv=None):
    args = argument_parser().parse_args(argv)
    allocation = allocation_guard()
    authorization = install_identity(args.authorization)
    binding = cell_binding(authorization)
    model, session = selected_identity(authorization)
    _need(args.cell_key == binding["cell_key"] and allocation["job_id"] == binding["job_id"]
          and str(args.root) == binding["remote_root"], "Runner cell/root/allocation differs from admission")
    _need(importlib.metadata.version("treequest") == "0.3.2", "Actual pinned TreeQuest 0.3.2 required")
    plan, subject, prepared, harness, statement_path = verify_shared_inputs(args.shared, authorization, args.cell_key)
    # Identity must be installed before importing legacy modules which capture it.
    import romeo_codex as runner
    from romeo_harness_comparison import ObservedController, verify_worker

    from hpc_forest.codex_mailbox import initialize_channel
    from hpc_forest.controller import create_workspace
    from hpc_forest.mother import MotherContext
    from hpc_forest.reporting import package, report

    class MotherController(MotherContext, ObservedController):
        pass

    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    output = root / f"results-{allocation['job_id']}"
    output.mkdir()
    result = {"schema": "hpc-forest-matrix15-native-single-cell-v1", **binding, "allocation": allocation,
              "pipeline_complete": False, "automatic_extension": False, "other_cells_started": 0,
              "native_research_admitted_by_this_code": False, "negative_outcomes_preserved": True,
              "old_candidates_imported": False, "operator_algorithm_advice": False,
              "private_case_v2_claimed": False, "independent_raw_stdout_per_candidate_verified": False,
              "independent_performance_audit_verified": False}
    started = time.monotonic()
    campaign = output / binding["subject_id"]
    try:
        channel = output / "mailbox"
        owner = initialize_channel(channel, session, allocation["job_id"])
        atomic_json(channel / "OWNER.json", {**owner, **binding})
        atomic_json(output / "channel.json", {**binding, "channel": str(channel)})
        worker = verify_worker(channel, session, 600)
        _need(all(worker.get(key) == value for key, value in binding.items()), "Worker is not this admitted cell")
        atomic_json(output / "worker-identity.json", worker)
        runner.CHANNEL, runner.SESSION_ID = channel, session
        runner.HARNESS = copy.deepcopy(harness)
        runner.reference.SCHEDULE.update(cycles=1, trials_per_role_per_cycle=2, integrations_per_cycle=2)
        runner.reference.LIMITS.update(wall_seconds=1800, tokens=1500000, generation_seconds=600)
        target = f"romeo:{socket.gethostname()}:slurm-{allocation['job_id']}:matrix15-cpu4"
        settings = settings_for_cell(subject["config"], prepared, harness, binding, channel, target,
                                     plan["runtime_manifest"]["sha256"])
        create_workspace(campaign, settings, source=Path(prepared["source"]), validation=Path(prepared["validation"]))
        assert_r1_pair_contract(read_json(artifact(subject["r1_contract_ref"])), read_json(campaign / "trusted/contract.json"))
        with MotherController(campaign, statement_path.read_text(encoding="utf8")) as controller:
            with controller.db.connection:
                controller.db.connection.execute("DELETE FROM documents")
            controller.db.event("matrix15_protocol_identity", {**binding, "mother_model": model,
                "mother_effort": EFFORT, "protocol_id": controller.db.get("protocol_id"),
                "harness_sha256": plan["harness"]["sha256"], "old_candidates_imported": False,
                "operator_algorithm_advice": False, "observation_mode": "command-stream-v1"})
            first_checked = first_released = False
            while True:
                result["search"] = controller.run(max_batches=1)
                first_checked, first = reconcile_after_batch(controller, channel, authorization, allocation, output, first_checked)
                result["first_start_control"] = "verified" if first_checked else "pending_first_real_evaluation"
                atomic_json(output / "results.json", result)
                if result["search"]["status"] != "checkpointed":
                    break
                if not first_released:
                    if not wait_first_batch_release(controller, authorization, output, first):
                        result.update(first_batch_release="closed_at_existing_search_deadline", extension_blocked=True,
                                      no_candidate_replay=True)
                        return 1
                    first_released = True
            final = first_start_receipt(controller, channel, authorization, allocation, output / "reconciliation-finale-verifiee.json")
            _need(final.get("technical_errors_found") is False, "Unknown/failed call blocks completion")
            result["first_start_control"] = "verified" if final["verified"] else "closed_known_negative_without_real_evaluation"
            result["best_confirmed"] = controller.confirm()
            confirmation = confirmation_receipt(controller, result["best_confirmed"], binding)
            atomic_json(output / "confirmations-finales-verifiees.json", confirmation)
            result["five_confirmations_verified"] = True
            result["protocol_id"] = controller.db.get("protocol_id")
            result["costs"] = controller.db.costs()
            result["mother"] = {phase: controller.db.get("mother_plan:" + phase) for phase in ("preparation", "synthesis")}
        report(campaign)
        package(campaign, campaign / "submission.zip")
        result["pipeline_complete"] = True
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(), extension_blocked=True)
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        atomic_json(output / "results.json", result)
        archive = root / f"results-{allocation['job_id']}.tar.gz"
        with tarfile.open(archive, "x:gz") as stream:
            stream.add(output, arcname=output.name)
        atomic_json(root / "archive.json", {**binding, "path": str(archive), "sha256": file_digest(archive),
                                           "private_audit_only_never_model_context": True})
    return 0 if result["pipeline_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
