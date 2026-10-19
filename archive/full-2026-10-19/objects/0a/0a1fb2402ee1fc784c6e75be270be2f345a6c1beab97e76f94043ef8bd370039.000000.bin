"""Deterministic tests of the new R2 full-generation admission contract."""

from copy import deepcopy

import pytest

from hpc_forest.core import BudgetExhausted, ForestError
from hpc_forest.generation_admission import SCHEMA, require_generation_window


def admission_config():
    return {
        "budget": {
            "generation_seconds": 600.0,
            "confirmation_seconds": 120.0,
            "generation_admission": {"schema": SCHEMA, "minimum_episode_seconds": 600.0},
        }
    }


def test_absent_policy_preserves_legacy_behavior_without_clock_validation():
    assert require_generation_window({"budget": {}}, None, now=False) == {"enabled": False}


def test_exact_threshold_is_admitted_with_receipt_and_no_reset():
    config = admission_config()
    original = deepcopy(config)
    receipt = require_generation_window(config, 1720.0, now=1000.0, purpose="integration")
    assert receipt == {
        "enabled": True,
        "schema": SCHEMA,
        "purpose": "integration",
        "observed_at": 1000.0,
        "campaign_deadline": 1720.0,
        "search_deadline": 1600.0,
        "minimum_episode_seconds": 600.0,
        "available_seconds": 600.0,
        "budget_reset": False,
    }
    assert config == original


@pytest.mark.parametrize("remaining", [21.233, 381.863, 450.507, 599.999, 0.0, -1.0])
def test_short_or_elapsed_search_windows_are_refused(remaining):
    with pytest.raises(BudgetExhausted, match="Full generation window unavailable"):
        require_generation_window(admission_config(), 1120.0 + remaining, now=1000.0)


def test_confirmation_reserve_cannot_be_spent_on_generation():
    config = admission_config()
    with pytest.raises(BudgetExhausted):
        require_generation_window(config, 1600.0, now=1000.0)
    assert config["budget"]["confirmation_seconds"] == 120.0


def test_default_clock_is_observed_once(monkeypatch):
    observations = []

    def fixed_time():
        observations.append(1000.0)
        return 1000.0

    monkeypatch.setattr("hpc_forest.generation_admission.time.time", fixed_time)
    assert require_generation_window(admission_config(), 1720)["observed_at"] == 1000.0
    assert observations == [1000.0]


@pytest.mark.parametrize("minimum", [0.1, 1, 450.5, 600])
def test_positive_minimum_up_to_configured_generation_ceiling_is_supported(minimum):
    config = admission_config()
    config["budget"]["generation_admission"]["minimum_episode_seconds"] = minimum
    receipt = require_generation_window(config, 2000, now=1000)
    assert receipt["minimum_episode_seconds"] == minimum


def test_ceiling_uses_actual_configured_generation_seconds():
    config = admission_config()
    config["budget"]["generation_seconds"] = 30
    config["budget"]["generation_admission"]["minimum_episode_seconds"] = 30
    assert require_generation_window(config, 1150, now=1000)["available_seconds"] == 30
    config["budget"]["generation_admission"]["minimum_episode_seconds"] = 31
    with pytest.raises(ForestError, match="must not exceed generation_seconds"):
        require_generation_window(config, 2000, now=1000)


@pytest.mark.parametrize("bad", [False, True, float("nan"), float("inf"), -float("inf"), -1, "600", None])
@pytest.mark.parametrize("field", ["generation_seconds", "confirmation_seconds", "minimum_episode_seconds"])
def test_invalid_config_numbers_fail_closed(field, bad):
    config = admission_config()
    target = config["budget"]["generation_admission"] if field == "minimum_episode_seconds" else config["budget"]
    target[field] = bad
    with pytest.raises(ForestError):
        require_generation_window(config, 2000, now=1000)


@pytest.mark.parametrize("field", ["generation_seconds", "minimum_episode_seconds"])
def test_zero_episode_lengths_fail_closed(field):
    config = admission_config()
    target = config["budget"]["generation_admission"] if field == "minimum_episode_seconds" else config["budget"]
    target[field] = 0
    with pytest.raises(ForestError):
        require_generation_window(config, 2000, now=1000)


def test_zero_confirmation_reserve_is_valid():
    config = admission_config()
    config["budget"]["confirmation_seconds"] = 0
    assert require_generation_window(config, 1600, now=1000)["available_seconds"] == 600


@pytest.mark.parametrize("bad", [False, True, float("nan"), float("inf"), -float("inf"), -1, "1000"])
@pytest.mark.parametrize("field", ["campaign_deadline", "now"])
def test_invalid_clock_values_fail_closed(field, bad):
    values = {"campaign_deadline": 2000, "now": 1000}
    values[field] = bad
    with pytest.raises(ForestError):
        require_generation_window(admission_config(), **values)


def test_missing_deadline_is_rejected():
    with pytest.raises(ForestError):
        require_generation_window(admission_config(), None, now=1000)


@pytest.mark.parametrize("policy", [None, False, {}, {"schema": SCHEMA},
    {"minimum_episode_seconds": 600},
    {"schema": "unknown", "minimum_episode_seconds": 600},
    {"schema": SCHEMA, "minimum_episode_seconds": 600, "enabled": True}])
def test_malformed_or_unknown_policy_is_rejected(policy):
    config = admission_config()
    config["budget"]["generation_admission"] = policy
    with pytest.raises(ForestError):
        require_generation_window(config, 2000, now=1000)


@pytest.mark.parametrize("field", ["generation_seconds", "confirmation_seconds"])
def test_enabled_policy_requires_configured_time_fields(field):
    config = admission_config()
    del config["budget"][field]
    with pytest.raises(ForestError):
        require_generation_window(config, 2000, now=1000)


def test_admission_and_refusal_do_not_mutate_config_or_create_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = admission_config()
    original = deepcopy(config)
    before = list(tmp_path.iterdir())
    require_generation_window(config, 1720, now=1000)
    with pytest.raises(BudgetExhausted):
        require_generation_window(config, 1719, now=1000)
    assert config == original
    assert list(tmp_path.iterdir()) == before
