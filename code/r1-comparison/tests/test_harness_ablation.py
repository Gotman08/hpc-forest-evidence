from datetime import UTC, datetime

import pytest

from hpc_forest.harness_ablation import (
    ARMS,
    EFFORTS,
    MODELS,
    admitted_subjects,
    allocation_fits,
    assert_fresh_root,
    assert_pair_contracts,
    available_lanes,
    cells_for,
    configure_arm,
    phase_ready,
    validate_cell,
)


def subjects():
    return ["2023-count", *[f"reviewed-{i}" for i in range(14)]]


def test_complete_six_hundred_cell_factorial():
    cells = cells_for(subjects())
    assert len(cells) == len({x["key"] for x in cells}) == 600
    for arm in ARMS:
        for model in MODELS:
            for effort in EFFORTS:
                assert len([x for x in cells if (x["arm"], x["model"], x["effort"])
                            == (arm, model, effort)]) == 15


def test_preparation_exclusions_do_not_become_model_failures():
    records = {x: {"status": "ready"} for x in subjects()}
    records["held-primes"] = {"status": "preparation_failed_no_model_called"}
    assert admitted_subjects({"records": records}) == subjects()


@pytest.mark.parametrize("bad", [[], subjects()[:-1], ["2023-count"] * 15])
def test_missing_or_repeated_subjects_are_rejected(bad):
    with pytest.raises(ValueError):
        cells_for(bad)


@pytest.mark.parametrize("field,value", [("model", "gpt-6-sol"), ("effort", "ultra"),
                                        ("arm", "mixed-harness"), ("seed", 24)])
def test_identity_substitution_is_rejected(field, value):
    cell = cells_for(subjects())[0]
    cell[field] = value
    with pytest.raises(ValueError):
        validate_cell(cell)


def test_codex_phase_waits_for_all_source_only_audits():
    cells = cells_for(subjects())
    assert not phase_ready("codex-native", cells)
    for cell in cells:
        if cell["arm"] == "source-only":
            cell.update(state="received_and_audited", final_attempt_accounted_for=True)
    assert phase_ready("codex-native", cells)
    cells[0]["final_attempt_accounted_for"] = False
    assert not phase_ready("codex-native", cells)


def test_no_third_native_worker():
    lanes = [{"current_state_verified": True, "released_after_audit": False} for _ in range(2)]
    assert available_lanes(lanes) == 0
    lanes[0]["released_after_audit"] = True
    assert available_lanes(lanes) == 1
    lanes[1]["current_state_verified"] = False
    with pytest.raises(ValueError):
        available_lanes(lanes)


def test_deadline_and_reception_reserve_are_exclusive():
    assert allocation_fits(datetime(2026, 10, 16, tzinfo=UTC), 11 * 3600)
    assert allocation_fits(datetime(2026, 10, 30, tzinfo=UTC), 60)
    assert not allocation_fits(datetime(2026, 10, 29, 23, tzinfo=UTC), 60, secondary_hypothesis=True)
    assert not allocation_fits(datetime(2026, 10, 30, 23, tzinfo=UTC), 60)
    assert not allocation_fits(datetime(2026, 10, 29, 23, tzinfo=UTC), 2 * 86400)


def test_no_harness_keeps_external_validation_and_disables_tools():
    original = {"harness": {"enabled": True, "max_attempts": 3}, "oracle": "exact"}
    configured = configure_arm(original, "source-only")
    assert configured["oracle"] == "exact"
    assert configured["harness"]["enabled"] is False
    assert configured["native_codex_agent"]["enabled"] is False
    assert original["harness"]["enabled"] is True


def test_native_codex_is_not_faked_by_enabling_custom_repair():
    with pytest.raises(ValueError, match="real, audited"):
        configure_arm({}, "codex-native")
    with pytest.raises(ValueError, match="real, audited"):
        configure_arm({}, "codex-native", {"scope_id": "wrong", "neutral_probe_received_and_audited": True})


def test_only_reference_calibration_is_allowed_to_differ():
    a = {"compiler_flags": ["-O3"], "benchmark": {"stdin": "x", "reference_seconds": 1},
         "confirmation": [{"expected": "exact"}]}
    b = {**a, "benchmark": {"stdin": "x", "reference_seconds": 2}}
    assert_pair_contracts(a, b)
    b["compiler_flags"] = ["-ffast-math"]
    with pytest.raises(ValueError):
        assert_pair_contracts(a, b)


def test_existing_campaign_is_never_reused(tmp_path):
    with pytest.raises(ValueError):
        assert_fresh_root(tmp_path)
    assert_fresh_root(tmp_path / "fresh")


def test_missing_concrete_admission_cannot_start_generation(tmp_path):
    import json

    from hpc_forest.harness_ablation import verify_authorization

    receipt = tmp_path / "auth.json"
    receipt.write_text(json.dumps({"model": "gpt-6-luna", "effort": "low",
                                    "arm": "source-only"}), encoding="utf-8")
    with pytest.raises(ValueError, match="concrete comparison admission"):
        verify_authorization(receipt, {"hpc-forest-harness-comparison-20261016-r1"})


def test_source_only_runtime_rejects_native_treatment_before_adapter_validation(monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "examples/marathon22/ablation_matrix.py"
    monkeypatch.syspath_prepend(str(path.parent))
    text = path.read_text(encoding="utf-8")
    assert 'choices=["source-only"]' in text
    spec = importlib.util.spec_from_file_location("source_only_matrix", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.select_subjects({"ready": {"status": "ready"},
                                   "held": {"status": "preparation_failed_no_model_called"}}) == ["ready"]
