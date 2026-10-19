"""Neutral future-runner gates; all calls and measurements here are synthetic."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import matrix15_first_batch as batch
from hpc_forest import matrix15_first_start as first_start
from hpc_forest.core import InfrastructureError, atomic_json, digest
from hpc_forest.matrix15_contract import REGISTERED_CELLS

RUNNER_PATH = Path(__file__).resolve().parents[1] / "examples/marathon22/forest_matrix15.py"
SPEC = importlib.util.spec_from_file_location("matrix15_runner_neutral_fixture", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def binding():
    return {"scope_id": "hpc-forest-matrix15-native-max-r2", **copy.deepcopy(next(iter(REGISTERED_CELLS.values()))),
            "job_id": "12345",
            "remote_root": "/scratch/neutral-fixture", "source_zip_sha256": "2" * 64,
            "plan_sha256": "3" * 64, "preparation_manifest_sha256": "4" * 64, "r1_contract_sha256": "5" * 64}


@pytest.fixture
def declared(binding):
    return {"problem": binding["subject_id"], "backend": "codex", "method": "H", "seed": 23,
            "roles": ["A", "B", "C"], "minimum_gain": 0.03,
            "schedule": {"cycles": 1, "trials_per_role_per_cycle": 2, "integrations_per_cycle": 2},
            "budget": {"search_slots": 11, "confirmation_slots": 3, "wall_seconds": 1800,
                "tokens": 1500000, "mission_tokens": 589824, "max_workers": 1, "max_depth": 6,
                "generation_seconds": 600, "infrastructure_retries": 0, "confirmation_seconds": 120},
            "harness": copy.deepcopy(runner.MIXED_HARNESS),
            "protocol": {"build": ["{python}", "{trusted}/contract_tool.py", "build", "{worktree}", "{build}"],
                "check": ["{python}", "{trusted}/contract_tool.py", "check", "{binary}", "{phase}"],
                "benchmark": ["/bin/sh", "{trusted}/benchmark.sh", "{binary}"], "repetitions": 3,
                "confirmation_repetitions": 5, "warmups": 1, "timeout_seconds": 17,
                "build_timeout_seconds": 120, "environment": copy.deepcopy(runner.SCIENTIFIC_ENVIRONMENT)},
            "codex": {"model": "{cell.model}", "reasoning_effort": "max", "transport": "codex-mailbox"}}


def configure(declared, binding):
    return runner.settings_for_cell(declared, {"protocol_timeout_seconds": 17}, runner.MIXED_HARNESS,
                                    binding, Path("/scratch/mailbox"), "target-neutral", "6" * 64)


def test_settings_keep_r1_scientific_contract_and_declared_generic_observer(declared, binding):
    original = copy.deepcopy(declared)
    settings = configure(declared, binding)
    assert declared == original
    assert settings["protocol"] == original["protocol"]
    assert settings["harness"] == original["harness"]
    assert settings["execution_provenance"]["cell_binding"] == binding
    assert settings["execution_provenance"]["mode"] == "command-stream-v1"
    assert "private_execution_audit" not in settings["protocol"]
    assert settings["budget"]["generation_admission"]["minimum_episode_seconds"] == 600
    assert settings["codex"]["session_id"] == binding["session_id"]
    assert settings["codex"]["model"] == binding["model"]


@pytest.mark.parametrize("cell", list(REGISTERED_CELLS.values()), ids=list(REGISTERED_CELLS))
def test_one_subject_template_resolves_only_each_registered_model_session(declared, binding, cell):
    binding.update(copy.deepcopy(cell))
    declared["problem"] = cell["subject_id"]
    settings = configure(declared, binding)
    assert settings["codex"]["model"] == cell["model"]
    assert settings["codex"]["session_id"] == cell["session_id"]
    assert declared["codex"]["model"] == "{cell.model}"


def test_model_placeholder_never_resolves_an_unregistered_session(declared, binding):
    binding["session_id"] = "f" * 32
    with pytest.raises(InfrastructureError):
        configure(declared, binding)


@pytest.mark.parametrize("section,key,value", [
    ("budget", "wall_seconds", 1801), ("budget", "tokens", 1500001),
    ("budget", "generation_seconds", 599), ("budget", "confirmation_seconds", 119),
    ("budget", "max_workers", 2), ("budget", "search_slots", 12),
    ("budget", "mission_tokens", 196608), ("budget", "infrastructure_retries", 1),
    ("protocol", "repetitions", 2), ("protocol", "confirmation_repetitions", 4),
    ("protocol", "warmups", 0), ("protocol", "timeout_seconds", 18),
    ("protocol", "build", ["replacement"]), ("protocol", "check", ["replacement"]),
    ("protocol", "environment", {}), ("protocol", "private_execution_audit", True),
    ("harness", "enabled", False), ("harness", "max_attempts", 2),
    ("codex", "model", "gpt-6-astra"), ("codex", "reasoning_effort", "high"),
    ("codex", "transport", "other"), ("schedule", "cycles", 2),
])
def test_settings_refuse_scientific_or_identity_drift(declared, binding, section, key, value):
    declared[section][key] = value
    with pytest.raises(InfrastructureError):
        configure(declared, binding)


@pytest.mark.parametrize("key,value", [("problem", "2020-graph"), ("seed", True),
    ("minimum_gain", 0.02), ("method", "U"), ("roles", ["A", "B"]),
    ("execution_provenance", {"mode": "unbound"})])
def test_settings_refuse_unbound_top_level_changes(declared, binding, key, value):
    declared[key] = value
    with pytest.raises(InfrastructureError):
        configure(declared, binding)


@pytest.mark.parametrize("extra", [["--model", "gpt-6-astra"], ["--subjects", "2020-graph"], ["--run"]])
def test_cli_has_no_free_model_subject_or_coordinator_switch(extra):
    with pytest.raises(SystemExit):
        runner.argument_parser().parse_args(["--root", "/r", "--shared", "/s", "--authorization", "/a",
                                             "--cell-key", "cell", *extra])


@pytest.fixture
def release_case(tmp_path, monkeypatch, binding):
    monkeypatch.setattr(batch, "cell_binding", lambda authorization: copy.deepcopy(binding))
    protocol = "7" * 64
    identity = {**binding, "protocol_id": protocol}
    def write(name, value):
        path = tmp_path / name
        atomic_json(path, value)
        return batch.bound_ref(path)
    request_ref = write("request.json", {"nonce": "a" * 32})
    private = {key: "b" * 64 for key in ("invocation_sha256", "process_sha256", "argv_sha256",
                                        "skill_override_sha256", "task_cli_policy_sha256")}
    call = {"request": request_ref, "private_cli_records": private, "private_cli_review_required": True,
            "private_cli_argv_verified": False, "invocation": {"sha256": "c" * 64}, "process": {"sha256": "d" * 64}}
    outcome = {"status": "incorrect", "correct": False, "logs": ["synthetic-preserved.log"]}
    evaluation_ref = write("evaluation.json", {**identity, "never_model_input": True,
        "experiment_id": "synthetic-child", "outcome": outcome})
    first = {**identity, "verified": True, "technical_errors_found": False, "invocation_unknown": False,
             "first_normal_delivered_call": call, "all_started_calls_reconciled": [call],
             "first_real_evaluation": {"experiment_id": "synthetic-child", "status": "incorrect",
                                       "outcome_sha256": digest(outcome)},
             "private_cli_review_required": True, "private_cli_argv_verified": False,
             "observation_mode": "command-stream-v1", "private_case_v2_claimed": False}
    first_ref = write("first.json", first)
    snapshot = {**identity, "first_start_receipt": first_ref, "evaluation_snapshot": evaluation_ref}
    snapshot["self_ref"] = write("snapshot.json", snapshot)
    audit = {"schema": "hpc-forest-matrix15-private-cli-audit-digest-projection-v1", **identity,
        "verified": True, "first_start_receipt_sha256": first_ref["sha256"],
        "paused_snapshot_sha256": snapshot["self_ref"]["sha256"], "call_bindings": batch.private_call_bindings(first),
        "all_private_raws_received_and_hashed": True, "argv_matches_projections_and_local_policy": True,
        "cli_diagnostics_clean": True, "raw_skill_paths_exported": False, "private_review_receipt_sha256": "e" * 64}
    audit_ref = write("audit.json", audit)
    release = {"schema": "hpc-forest-matrix15-first-batch-release-v1", **identity, "verified": True,
               "paused_snapshot": snapshot["self_ref"], "first_start_receipt": first_ref,
               "evaluation_snapshot": evaluation_ref, "private_cli_audit": audit_ref,
               "no_replay": True, "new_model_or_budget_authorized": False}
    return release, snapshot, first, {}, audit


def test_actual_linked_negative_evaluation_can_release_without_turning_into_gain(release_case):
    release, snapshot, first, auth, audit = release_case
    assert batch.validate_first_batch_release(release, snapshot, first, auth) == audit
    assert first["first_real_evaluation"]["status"] == "incorrect"


@pytest.mark.parametrize("key,value", [("subject_id", "2020-graph"), ("cell_key", "foreign"),
    ("protocol_id", "f" * 64), ("session_id", "f" * 32), ("job_id", "99999"),
    ("r1_contract_sha256", "f" * 64), ("new_model_or_budget_authorized", True), ("verified", 1)])
def test_first_batch_release_rejects_cross_cell_protocol_or_budget(release_case, key, value):
    release, snapshot, first, auth, _ = release_case
    release[key] = value
    with pytest.raises(InfrastructureError):
        batch.validate_first_batch_release(release, snapshot, first, auth)


def test_first_batch_rehashes_snapshot_and_private_audit(release_case):
    release, snapshot, first, auth, _ = release_case
    Path(release["private_cli_audit"]["path"]).write_text("{}", encoding="utf8")
    with pytest.raises(InfrastructureError):
        batch.validate_first_batch_release(release, snapshot, first, auth)


def test_first_batch_refuses_relabelled_negative(release_case):
    release, snapshot, first, auth, _ = release_case
    first["first_real_evaluation"]["status"] = "valid"
    with pytest.raises(InfrastructureError):
        batch.validate_first_batch_release(release, snapshot, first, auth)


def test_duplicate_claim_nonce_blocks_private_audit(release_case):
    _, _, first, _, _ = release_case
    first["all_started_calls_reconciled"].append(copy.deepcopy(first["all_started_calls_reconciled"][0]))
    with pytest.raises(InfrastructureError):
        batch.private_call_bindings(first)


def test_wait_expiry_keeps_original_deadline_and_does_not_make_requests(tmp_path, monkeypatch, binding):
    monkeypatch.setattr(batch, "cell_binding", lambda _: binding)
    first = {"protocol_id": "7" * 64, "verified": False}
    atomic_json(tmp_path / "premier-demarrage-verifie.json", first)
    controller = SimpleNamespace(db=SimpleNamespace(get=lambda key: 1120), config={"budget": {"confirmation_seconds": 120}})
    assert batch.wait_first_batch_release(controller, {"expires_at": 2000}, tmp_path, first,
        now=lambda: 1001, monotonic=lambda: 5, sleep=lambda _: pytest.fail("No wait after expiry")) is False
    receipt = json.loads((tmp_path / "premier-batch-attente-expiree.json").read_text(encoding="utf8"))
    assert receipt["existing_search_deadline"] == 1000
    assert receipt["next_batch_started"] is False
    assert receipt["budget_or_chronology_reset"] is False
    with pytest.raises(InfrastructureError):
        batch.wait_first_batch_release(controller, {"expires_at": 2000}, tmp_path, first,
            now=lambda: 1001, monotonic=lambda: 5, sleep=lambda _: None)


def test_first_start_marks_unknown_delivery_technical_and_never_verified(tmp_path, monkeypatch, binding):
    monkeypatch.setattr(first_start, "selected_identity", lambda _: (binding["model"], binding["session_id"]))
    monkeypatch.setattr(first_start, "cell_binding", lambda _: binding)
    monkeypatch.setattr(first_start, "read_json", lambda path: {})
    controller = SimpleNamespace(db=SimpleNamespace(get=lambda key: "7" * 64))
    receipt = first_start.first_start_receipt(controller, tmp_path / "mailbox", {"artifacts": {}},
                                               {"job_id": binding["job_id"]}, tmp_path / "receipt.json")
    assert receipt["verified"] is False
    assert receipt["invocation_unknown"] is True
    assert receipt["technical_errors_found"] is True
    assert receipt["private_case_v2_claimed"] is False
    assert receipt["independent_performance_audit_verified"] is False


def test_final_confirmations_require_five_actual_times_and_keep_reference_negative(monkeypatch, binding):
    outcome = {"status": "valid", "correct": True, "times": [1.0] * 5, "logs": ["synthetic"]}
    rows = [{"experiment_id": "baseline-e1", "outcome": outcome}]
    controller = SimpleNamespace(epoch=lambda: {"id": 1}, db=SimpleNamespace(evaluations=lambda *_: rows,
        get=lambda _: "7" * 64), config={"execution_provenance": {"synthetic": True}})
    monkeypatch.setattr(runner, "evaluation_provenance", lambda *args, **kwargs: [{"synthetic": True}])
    best = {"experiment_id": "baseline-e1", "is_baseline": True}
    receipt = runner.confirmation_receipt(controller, best, binding)
    assert receipt["verified"] is True and receipt["algorithmic_negative_preserved"] is True
    assert receipt["independent_performance_audit_verified"] is False
    outcome["times"] = [1.0] * 4
    with pytest.raises(InfrastructureError):
        runner.confirmation_receipt(controller, best, binding)


def test_exact_usage_reconciles_program_and_mother_without_budget_credit():
    calls = [{"exact_tokens": 12, "mother_phase": None},
             {"exact_tokens": 7, "mother_phase": "mother-preparation"}]
    costs = {"unknown_usage_calls": 0, "bounded_usage_calls": 0, "exact_tokens_used": 19}
    controller = SimpleNamespace(db=SimpleNamespace(costs=lambda: costs, get=lambda key:
        {"status": "complete", "model_calls": 1} if key.endswith("preparation") else None))
    result = first_start.reconcile_usage_and_mothers(controller, calls)
    assert result["all_delivered_tokens_exact"] == 19
    assert result["mother_claims"]["preparation"]["delivered_calls_reconciled"] == 1
    assert result["budget_or_chronology_reset"] is False


@pytest.mark.parametrize("mutation", ["unknown", "bounded", "missing_tokens", "unpublished_mother", "unowned_mother",
                                      "duplicate_mother", "unfinished_mother"])
def test_usage_or_mother_claim_gap_blocks_without_replay(mutation):
    calls = [{"exact_tokens": 7, "mother_phase": "mother-preparation"}]
    costs = {"unknown_usage_calls": 0, "bounded_usage_calls": 0, "exact_tokens_used": 7}
    mother = {"status": "complete", "model_calls": 1}
    if mutation == "unknown":
        costs["unknown_usage_calls"] = 1
    elif mutation == "bounded":
        costs["bounded_usage_calls"] = 1
    elif mutation == "missing_tokens":
        costs["exact_tokens_used"] = 8
    elif mutation == "unpublished_mother":
        calls, costs["exact_tokens_used"] = [], 0
    elif mutation == "unowned_mother":
        mother = None
    elif mutation == "duplicate_mother":
        calls.append(copy.deepcopy(calls[0]))
        costs["exact_tokens_used"] = 14
    elif mutation == "unfinished_mother":
        mother = {"status": "started_without_final_response"}
    controller = SimpleNamespace(db=SimpleNamespace(costs=lambda: costs,
        get=lambda key: mother if key.endswith("preparation") else None))
    with pytest.raises(InfrastructureError):
        first_start.reconcile_usage_and_mothers(controller, calls)


def test_command_proof_cannot_be_relabelled_from_search_to_confirmation(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.command-stream.json"
    atomic_json(path, {"phase": "search"})
    monkeypatch.setattr(first_start, "command_stream_provenance", lambda *args, **kwargs: [first_start.ref(path)])
    assert first_start.evaluation_provenance({}, "fixture", policy={}, protocol_id="7" * 64, phase="search")
    with pytest.raises(InfrastructureError):
        first_start.evaluation_provenance({}, "fixture", policy={}, protocol_id="7" * 64, phase="confirmation")
