"""Neutral continuation regressions; no operational observation is manufactured.

The real static package may be read and checked. Every generated test artifact is
temporary, and no test constructs a complete positive assembly or a release.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admission = load_file("neutral_matrix15_extension_admission", HERE / "dynamic_admission.py")
capacity = load_file("neutral_matrix15_extension_capacity", HERE / "capacity.py")
selection = load_file("neutral_matrix15_extension_selection", HERE / "selection.py")
gate_validator = load_file("neutral_matrix15_extension_gate", HERE / "extension_gate.py")
STATICS = BASE / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2/STATICS.json"


@pytest.fixture(autouse=True)
def forbid_operational_actions(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Neutral extension test attempted a process, live census or capacity acquisition")

    monkeypatch.setitem(sys.modules, "capacity", capacity)
    monkeypatch.setitem(sys.modules, "selection", selection)
    monkeypatch.setitem(sys.modules, "extension_gate", gate_validator)
    monkeypatch.setattr(admission.subprocess, "run", forbidden)
    monkeypatch.setattr(admission.subprocess, "Popen", forbidden)
    monkeypatch.setattr(capacity, "collect_windows", forbidden)
    monkeypatch.setattr(capacity, "exclusive_capacity", forbidden)


def write_ref(tmp_path, name, value):
    path = tmp_path / name
    path.write_bytes(admission.raw_json(value))
    return admission.reference(path.resolve())


def gate_candidate():
    """Intentionally incomplete; it cannot pass the real portable validator."""
    return {"schema": gate_validator.SCHEMA, "verified": True, "evidence_origin": "received",
            "source_zip_sha256": admission.SOURCE_SHA256, "plan_sha256": admission.PLAN_SHA256}


def inventory_candidate():
    """An empty receipt inventory never establishes received native evidence."""
    return {"schema": "hpc-forest-matrix15-extension-received-evidence-v1",
            "evidence_origin": "received", "received": [], "local_refs": []}


def test_input_template_remains_an_incomplete_preparation_request():
    inputs = admission.template()
    assert inputs["schema"] == "hpc-forest-matrix15-dynamic-extension-input-v1"
    assert inputs["mode"] == "PREPARE" and inputs["cell_key"] is None
    assert inputs["first_batch_extension_gate"] is None
    assert inputs["first_batch_received_evidence"] is None
    assert inputs["selection_state"] is None
    assert inputs["capacity_registry"] is None and inputs["capacity_evidence"] is None
    assert "verified" not in inputs


def test_prepare_reads_pinned_runtime_and_emits_only_false_local_preparation(tmp_path):
    output = tmp_path / "NEUTRAL-preparation"
    result = admission.prepare(output)
    inputs = admission.read(admission.verified_ref(result))
    preparation = admission.read(output / "PREPARATION.json")
    state = admission.read(output / "ETAT-PREPARATOIRE-60.json")
    selected = admission.read(output / "SELECTION-PREPARATOIRE.json")
    assert inputs == admission.template()
    assert preparation["mode"] == "PREPARE" and preparation["verified"] is False
    assert preparation["native_model_calls"] == preparation["jobs_submitted"] == 0
    assert preparation["capacity_observed"] is preparation["first_batch_release_received"] is False
    assert preparation["automatic_extension"] is False
    assert {"cell_key", "first_batch_extension_gate", "first_batch_received_evidence", "selection_state"} <= set(preparation["missing"])
    assert all(inputs[key] is None for key in preparation["missing"])
    assert state["verified"] is False and state["mode"] == "PREPARE" and len(state["records"]) == 60
    assert {row["cell_key"] for row in state["records"]} == set(admission.contract.REGISTERED_CELLS)
    assert len({row["session_id"] for row in state["records"]}) == 60
    assert selected["verified"] is False and selected["commands_to_execute"] == []
    assert selected["prerequisite_pending"] is True and len(selected["candidates"]) == 59
    assert admission.FIRST_CELL not in {cell["cell_key"] for cell in selected["candidates"]}
    assert not any("authorization" in path.name.casefold() for path in output.iterdir())


@pytest.mark.parametrize("cell_key", ["unknown", "forest-r2/gpt-6-luna/max/primes/seed-23",
    "forest-r2/gpt-6-luna/high/2020-quicksort/seed-23", "forest-r2/unknown/max/2020-quicksort/seed-23"])
def test_unregistered_subject_model_or_nonmax_cell_is_refused_before_output(tmp_path, cell_key):
    output = tmp_path / "NEUTRAL-wrong-cell"
    with pytest.raises(admission.InfrastructureError, match="registered continuation identity"):
        admission.prepare(output, cell_key)
    assert not output.exists()


def test_cli_select_prints_false_candidates_and_no_command(tmp_path, capsys):
    state = write_ref(tmp_path, "NEUTRAL-state.json", selection.template_state())
    assert admission.main(["select", "--state", state["path"], "--limit", "60"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verified"] is False and result["commands_to_execute"] == []
    assert result["prerequisite_pending"] is True and len(result["candidates"]) == 59


@pytest.mark.parametrize("mode", ["PREPARE", "ASSEMBLE"])
def test_incomplete_input_cannot_acquire_capacity_or_create_authorization(tmp_path, mode):
    inputs = admission.template()
    inputs["mode"] = mode
    ref = write_ref(tmp_path, "NEUTRAL-incomplete-input.json", inputs)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(admission.InfrastructureError, match="PREPARE/missing inputs"):
        admission.assemble(ref)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_real_static_package_keeps_source_plan_and_registered_sixty_exact():
    refs, plan, _aliases = admission.static_inputs(admission.reference(STATICS.resolve()))
    assert refs["source_zip"]["sha256"] == admission.SOURCE_SHA256 == selection.SOURCE_SHA
    assert refs["plan"]["sha256"] == admission.PLAN_SHA256 == selection.PLAN_SHA
    assert plan["source_zip_sha256"] == admission.SOURCE_SHA256
    assert len(plan["cells"]) == 60
    assert {cell["cell_key"] for cell in plan["cells"]} == set(admission.contract.REGISTERED_CELLS)
    assert {cell["effort"] for cell in plan["cells"]} == {"max"}


@pytest.mark.parametrize("key", ["source_zip", "plan"])
def test_static_pin_drift_is_refused_before_any_capacity(tmp_path, key):
    value = copy.deepcopy(admission.read(STATICS.resolve()))
    value["artifacts"][key]["sha256"] = "0" * 64
    ref = write_ref(tmp_path, "NEUTRAL-drifted-statics.json", value)
    with pytest.raises(admission.InfrastructureError, match="unchanged source"):
        admission.static_inputs(ref)


@pytest.mark.parametrize("missing", ["gate", "inventory"])
def test_missing_gate_or_received_inventory_is_refused(tmp_path, missing):
    gate = write_ref(tmp_path, "NEUTRAL-gate.json", gate_candidate())
    inventory = write_ref(tmp_path, "NEUTRAL-inventory.json", inventory_candidate())
    with pytest.raises(admission.InfrastructureError, match="path/SHA reference"):
        admission.verify_extension_gate(None if missing == "gate" else gate,
                                        None if missing == "inventory" else inventory)


@pytest.mark.parametrize("change", ["schema", "origin", "missing-local", "missing-received", "extra-field"])
def test_malformed_received_inventory_is_refused_before_gate_evaluation(tmp_path, change):
    gate = write_ref(tmp_path, "NEUTRAL-gate.json", gate_candidate())
    value = inventory_candidate()
    if change == "schema":
        value["schema"] = "not-the-received-evidence-schema"
    elif change == "origin":
        value["evidence_origin"] = "unspecified"
    elif change == "extra-field":
        value["unexpected"] = True
    else:
        value.pop("local_refs" if change == "missing-local" else "received")
    ref = write_ref(tmp_path, "NEUTRAL-invalid-inventory.json", value)
    with pytest.raises(admission.InfrastructureError, match="received first-batch evidence inventory"):
        admission.verify_extension_gate(gate, ref)


@pytest.mark.parametrize("fixture", [{"verified": False}, {"synthetic": True}, {"prepared": True},
    {"fixture": True}, {"test_only": True}, {"evidence_origin": "fixture"}])
def test_fixture_gate_cannot_reach_received_inventory_or_capacity(tmp_path, fixture):
    value = {**gate_candidate(), **fixture}
    gate = write_ref(tmp_path, "NEUTRAL-fixture-gate.json", value)
    # No inventory is supplied: the gate itself must fail first.
    with pytest.raises(admission.InfrastructureError, match="negative|synthetic|Fixture"):
        admission.verify_extension_gate(gate, None)


@pytest.mark.parametrize("which", ["gate", "inventory"])
def test_gate_and_inventory_are_rehashed_before_received_validation(tmp_path, which):
    gate = write_ref(tmp_path, "NEUTRAL-gate.json", gate_candidate())
    inventory = write_ref(tmp_path, "NEUTRAL-inventory.json", inventory_candidate())
    ref = gate if which == "gate" else inventory
    Path(ref["path"]).write_bytes(b"{}")
    with pytest.raises(admission.InfrastructureError, match="bytes changed"):
        admission.verify_extension_gate(gate, inventory)


def test_empty_received_inventory_never_becomes_a_positive_gate(tmp_path):
    gate = write_ref(tmp_path, "NEUTRAL-gate.json", gate_candidate())
    inventory = write_ref(tmp_path, "NEUTRAL-inventory.json", inventory_candidate())
    with pytest.raises(ValueError, match="Bounded received inventory"):
        admission.verify_extension_gate(gate, inventory)


def test_selection_import_uses_the_same_source_pin_in_output_delivery_layout(tmp_path):
    root = tmp_path / "NEUTRAL-root"
    destination = root / "outputs/NEUTRAL-delivery/selection.py"
    destination.parent.mkdir(parents=True)
    contract = root / "work/matrix15-admission-no-cycle-r2/project/src/hpc_forest/matrix15_contract.py"
    contract.parent.mkdir(parents=True)
    shutil.copyfile(HERE / "selection.py", destination)
    shutil.copyfile(admission.PROJECT / "src/hpc_forest/matrix15_contract.py", contract)
    delivered = load_file("neutral_matrix15_delivered_selection", destination)
    assert delivered.CONTRACT_PATH == contract
    assert delivered.CONTRACT_SHA == selection.CONTRACT_SHA
    assert len(delivered.template_state()["records"]) == 60


@pytest.mark.parametrize("value", [
    {"kind": "source-proposal", "nonce": "1" * 32,
     "messages": [{"role": "user", "content": "// neutral element; fixture is ordinary source data"}]},
    {"nonce": "1" * 32, "infrastructure_error": False,
     "source_proposal": {"changes": [{"path": "src/main.c", "content": "// neutral element\n// fixture input\n"}]}},
    {"schema": "hpc-forest-matrix15-generic-command-evaluation-v1", "never_model_input": True,
     "outcome": {"status": "incorrect", "verified": False, "diagnostic": "fixture mismatch; neutral source comment"}},
])
def test_scientific_source_and_negative_outcomes_are_not_fixture_classified(tmp_path, value):
    ref = write_ref(tmp_path, "received-scientific-data.json", value)
    path = admission.verified_ref(ref)
    before = path.read_bytes()
    admission.check_received_metadata(path)
    assert path.read_bytes() == before
    assert admission.reference(path) == ref
    assert not list(tmp_path.glob("authorization*"))


@pytest.mark.parametrize("metadata", [
    {"verified": False}, {"evidence_origin": "neutral"}, {"fixture": True},
    {"synthetic": True}, {"test_only": True}, {"prepared": True}, {"neutral": True},
])
def test_negative_or_prepared_typed_receipt_metadata_is_still_refused(tmp_path, metadata):
    ref = write_ref(tmp_path, "received-control-receipt.json", {
        "schema": "hpc-forest-matrix15-extension-first-batch-root-review-v1", **metadata})
    with pytest.raises(admission.InfrastructureError, match="typed receipt"):
        admission.check_received_metadata(admission.verified_ref(ref))
