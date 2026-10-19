"""Neutral process doubles only: no Git process, compiler, model, or received code."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from hpc_forest import evaluator
from hpc_forest import matrix15_provenance as provenance
from hpc_forest.config import load_config, validate
from hpc_forest.core import (
    BudgetExhausted,
    ForestError,
    InfrastructureError,
    ProcessResult,
    atomic_json,
    file_digest,
)

COMMIT, TREE, PROTOCOL = "1" * 40, "2" * 40, "3" * 64


@pytest.fixture
def policy():
    return {
        "mode": "command-stream-v1",
        "cell_binding": {
            "scope_id": provenance.SCOPE,
            "cell_key": "forest-r2/gpt-6-astra/max/2023-count/seed-23",
            "subject_id": "2023-count", "model": "gpt-6-astra", "effort": "max",
            "session_id": "4" * 32, "job_id": "999001",
            "remote_root": "/scratch_p/NEUTRAL/matrix15-cell",
            "source_zip_sha256": "5" * 64, "plan_sha256": "6" * 64,
            "preparation_manifest_sha256": "7" * 64, "r1_contract_sha256": "8" * 64,
        },
        "source_runtime_sha256": "9" * 64,
        "cell_contract_sha256": "a" * 64,
        "protocol_plan_sha256": "b" * 64,
    }


@pytest.fixture
def observed(tmp_path, monkeypatch, policy):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    binary = tmp_path / "build" / "solution"
    binary.parent.mkdir()
    binary.write_bytes(b"NEUTRAL_BINARY_NEVER_EXECUTED")
    script = tmp_path / "trusted" / "checker.py"
    script.parent.mkdir()
    script.write_bytes(b"NEUTRAL_CHECKER_NEVER_EXECUTED")
    configuration = {
        "target_id": "NEUTRAL",
        "execution_provenance": policy,
        "protocol": {
            "build": ["NEVER_EXECUTE_BUILD", "{binary}"],
            "check": ["NEVER_EXECUTE_PYTHON", str(script), "{binary}", "{phase}"],
            "benchmark": ["{binary}", "R1_OPTION_UNCHANGED"],
            "environment": {"OMP_NUM_THREADS": "4", "UNIT_SCIENCE_OPTION": "unchanged"},
            "timeout_seconds": 30, "build_timeout_seconds": 120,
        },
    }
    variables = {
        "worktree": str(worktree), "binary": str(binary), "phase": "search",
        "experiment_id": "neutral-experiment", "epoch": 1, "commit": COMMIT, "tree_hash": TREE,
    }
    calls = []
    clean_calls = []
    monkeypatch.setattr(provenance, "ensure_clean", lambda *args: clean_calls.append(args))
    monkeypatch.setattr(provenance, "git", lambda *args: TREE)

    def fake_process(command, cwd, log, timeout, env):
        calls.append((list(command), cwd, log, timeout, copy.deepcopy(env)))
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(b"EXACT_STDOUT\x00\xff\nEXACT_STDERR_ALREADY_COMBINED\r\n")
        result = ProcessResult(command, 0, 0.125, False, str(log))
        atomic_json(log.with_suffix(log.suffix + ".json"), asdict(result))
        return result

    monkeypatch.setattr(evaluator, "run_process", fake_process)
    instance = evaluator.Evaluator(tmp_path, configuration, {}, PROTOCOL, 10**10)
    monkeypatch.setattr(instance, "_timeout", lambda build=False: 42.5 if build else 12.5)
    return instance, variables, tmp_path / "logs" / "correctness.log", calls, clean_calls


def read_proof(log):
    return json.loads(provenance.provenance_path(log).read_text(encoding="utf-8"))


def cold(log, policy):
    return provenance.command_stream_provenance(
        {"logs": [str(log)], "commit": COMMIT, "tree_hash": TREE}, "neutral-experiment",
        expected_policy=policy, protocol_id=PROTOCOL,
    )


def test_policy_is_optional_without_mutating_legacy_configuration():
    config = load_config()
    before = copy.deepcopy(config)
    assert provenance.command_stream_policy(config) is None
    validate(config)
    assert config == before


def test_policy_validation_is_exact_and_returns_detached_copy(policy):
    config = load_config()
    scientific = copy.deepcopy(config["protocol"])
    config["execution_provenance"] = policy
    validate(config)
    checked = provenance.command_stream_policy(config)
    checked["cell_binding"]["job_id"] = "999002"
    assert config["execution_provenance"]["cell_binding"]["job_id"] == "999001"
    assert config["protocol"] == scientific


@pytest.mark.parametrize("mutation", [
    "extra-policy", "missing-policy", "wrong-mode", "null-policy", "extra-cell", "missing-cell",
    "wrong-scope", "wrong-subject", "wrong-model", "wrong-effort", "wrong-key", "old-session",
    "bad-job", "relative-root", "parent-root", "bool-hash", "bad-hash", "case-v2", "case-v2-one",
])
def test_malformed_or_cross_mode_policy_refused_before_effects(policy, mutation):
    configuration = {"execution_provenance": copy.deepcopy(policy), "protocol": {}}
    value = configuration["execution_provenance"]
    cell = value["cell_binding"]
    if mutation == "extra-policy":
        value["verified"] = True
    elif mutation == "missing-policy":
        del value["source_runtime_sha256"]
    elif mutation == "wrong-mode":
        value["mode"] = "case-v2"
    elif mutation == "null-policy":
        configuration["execution_provenance"] = None
    elif mutation == "extra-cell":
        cell["verified"] = True
    elif mutation == "missing-cell":
        del cell["job_id"]
    elif mutation == "wrong-scope":
        cell["scope_id"] = "hpc-forest-primes-native-max-r2h"
    elif mutation == "wrong-subject":
        cell["subject_id"] = "2023-primes"
    elif mutation == "wrong-model":
        cell["model"] = "unregistered-model"
    elif mutation == "wrong-effort":
        cell["effort"] = "high"
    elif mutation == "wrong-key":
        cell["cell_key"] += "-other"
    elif mutation == "old-session":
        cell["session_id"] = "legacy-session"
    elif mutation == "bad-job":
        cell["job_id"] = True
    elif mutation == "relative-root":
        cell["remote_root"] = "scratch/cell"
    elif mutation == "parent-root":
        cell["remote_root"] = "/scratch/../cell"
    elif mutation == "bool-hash":
        value["source_runtime_sha256"] = True
    elif mutation == "bad-hash":
        cell["source_zip_sha256"] = "not-a-sha"
    else:
        configuration["protocol"]["private_execution_audit"] = True if mutation == "case-v2" else 1
    with pytest.raises(ForestError):
        provenance.command_stream_policy(configuration)


def test_observation_preserves_original_process_options_raw_bytes_and_seconds(observed, policy):
    instance, variables, log, calls, clean_calls = observed
    original_protocol = copy.deepcopy(instance.protocol)
    result = instance._run("check", variables, log)
    assert result.seconds == 0.125
    assert len(calls) == 1 and len(clean_calls) == 2
    command, cwd, recorded_log, timeout, environment = calls[0]
    assert command == ["NEVER_EXECUTE_PYTHON", str(log.parent.parent / "trusted" / "checker.py"),
                       variables["binary"], "search"]
    assert cwd == Path(variables["worktree"]) and recorded_log == log and timeout == 12.5
    assert environment == original_protocol["environment"]
    assert instance.protocol == original_protocol
    assert not any(key.startswith("HPC_FOREST_PRIVATE_") for key in environment)
    proof = read_proof(log)
    assert proof["schema"] == provenance.EXECUTION_SCHEMA and proof["verified"] is True
    assert proof["operator_binding"] == policy
    assert proof["measured_seconds"] == result.seconds
    assert proof["binary_before"] == proof["binary_after"]
    assert proof["streams"]["combined_stdout_stderr"]["sha256"] == file_digest(log)
    assert proof["streams"]["separate_stdout"] is None
    assert proof["streams"]["separate_stderr"] is None
    assert proof["case_execution_records"] == []
    assert proof["individual_case_provenance_verified"] is False
    assert proof["independent_raw_stdout_per_candidate_verified"] is False
    assert proof["independent_performance_audit_verified"] is False
    refs = cold(log, policy)
    assert len(refs) == 1 and refs[0]["sha256"] == file_digest(provenance.provenance_path(log))
    assert refs[0]["independent_performance_audit_verified"] is False


def test_expired_budget_has_no_git_file_or_process_effects(observed, monkeypatch):
    instance, variables, log, calls, clean_calls = observed
    monkeypatch.setattr(instance, "_timeout", lambda build=False: 0)
    with pytest.raises(BudgetExhausted):
        instance._run("check", variables, log)
    assert not log.parent.exists() and calls == [] and clean_calls == []


def test_admission_rechecks_deadline_after_hashing_before_process(observed, monkeypatch):
    instance, variables, log, calls, _ = observed
    ticks = iter([10, 0])
    monkeypatch.setattr(instance, "_timeout", lambda build=False: next(ticks))
    with pytest.raises(BudgetExhausted):
        instance._run("check", variables, log)
    assert calls == [] and not log.exists() and not provenance.provenance_path(log).exists()


def test_existing_context_refuses_replay_before_process(observed):
    instance, variables, log, calls, _ = observed
    log.parent.mkdir()
    log.with_suffix(log.suffix + ".command-context.json").write_text("OLD_CONTEXT", encoding="utf-8")
    with pytest.raises(InfrastructureError, match="already exists"):
        instance._run("check", variables, log)
    assert calls == []


def test_source_tree_mismatch_refused_before_process(observed, monkeypatch):
    instance, variables, log, calls, _ = observed
    monkeypatch.setattr(provenance, "git", lambda *args: "f" * 40)
    with pytest.raises(InfrastructureError, match="source tree changed"):
        instance._run("check", variables, log)
    assert calls == [] and not log.parent.exists()


def test_changed_binary_after_process_fails_without_replay(observed, monkeypatch):
    instance, variables, log, calls, _ = observed
    original = evaluator.run_process

    def change_binary(*args):
        result = original(*args)
        Path(variables["binary"]).write_bytes(b"TAMPERED_AFTER_COMMAND")
        return result

    monkeypatch.setattr(evaluator, "run_process", change_binary)
    with pytest.raises(InfrastructureError, match="no replay"):
        instance._run("check", variables, log)
    assert len(calls) == 1 and read_proof(log)["verified"] is False


def test_build_may_create_contracted_binary_without_changing_science_options(observed, monkeypatch, policy):
    instance, variables, log, calls, _ = observed
    Path(variables["binary"]).unlink()
    original = evaluator.run_process

    def build_binary(*args):
        result = original(*args)
        Path(variables["binary"]).write_bytes(b"NEUTRAL_BUILD_OUTPUT")
        return result

    monkeypatch.setattr(evaluator, "run_process", build_binary)
    instance._run("build", variables, log, build=True)
    assert calls[0][3] == 42.5
    proof = read_proof(log)
    assert proof["binary_before"] is None and proof["binary_after"]["sha256"] == file_digest(Path(variables["binary"]))
    assert cold(log, policy)[0]["verified"] is True


def test_nonzero_or_timeout_is_observed_without_promoting_correctness(observed, monkeypatch, policy):
    instance, variables, log, _, _ = observed
    original = evaluator.run_process

    def failed_process(*args):
        result = original(*args)
        result.returncode, result.timed_out = 9, True
        atomic_json(log.with_suffix(log.suffix + ".json"), asdict(result))
        return result

    monkeypatch.setattr(evaluator, "run_process", failed_process)
    result = instance._run("check", variables, log)
    proof = read_proof(log)
    assert result.returncode == 9 and result.timed_out is True and proof["verified"] is True
    assert "correct" not in proof and "score" not in proof
    assert cold(log, policy)[0]["verified"] is True


@pytest.mark.parametrize("changed", [
    "raw", "context", "process", "binding", "protocol", "commit", "tree", "promote-cases",
    "promote-independent", "promote-raw", "separate-stream", "extra-proof", "returncode",
])
def test_cold_reader_refuses_tampering_and_unproved_promotions(observed, policy, changed):
    instance, variables, log, _, _ = observed
    instance._run("check", variables, log)
    proof = read_proof(log)
    if changed == "raw":
        log.write_bytes(b"CHANGED_RAW")
    elif changed == "context":
        Path(proof["context"]["path"]).write_bytes(b"CHANGED_CONTEXT")
    elif changed == "process":
        Path(proof["original_process_result"]["path"]).write_bytes(b"CHANGED_PROCESS")
    else:
        if changed == "binding":
            proof["operator_binding"]["cell_binding"]["job_id"] = "999002"
        elif changed == "protocol":
            proof["protocol_id"] = "f" * 64
        elif changed == "commit":
            proof["commit"] = "f" * 40
        elif changed == "tree":
            proof["tree_hash"] = "f" * 40
        elif changed == "promote-cases":
            proof["case_execution_records"] = [{"fake": True}]
        elif changed == "promote-independent":
            proof["independent_performance_audit_verified"] = True
        elif changed == "promote-raw":
            proof["independent_raw_stdout_per_candidate_verified"] = True
        elif changed == "separate-stream":
            proof["streams"]["separate_stdout"] = proof["streams"]["combined_stdout_stderr"]
        elif changed == "extra-proof":
            proof["all_cases_verified"] = True
        else:
            proof["returncode"] = 2
        atomic_json(provenance.provenance_path(log), proof)
    with pytest.raises(InfrastructureError):
        cold(log, policy)


def test_cold_reader_refuses_missing_or_duplicate_logs(observed, policy):
    instance, variables, log, _, _ = observed
    instance._run("check", variables, log)
    for logs in ([], [str(log), str(log)], [str(log.with_name("missing.log"))]):
        with pytest.raises(InfrastructureError):
            provenance.command_stream_provenance(
                {"logs": logs, "commit": COMMIT, "tree_hash": TREE}, "neutral-experiment",
                expected_policy=policy, protocol_id=PROTOCOL,
            )


def test_legacy_no_observation_path_does_not_require_git_or_new_sidecar(observed, monkeypatch):
    instance, variables, log, calls, clean_calls = observed
    del instance.config["execution_provenance"]
    monkeypatch.setattr(provenance, "ensure_clean", lambda *args: pytest.fail("new provenance invoked"))
    instance._run("check", variables, log)
    assert len(calls) == 1 and clean_calls == []
    assert not provenance.provenance_path(log).exists()
