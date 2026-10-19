"""Inert local fixtures only; positive unit data cannot admit a production source."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import contracts, evaluator
from hpc_forest import native_r2max as native
from hpc_forest.core import InfrastructureError, Outcome, atomic_json, digest, file_digest
from hpc_forest.r2max_first_start import evaluation_provenance


@pytest.fixture(autouse=True)
def no_real_processes(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("No real process in unit fixtures"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("No real process in unit fixtures"))


@pytest.mark.parametrize("model,session", native.CELLS.items())
def test_closed_max_pairs(model, session):
    assert native.selected_identity({"model": model, "effort": "max", "session_id": session}) == (model, session)


@pytest.mark.parametrize("model,session", native.CELLS.items())
def test_exact_cache_binding_and_started_claim(model, session, tmp_path):
    auth = {"model": model, "effort": "max", "session_id": session, "job_id": "999999",
            "remote_root": "/UNIT/" + native.SCOPE + "-" + session,
            "artifacts": {"source_zip": {"sha256": "1" * 64}, "plan": {"sha256": "2" * 64}}}
    cache = tmp_path / "unit-cache"
    binding = native.bind_worker_cache(cache, auth)
    claim_root = cache / ("a" * 32)
    claim_root.mkdir()
    request = claim_root / "downloaded-request.json"
    atomic_json(request, {"model": model, "reasoning_effort": "max", "session_id": session})
    atomic_json(claim_root / "generation-claimed.json", {"request_sha256": file_digest(request)})
    assert native.bind_worker_cache(cache, auth) == binding
    atomic_json(request, {"model": "other", "reasoning_effort": "max", "session_id": session})
    with pytest.raises(InfrastructureError, match="Started claim"):
        native.bind_worker_cache(cache, auth)
    auth["job_id"] = "999998"
    with pytest.raises(InfrastructureError, match="different source/plan/job/session"):
        native.bind_worker_cache(cache, auth)


def test_old_unbound_cache_refused(tmp_path):
    (tmp_path / "old-response.json").write_text("UNIT_ONLY")
    model = next(iter(native.CELLS))
    auth = {"model": model, "effort": "max", "session_id": native.CELLS[model], "job_id": "999999",
            "remote_root": "/UNIT", "artifacts": {"source_zip": {"sha256": "1" * 64}, "plan": {"sha256": "2" * 64}}}
    with pytest.raises(InfrastructureError, match="Unbound nonempty"):
        native.bind_worker_cache(tmp_path, auth)


@pytest.mark.parametrize("model,effort,session", [
    ("gpt-6-luna", "max", native.LUNA_SESSION),
    ("gpt-6-astra", "xhigh", native.CELLS["gpt-6-astra"]),
    ("gpt-6-astra", "medium", native.CELLS["gpt-6-astra"]),
    ("gpt-6-astra", "max", native.CELLS["gpt-6.1-sol"]),
    ("unknown", "max", "0" * 32),
])
def test_replay_nonmax_and_mixed_identity_refused(model, effort, session):
    with pytest.raises(InfrastructureError):
        native.selected_identity({"model": model, "effort": effort, "session_id": session})


def unit_luna_proofs(tmp_path):
    """Clearly synthetic files used to exercise the reader, not deployment receipts."""
    def save(name, value):
        path = tmp_path / name
        atomic_json(path, value)
        return {"path": str(path), "sha256": file_digest(path)}
    common = {"model": "gpt-6-luna", "effort": "max", "session_id": native.LUNA_SESSION,
              "job_id": "751992", "source_zip_sha256": native.LUNA_SOURCE, "plan_sha256": native.LUNA_PLAN}
    first = save("unit-first.json", {**common, "schema": "hpc-forest-primes-r2max-first-start-verified-v1",
        "verified": True, "technical_errors_found": False, "invocation_unknown": False,
        "first_normal_delivered_call": {"unit": True}, "first_real_evaluation": {"unit": True}})
    audit = save("unit-audit.json", {**common, "verified": False,
        "schema": "hpc-forest-primes-r2max-readonly-audit-v1", "scope_id": "hpc-forest-primes-native-max-r1",
        "preparation_manifest_sha256": native.PREPARATION_MANIFEST_SHA256,
        "independent_raw_stdout_per_candidate_verified": False, "independent_performance_audit_verified": False,
        "received_cohort_audited_with_explicit_raw_attribution_limit": True, "unit_fixture_only": True})
    inert = save("unit-inert.json", {"unit_fixture_only": True})
    closure = save("unit-closure.json", {**common, "schema": "hpc-forest-primes-r2max-luna-closure-admission-v1",
        "first_start_sha256": first["sha256"], "operator_bounded_acceptance": True,
        "received_cohort_audited_with_explicit_raw_attribution_limit": True,
        "raw_attribution_limit_preserved": True, "independent_performance_validation": False,
        "all_started_calls_reconciled": True, "owned_worker_absence_verified": True,
        "archive": inert, "audit": audit, "reconciliation": inert, "owned_worker_absence": inert})
    return {"luna_first_start": Path(first["path"]), "luna_closure": Path(closure["path"])}, save


def test_bounded_luna_reader_preserves_false_independent_audit(tmp_path):
    paths, _ = unit_luna_proofs(tmp_path)
    native.verify_luna_release(paths)
    closure = native.read_json(paths["luna_closure"])
    audit_path = Path(closure["audit"]["path"])
    audit = native.read_json(audit_path)
    audit["verified"] = True
    atomic_json(audit_path, audit)
    closure["audit"]["sha256"] = file_digest(audit_path)
    atomic_json(paths["luna_closure"], closure)
    with pytest.raises(InfrastructureError, match="raw attribution"):
        native.verify_luna_release(paths)


@pytest.mark.parametrize("field", ["operator_bounded_acceptance", "raw_attribution_limit_preserved",
    "received_cohort_audited_with_explicit_raw_attribution_limit", "all_started_calls_reconciled",
    "owned_worker_absence_verified"])
def test_each_actual_luna_release_fact_required(tmp_path, field):
    paths, _ = unit_luna_proofs(tmp_path)
    closure = native.read_json(paths["luna_closure"])
    closure[field] = False
    atomic_json(paths["luna_closure"], closure)
    with pytest.raises(InfrastructureError):
        native.verify_luna_release(paths)


def case_fixture(tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    (trusted / "input.txt").write_bytes(b"PRIVATE_INPUT")
    binary = tmp_path / "inert-binary"
    binary.write_bytes(b"INERT_NOT_EXECUTABLE")
    case = {"name": "unit-case", "stdin": "input.txt", "argv": [], "files": [],
            "capture_files": [], "input_fingerprint": "declared-only"}
    return trusted, binary, case


def test_reference_duration_preserves_old_audit_and_output_work_excludes_new_hashes(tmp_path, monkeypatch):
    trusted, binary, case = case_fixture(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(contracts.time, "perf_counter", lambda: clock[0])
    original_audit, original_finish = contracts._audit_execution, contracts._finish_execution_audit
    original_blob, original_sha = contracts.blob, contracts.sha
    def fake_run(*args, **kwargs):
        kwargs["stdout"].write(b"UNIT_OUTPUT")
        clock[0] += 2
        return SimpleNamespace(returncode=0)
    def old_audit(*args):
        result = original_audit(*args)
        clock[0] += 3
        return result
    def old_blob(*args):
        clock[0] += 5
        return original_blob(*args)
    def added_hash(*args):
        clock[0] += 20
        return original_sha(*args)
    def added_sidecar(*args):
        clock[0] += 100
        return original_finish(*args)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(contracts, "_audit_execution", old_audit)
    monkeypatch.setattr(contracts, "_finish_execution_audit", added_sidecar)
    monkeypatch.setattr(contracts, "blob", old_blob)
    monkeypatch.setattr(contracts, "sha", added_hash)
    output, seconds = contracts.execute(binary, case, resources=trusted)
    assert seconds == 2 + 3 + 5
    assert output == {"stdout": original_blob(b"UNIT_OUTPUT")}
    audit_path = next((tmp_path / "private-audit/executions").glob("*/execution.json"))
    assert json.loads(audit_path.read_text()) == {
        "case": "unit-case", "returncode": 0, "timed_out": False, "never_model_input": True}
    proof = native.read_json(audit_path.with_name("execution-provenance.json"))
    assert proof["historical_record"]["sha256"] == file_digest(audit_path)
    assert proof["execution_seconds"] == seconds and proof["experiment_id"] is None


def test_evaluator_links_actual_binary_input_context_and_combined_log(tmp_path, monkeypatch):
    trusted, binary, case = case_fixture(tmp_path)
    atomic_json(trusted / "contract.json", {"search": [case], "confirmation": [case], "benchmark": case})
    protocol = {"private_execution_audit": True, "check": ["NEVER_RUN", "{binary}", "{phase}"],
                "environment": {}, "build_timeout_seconds": 5, "timeout_seconds": 5}
    instance = evaluator.Evaluator(tmp_path, {"protocol": protocol, "target_id": "UNIT"}, {}, "UNIT_PROTOCOL", time.time() + 30)
    variables = {"worktree": str(tmp_path), "binary": str(binary), "phase": "search", "experiment_id": "UNIT_EXP",
                 "epoch": 3, "commit": "UNIT_COMMIT", "tree_hash": "UNIT_TREE"}
    def fake_child(*args, **kwargs):
        assert not any(k.startswith("HPC_FOREST_PRIVATE_") for k in kwargs["env"])
        kwargs["stdout"].write(b"PRIVATE_STDOUT")
        kwargs["stderr"].write(b"PRIVATE_STDERR")
        return SimpleNamespace(returncode=0)
    def fake_process(command, cwd, log, timeout, env):
        assert command == ["NEVER_RUN", str(binary), "search"]
        with monkeypatch.context() as scoped:
            for key, value in env.items():
                scoped.setenv(key, value)
            contracts.execute(binary, case, resources=trusted)
        log.write_bytes(b'{}\nPRIVATE_STDERR_ALREADY_COMBINED')
        return SimpleNamespace(returncode=1, timed_out=False, seconds=0.125, log=str(log))
    monkeypatch.setattr(subprocess, "run", fake_child)
    monkeypatch.setattr(evaluator, "run_process", fake_process)
    log = tmp_path / "correctness.log"
    result = instance._run("check", variables, log)
    assert result.returncode == 1 and result.seconds == 0.125
    proof = native.read_json(log.with_suffix(".log.private-execution.json"))
    assert proof["streams"]["combined_stdout_stderr"]["sha256"] == file_digest(log)
    assert proof["streams"]["separate_stderr"] is None and proof["streams"]["separate_stdout"] is None
    assert proof["binary_sha256_before"] == proof["binary_sha256_after"] == file_digest(binary)
    assert proof["experiment_id"] == "UNIT_EXP" and proof["phase"] == "search"
    assert proof["private_cases"][0]["case_sha256"] == digest(case)
    assert proof["private_cases"][0]["stdin_sha256"] == file_digest(trusted / "input.txt")
    private = native.read_json(Path(proof["case_execution_records"][0]["path"]))
    assert private["context"]["sha256"] == proof["context"]["sha256"]
    assert private["stdout"]["sha256"] == file_digest(Path(proof["case_execution_records"][0]["path"]).parent / "stdout.bin")
    assert len(evaluation_provenance({"logs": [str(log)]}, "UNIT_EXP")) == 1
    raw_path = Path(proof["case_execution_records"][0]["path"]).parent / "stderr.bin"
    raw_path.write_bytes(b"CHANGED")
    with pytest.raises(ValueError, match="stream changed"):
        evaluation_provenance({"logs": [str(log)]}, "UNIT_EXP")


@pytest.mark.parametrize("changed", ["binary", "input", "context"])
def test_private_provenance_mismatch_refused_before_child(tmp_path, monkeypatch, changed):
    trusted, binary, case = case_fixture(tmp_path)
    context = {"schema": "hpc-forest-private-evaluation-context-v1", "never_model_input": True,
               "experiment_id": "UNIT", "phase": "search", "operation": "check",
               "binary_sha256_before": file_digest(binary), "private_cases": [{"case_sha256": digest(case),
                   "stdin_sha256": file_digest(trusted / "input.txt"), "stdin_bytes": 13}]}
    path = tmp_path / "private-context.json"
    atomic_json(path, context)
    monkeypatch.setenv("HPC_FOREST_PRIVATE_CONTEXT", str(path))
    monkeypatch.setenv("HPC_FOREST_PRIVATE_CONTEXT_SHA256", file_digest(path))
    if changed == "context":
        atomic_json(path, {"tampered": True})
    else:
        (binary if changed == "binary" else trusted / "input.txt").write_bytes(b"CHANGED")
    with pytest.raises(contracts.ContractError, match="Private|unrelated"):
        contracts.execute(binary, case, resources=trusted)


def test_benchmark_receives_no_private_pointer_and_retains_combined_stream(tmp_path, monkeypatch):
    trusted, binary, case = case_fixture(tmp_path)
    atomic_json(trusted / "contract.json", {"search": [case], "confirmation": [case], "benchmark": case})
    protocol = {"private_execution_audit": True, "benchmark": ["INERT_BENCHMARK", "{binary}"],
                "environment": {"OMP_NUM_THREADS": "4"}, "timeout_seconds": 5}
    instance = evaluator.Evaluator(tmp_path, {"protocol": protocol, "target_id": "UNIT"}, {}, "UNIT", time.time() + 30)
    variables = {"worktree": str(tmp_path), "binary": str(binary), "phase": "search", "experiment_id": "UNIT",
                 "epoch": 1, "commit": "UNIT", "tree_hash": "UNIT"}
    def fake_process(command, cwd, log, timeout, env):
        assert env == {"OMP_NUM_THREADS": "4"}
        log.write_bytes(b"stdout_and_original_stderr_together")
        return SimpleNamespace(returncode=2, timed_out=False, seconds=0.25, log=str(log))
    monkeypatch.setattr(evaluator, "run_process", fake_process)
    log = tmp_path / "sample.log"
    assert instance._run("benchmark", variables, log).returncode == 2
    assert log.read_bytes() == b"stdout_and_original_stderr_together"


def test_official_trace_qualification_refuses_windows_before_work(tmp_path, monkeypatch):
    from hpc_forest import r2max_trace_qualification as module
    monkeypatch.setattr(native.platform, "system", lambda: "Windows")
    with pytest.raises(InfrastructureError, match="Linux ARM64"):
        module.qualify_trace({}, tmp_path / "must-not-exist", {})
    assert not (tmp_path / "must-not-exist").exists()


def test_official_trace_flow_is_not_a_model_or_first_start(tmp_path, monkeypatch):
    from hpc_forest import r2max_trace_qualification as module
    source = tmp_path / "source"
    official = source / "src/model-view/primetest.c"
    official.parent.mkdir(parents=True)
    official.write_bytes(b"INERT_UNIT_C_NEVER_COMPILED")
    validation = tmp_path / "validation"
    validation.mkdir()
    (validation / "unit.txt").write_text("UNIT")
    monkeypatch.setattr(module, "REFERENCE_SHA256", file_digest(official))
    allocation = {"job_id": "999999", "unit_only": True}
    monkeypatch.setattr(module, "allocation_guard", lambda: allocation)
    calls = []
    def snapshot(start, target):
        import shutil
        shutil.copytree(start, target)
        return "UNIT_NO_GIT_OR_PROCESS"
    class NeutralEvaluator:
        def __init__(self, root, config, manifest, protocol_id, deadline):
            assert config["protocol"]["private_execution_purpose"] == module.PURPOSE
            self.protocol_id = protocol_id
        def evaluate(self, experiment, epoch, worktree, commit, baseline):
            calls.append(("search", experiment))
            return Outcome("valid", correct=True, times=[1.0] * 3)
        def confirm(self, rows, epoch):
            calls.append(("confirmation", rows[0]["id"]))
            return {rows[0]["id"]: Outcome("valid", correct=True, times=[1.0] * 5)}
    monkeypatch.setattr(module, "initialize_source", snapshot)
    monkeypatch.setattr(module, "Evaluator", NeutralEvaluator)
    monkeypatch.setattr(module, "evaluation_provenance", lambda *a, **k: [{"unit_fixture_only": True}])
    proof = module.qualify_trace({"source": str(source), "validation": str(validation), "protocol_timeout_seconds": 5},
                                tmp_path / "trace", allocation)
    assert calls == [("search", module.PURPOSE), ("confirmation", module.PURPOSE)]
    assert proof["native_model_calls"] == proof["new_model_candidates"] == 0
    assert proof["native_first_start_proved"] is proof["performance_research_result"] is False


def test_old_qualification_cannot_prove_new_trace():
    with pytest.raises(InfrastructureError, match="own official Evaluator"):
        native.verify_trace_members({}, lambda name: pytest.fail("No prior trace to read"))
