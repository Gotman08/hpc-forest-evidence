"""NEUTRAL helper tests; never an operational observation or authorization.

Real temporary bytes and SHA references are used, but every observation example
is visibly synthetic. Process execution and live capacity collection are forbidden.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import capacity
import dynamic_admission as admission
import pytest


@pytest.fixture(autouse=True)
def forbid_operational_actions(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("NEUTRAL test attempted a process, live census or capacity acquisition")

    monkeypatch.setattr(admission.subprocess, "run", forbidden)
    monkeypatch.setattr(capacity, "collect_windows", forbidden)
    monkeypatch.setattr(capacity, "exclusive_capacity", forbidden)


@pytest.fixture
def prepared_runtime(monkeypatch):
    calls = []

    def load():
        calls.append("runtime-check-only")
        return {"verified": False, "test_only": True}

    monkeypatch.setattr(admission, "load_runtime", load)
    return calls


def test_canonical_json_and_hash_are_exact_bytes():
    raw = admission.raw_json({"z": "NEUTRAL é", "a": 1})
    assert raw == '{"a":1,"z":"NEUTRAL é"}\n'.encode()
    assert admission.sha(raw) == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_json_refuses_nonfinite_numbers(value):
    with pytest.raises(ValueError):
        admission.raw_json({"NEUTRAL": value})


def test_exclusive_create_round_trips_actual_json_and_raw_bytes(tmp_path):
    value = {"schema": "NEUTRAL-only", "verified": False, "test_only": True}
    ref = admission.create(tmp_path / "NEUTRAL/deep/value.json", value)
    path = admission.verified_ref(ref)
    assert admission.read(path) == value
    assert path.read_bytes() == admission.raw_json(value)
    assert ref["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    raw = b"NEUTRAL\x00\xff\r\n"
    raw_ref = admission.create(tmp_path / "NEUTRAL/raw.bin", raw)
    assert admission.verified_ref(raw_ref).read_bytes() == raw


def test_create_never_overwrites_prior_bytes(tmp_path):
    path = tmp_path / "NEUTRAL-existing.json"
    ref = admission.create(path, {"verified": False, "test_only": True})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        admission.create(path, b"NEUTRAL replacement forbidden")
    assert path.read_bytes() == original
    assert admission.verified_ref(ref) == path


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra-field", "bad-sha", "relative"])
def test_verified_reference_requires_exact_shape_path_and_current_bytes(tmp_path, mutation):
    ref = admission.create(tmp_path / "NEUTRAL-ref.json", {"verified": False, "test_only": True})
    if mutation == "changed":
        Path(ref["path"]).write_bytes(b"NEUTRAL changed")
    elif mutation == "missing":
        Path(ref["path"]).unlink()
    elif mutation == "extra-field":
        ref["verified"] = False
    elif mutation == "bad-sha":
        ref["sha256"] = "not-a-sha"
    else:
        ref["path"] = "NEUTRAL-relative.json"
    with pytest.raises(admission.InfrastructureError):
        admission.verified_ref(ref)


def test_read_rejects_duplicate_json_fields(tmp_path):
    ref = admission.create(tmp_path / "NEUTRAL-duplicate.json", b'{"verified":false,"verified":false}')
    with pytest.raises(admission.InfrastructureError):
        admission.read(ref["path"])


@pytest.mark.parametrize("relative", ["NEUTRAL-relative.json", "NEUTRAL/../value.json"])
def test_ordinary_requires_an_absolute_path(relative):
    with pytest.raises(admission.InfrastructureError):
        admission.ordinary(relative, exists=False)


@pytest.mark.parametrize("value", [
    {"message": "NEUTRAL only"}, {"message": "not-an-admission"}, {"message": "fixture data"},
    {"synthetic": True}, {"prepared": True}, {"test_only": True},
    {"evidence": [{"synthetic": True}]}, {"evidence": {"message": "NEUTRAL"}},
])
def test_fixture_claims_cannot_be_promoted_to_operational_evidence(value):
    with pytest.raises(admission.InfrastructureError):
        admission.reject_fixture(value)


def test_a_field_name_is_not_itself_a_fixture_value():
    admission.reject_fixture({"neutral_tests_passed": False})


@pytest.mark.parametrize("observed,now", [(1000, 1000), (1000.0, 1600.0), (1000, 1000.1)])
def test_fresh_accepts_only_typed_current_observations(observed, now):
    admission.fresh(observed, now)


@pytest.mark.parametrize("observed,now", [
    (1000, 1600.01), (1001, 1000), (True, 1000), (1000, True), ("1000", 1000),
    (1000, "1000"), (None, 1000), (float("nan"), 1000), (1000, float("nan")),
    (float("inf"), 1000), (1000, float("inf")),
])
def test_stale_future_untyped_or_nonfinite_observations_fail(observed, now):
    with pytest.raises(admission.InfrastructureError):
        admission.fresh(observed, now)


def test_pointer_selects_the_exact_structured_content_without_searching():
    raw = {"structuredContent": {"jobs": [{"job_id": "NEUTRAL-a"}, {"job_id": "NEUTRAL-b"}]},
           "content": [{"text": "NEUTRAL-b"}]}
    assert admission.pointer(raw, ["structuredContent", "jobs", 1, "job_id"]) == "NEUTRAL-b"
    assert raw["structuredContent"]["jobs"][0]["job_id"] == "NEUTRAL-a"


@pytest.mark.parametrize("pointer", [None, [], "structuredContent", [True], [1.0]])
def test_pointer_requires_a_nonempty_typed_explicit_path(pointer):
    with pytest.raises(admission.InfrastructureError):
        admission.pointer({"NEUTRAL": False}, pointer)


def test_primary_rejects_real_hashed_but_neutral_mcp_return(tmp_path):
    observation = {"schema": admission.OBS_SCHEMA, "tool": "mcp__romeo__job_status", "arguments": {"job_id": "NEUTRAL"},
        "response": {"structuredContent": {"job_id": "NEUTRAL"}}, "verified": False, "test_only": True}
    raw_ref = admission.create(tmp_path / "NEUTRAL-primary.json", observation)
    claim = {"raw": raw_ref, "pointer": ["structuredContent", "job_id"]}
    assert admission.pointer(admission.read(admission.verified_ref(raw_ref))["response"], claim["pointer"]) == "NEUTRAL"
    with pytest.raises(admission.InfrastructureError, match="Fixture|synthetic|operational"):
        admission.primary(claim, "NEUTRAL", tools={"mcp__romeo__job_status"})


def test_primary_rejects_changed_raw_mcp_bytes_before_projection(tmp_path):
    raw_ref = admission.create(tmp_path / "NEUTRAL-primary.json", {"verified": False, "test_only": True})
    Path(raw_ref["path"]).write_bytes(b"NEUTRAL changed raw MCP response")
    with pytest.raises(admission.InfrastructureError, match="bytes changed"):
        admission.primary({"raw": raw_ref, "pointer": ["structuredContent"]}, {}, tools=admission.TOOLS)


def test_prepare_writes_only_an_incomplete_false_template(tmp_path, prepared_runtime):
    output = tmp_path / "NEUTRAL-preparation"
    ref = admission.prepare(output)
    inputs = admission.read(admission.verified_ref(ref))
    preparation = admission.read(output / "PREPARATION.json")
    assert inputs == admission.template()
    assert inputs["mode"] == "PREPARE"
    assert all(inputs[key] is None for key in preparation["missing"])
    assert preparation["verified"] is False
    assert preparation["capacity_observed"] is False
    assert preparation["native_model_calls"] == preparation["jobs_submitted"] == 0
    assert preparation["inputs"] == ref
    assert set(path.name for path in output.iterdir()) == {
        "ENTREES-A-RENSEIGNER.json", "PREPARATION.json", "WORKER-TEMPLATE.json"}
    worker = admission.read(output / "WORKER-TEMPLATE.json")
    assert worker["argv"] == admission.worker_template()
    assert "--once" not in worker["argv"]
    assert prepared_runtime == ["runtime-check-only"]


def test_prepare_cannot_overwrite_an_existing_template(tmp_path, prepared_runtime):
    output = tmp_path / "NEUTRAL-preparation"
    admission.prepare(output)
    before = {path: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError):
        admission.prepare(output)
    assert {path: path.read_bytes() for path in output.iterdir()} == before


@pytest.mark.parametrize("kind", ["PREPARE", "incomplete", "NEUTRAL", "synthetic"])
def test_assemble_refuses_prepare_or_synthetic_inputs_before_any_capacity(tmp_path, prepared_runtime, kind):
    inputs = copy.deepcopy(admission.template())
    if kind == "incomplete":
        inputs["mode"] = "ASSEMBLE"
    elif kind == "NEUTRAL":
        inputs["mode"] = "NEUTRAL-ASSEMBLE"
    elif kind == "synthetic":
        inputs["mode"] = "ASSEMBLE"
        inputs["synthetic"] = True
    ref = admission.create(tmp_path / ("NEUTRAL-" + kind + ".json"), inputs)
    before = set(tmp_path.rglob("*"))
    with pytest.raises(admission.InfrastructureError):
        admission.assemble(ref)
    assert set(tmp_path.rglob("*")) == before


def test_failed_proof_checks_never_produce_a_verified_document():
    with pytest.raises(admission.InfrastructureError, match="Unproved"):
        admission.proof({"scope_id": "NEUTRAL"}, "transport_admission", {}, [], checks=[False])
