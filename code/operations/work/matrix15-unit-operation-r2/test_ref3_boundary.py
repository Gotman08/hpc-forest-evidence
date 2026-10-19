"""Real serialized-input boundary regression, with immutable received gate bytes."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).with_name("materialize_unit.py")
spec = importlib.util.spec_from_file_location("unit_ref3", PATH)
unit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unit)
OLD = unit.BASE / "outputs/HPC-Forest-Matrice15-Unit-Operation-Preparation-r1/sol-count-materialisation-r1/stage/INPUT-BOOTSTRAP.json"
NEW = unit.OUTPUT / "sol-count-corrected-input-r1/stage/INPUT-BOOTSTRAP.json"
PRIOR = unit.BASE / "outputs/HPC-Forest-Matrice15-Extension-Gate-Packet-r1/finalisation-r3/PREREQUISITES.json"


def boundary():
    builder, _upstream, _reader, dynamic, _capacity, bootstrap, _prefix = unit.runtime()
    helper = bootstrap.load_helper((builder.BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    prior = json.loads(PRIOR.read_bytes())
    evidence = dynamic.received_evidence(prior["first_batch_received_evidence"])
    # Read the emitted serialized input, not an unsaved Python object.
    emitted = json.loads(NEW.read_bytes())
    local = evidence.resolve(prior["gate_arm"])
    mapped = {**emitted["first_batch_gate"], "path": str(local)}
    return helper, evidence, mapped


def test_exact_regression_old_serialized_ref2_is_rejected():
    helper, _evidence, _mapped = boundary()
    old = json.loads(OLD.read_bytes())["first_batch_gate"]
    assert set(old) == {"path", "sha256"}
    with pytest.raises(ValueError, match="Exact bounded path/SHA/bytes reference"):
        helper.read_ref(old)


def test_real_serialized_ref3_crosses_original_read_ref_boundary():
    helper, evidence, mapped = boundary()
    assert set(mapped) == {"path", "sha256", "bytes"} and mapped["bytes"] == 3119
    data = helper.read_ref(mapped)
    assert len(data) == mapped["bytes"] and helper.sha(data) == mapped["sha256"]
    assert json.loads(data)["verified"] is True
    evidence.recheck()


@pytest.mark.parametrize("field,value", [("bytes", True), ("bytes", 3118), ("bytes", 3120), ("sha256", "0" * 64)])
def test_wrong_sized_reference_cannot_cross_boundary(field, value):
    helper, _evidence, mapped = boundary()
    with pytest.raises(ValueError):
        helper.read_ref({**mapped, field: value})


def test_only_semantic_change_is_actual_gate_byte_count():
    before = json.loads(OLD.read_bytes())
    after = json.loads(NEW.read_bytes())
    assert set(after["first_batch_gate"]) == {"path", "sha256", "bytes"}
    assert after["first_batch_gate"].pop("bytes") == 3119
    assert after == before
    assert unit.ref(OLD)["sha256"] == "b9d0cecb0f786eda04f6c66d7500e0eee226462c281f3800882cadf66ff2653f"


def test_normal_bootstrap_does_not_bypass_failed_admission_root():
    body = (NEW.parents[1] / "job-body.sh").read_text(encoding="utf8")
    assert "Admission root exists; no replay" in body
    assert "technical-resume" not in body
