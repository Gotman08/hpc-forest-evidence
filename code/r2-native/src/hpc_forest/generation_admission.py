"""Pure admission check for an uninterrupted, bounded generation episode.

Callers must invoke this before creating a trial or starting a generation call.
This check never extends a deadline, changes a configuration, or resets a budget.
"""

from __future__ import annotations

import math
import time
from typing import Any

from .core import BudgetExhausted, ForestError

SCHEMA = "hpc-forest-full-generation-window-v1"
_POLICY_KEYS = {"schema", "minimum_episode_seconds"}


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    """Accept only finite plain JSON numbers, excluding bool and subclasses."""
    if type(value) not in (int, float):
        raise ForestError(f"{name} must be a finite plain int or float")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ForestError(f"{name} must be finite") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        relation = "positive" if positive else "nonnegative"
        raise ForestError(f"{name} must be finite and {relation}")
    return number


def generation_admission_policy(config: dict) -> dict | None:
    """Validate the optional policy without observing a clock or changing state."""
    if not isinstance(config, dict) or not isinstance(config.get("budget"), dict):
        raise ForestError("generation admission requires a budget object")
    budget = config["budget"]
    if "generation_admission" not in budget:
        return None

    policy = budget["generation_admission"]
    if type(policy) is not dict or set(policy) != _POLICY_KEYS:
        raise ForestError("generation_admission must contain exactly schema and minimum_episode_seconds")
    if policy["schema"] != SCHEMA:
        raise ForestError(f"generation_admission schema must be {SCHEMA}")
    minimum = _number(policy["minimum_episode_seconds"], "minimum_episode_seconds", positive=True)
    generation = _number(budget.get("generation_seconds"), "generation_seconds", positive=True)
    confirmation = _number(budget.get("confirmation_seconds"), "confirmation_seconds")
    if minimum > generation:
        raise ForestError("minimum_episode_seconds must not exceed generation_seconds")
    return {"minimum_episode_seconds": minimum, "confirmation_seconds": confirmation}


def require_generation_window(
    config: dict,
    campaign_deadline: float,
    *,
    now: float | None = None,
    purpose: str = "node",
) -> dict:
    """Require the full episode in the existing clock; an absent policy is legacy.

    Malformed policies raise ForestError. Insufficient wall time raises
    BudgetExhausted. Equality at the admission threshold is allowed.
    """
    policy = generation_admission_policy(config)
    if policy is None:
        return {"enabled": False}
    minimum = policy["minimum_episode_seconds"]
    confirmation = policy["confirmation_seconds"]
    deadline = _number(campaign_deadline, "campaign_deadline")
    observed_at = _number(time.time() if now is None else now, "now")
    if not isinstance(purpose, str) or not purpose:
        raise ForestError("generation admission purpose must be a nonempty string")

    search_deadline = deadline - confirmation
    available = search_deadline - observed_at
    if available < minimum:
        raise BudgetExhausted(
            f"Full generation window unavailable for {purpose}: "
            f"{available:.6f}s remaining, {minimum:.6f}s required"
        )
    return {
        "enabled": True,
        "schema": SCHEMA,
        "purpose": purpose,
        "observed_at": observed_at,
        "campaign_deadline": deadline,
        "search_deadline": search_deadline,
        "minimum_episode_seconds": minimum,
        "available_seconds": available,
        "budget_reset": False,
    }
