"""Scope, coverage and launch gates for the fresh, human-authorized harness comparison.

No candidate, optimization hint, model call or cluster submission is made here.
The existing R1 source and coordinator stay immutable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

MODELS = ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra")
EFFORTS = ("max", "xhigh", "high", "medium", "low")
ARMS = ("source-only", "codex-native")
SCOPE = "hpc-forest-harness-comparison-20261016-r1"
DEADLINE = datetime(2026, 10, 31, 23, tzinfo=UTC)
NATIVE_GATES = (
    "exact_model_effort_verified", "default_codex_instructions_preserved",
    "native_tools_executed_in_owned_arm64_allocation", "protected_holdout_unreadable",
    "sibling_sources_unreadable", "no_oauth_or_api_key_transferred",
    "native_usage_stream_verified", "shared_budget_stop_verified",
    "resume_without_generation_replay_verified", "source_archive_and_plan_verified",
)


def admitted_subjects(prepared):
    subjects = [key for key, value in prepared["records"].items() if value["status"] == "ready"]
    if len(subjects) != 15 or len(set(subjects)) != 15 or "2023-count" not in subjects:
        raise ValueError("Exactly the fifteen reviewed R1 subjects are required")
    return ["2023-count", *[key for key in subjects if key != "2023-count"]]


def cells_for(subjects):
    if len(subjects) != 15 or len(set(subjects)) != 15:
        raise ValueError("Fifteen distinct admitted subjects are required")
    return [{"key": f"{arm}/{model}/{effort}/{subject}/seed-23", "arm": arm,
             "model": model, "effort": effort, "subject": subject, "seed": 23,
             "state": "planned_not_started", "fresh_programs_required": True}
            for arm in ARMS for effort in EFFORTS for model in MODELS for subject in subjects]


def validate_cell(cell):
    if (cell.get("model") not in MODELS or cell.get("effort") not in EFFORTS
            or cell.get("arm") not in ARMS or cell.get("seed") != 23):
        raise ValueError("Cell is outside the exact authorized identity/effort/arm")


def phase_ready(arm, cells):
    if arm not in ARMS:
        raise ValueError("Unknown arm")
    if arm == "source-only":
        return True
    previous = [cell for cell in cells if cell["arm"] == "source-only"]
    return len(previous) == 300 and all(
        cell.get("state") == "received_and_audited"
        and cell.get("final_attempt_accounted_for") is True for cell in previous)


def allocation_fits(now, maximum_seconds, *, secondary_hypothesis=False):
    if now.tzinfo is None or maximum_seconds <= 0:
        raise ValueError("An explicit UTC-aware time and bounded allocation are required")
    # Paris is UTC+1 on these dates. The 31st is reception and delivery only.
    stop_secondary = datetime(2026, 10, 29, 23, tzinfo=UTC)
    stop_all_new_jobs = datetime(2026, 10, 30, 23, tzinfo=UTC)
    return (now < stop_all_new_jobs and (not secondary_hypothesis or now < stop_secondary)
            and now + timedelta(seconds=maximum_seconds, hours=3) < DEADLINE)


def available_lanes(observations):
    if any(not item.get("current_state_verified") for item in observations):
        raise ValueError("Do not admit a new worker from stale or unknown lane observations")
    active = [item for item in observations if not item.get("released_after_audit", False)]
    if len(active) > 2:
        raise ValueError("Existing native lane occupancy exceeds the authorized cap")
    return 2 - len(active)


def configure_arm(settings, arm, capability=None):
    if arm not in ARMS:
        raise ValueError("Unknown comparison arm")
    result = copy.deepcopy(settings)
    result["harness"] = {"enabled": False}
    result["experiment_arm"] = arm
    if arm == "codex-native":
        if (not capability or capability.get("scope_id") != SCOPE
                or capability.get("neutral_probe_received_and_audited") is not True
                or any(capability.get(name) is not True for name in NATIVE_GATES)
                or not capability.get("audited_probe_receipts")):
            raise ValueError("A real, audited native Codex capability gate is required")
        result["native_codex_agent"] = {"enabled": True,
                                       "custom_node_repair_loop_enabled": False,
                                       "execution_target": "owned-arm64-allocation"}
    else:
        result["native_codex_agent"] = {"enabled": False}
    return result


def comparable_contract(contract):
    """Remove allocation-local calibration only; keep every input, oracle and build flag."""
    result = copy.deepcopy(contract)
    if isinstance(result.get("benchmark"), dict):
        result["benchmark"].pop("reference_seconds", None)
    return result


def assert_pair_contracts(left, right):
    if comparable_contract(left) != comparable_contract(right):
        raise ValueError("Input, expected output, domain or compiler differs between arms")


def assert_fresh_root(path):
    if path.exists():
        raise ValueError("Never reuse a campaign root, candidate, registry or interrupted search")


def verify_authorization(path, required_scopes):
    """Do not generate from a plan alone: require a concrete audited launch admission."""
    from pathlib import Path

    receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_cell({**receipt, "seed": 23})
    if (receipt.get("schema") != "hpc-forest-harness-comparison-authorization-v1"
            or receipt.get("scope_id") != SCOPE or required_scopes != {SCOPE}
            or receipt.get("expires_at", 0) <= time.time()
            or receipt.get("old_candidates_imported") is not False
            or receipt.get("operator_algorithm_advice") is not False
            or receipt.get("mother_and_children_same_model_effort") is not True
            or receipt.get("native_lane_release_received_and_verified") is not True
            or receipt.get("arm64_preflight_received_and_audited") is not True
            or not receipt.get("user_messages") or len(receipt.get("session_id", "")) != 32):
        raise ValueError("Missing or invalid concrete comparison admission")
    for key in ("source_zip", "plan", "lane_admission", "arm64_preflight_audit"):
        item = receipt[key]
        source = Path(item["path"])
        if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("A bound comparison artifact changed: " + key)
    plan = json.loads(Path(receipt["plan"]["path"]).read_text(encoding="utf-8"))
    if (plan.get("scope_id") != SCOPE or plan.get("models") != list(MODELS)
            or plan.get("efforts") != list(EFFORTS) or plan.get("new_arms") != list(ARMS)):
        raise ValueError("Wrong frozen comparison plan")
    lane = json.loads(Path(receipt["lane_admission"]["path"]).read_text(encoding="utf-8"))
    if (lane.get("scope_id") != SCOPE or lane.get("session_id") != receipt["session_id"]
            or lane.get("current_state_verified") is not True
            or type(lane.get("active_native_workers_before_admission")) is not int
            or not 0 <= lane["active_native_workers_before_admission"] < 2
            or not lane.get("verified_dependency_release_receipts")):
        raise ValueError("No verified native lane release")
    preflight = json.loads(Path(receipt["arm64_preflight_audit"]["path"]).read_text(encoding="utf-8"))
    if (preflight.get("scope_id") != SCOPE or preflight.get("audit_passed") is not True
            or preflight.get("architecture") != "aarch64"
            or preflight.get("source_zip_sha256") != receipt["source_zip"]["sha256"]
            or preflight.get("protected_bytes_verified_before_after") is not True
            or preflight.get("compiler_tests_executed") is not True
            or preflight.get("model_calls") != 0):
        raise ValueError("No audited ARM64 preflight for this exact source")
    if receipt["arm"] == "codex-native":
        configure_arm({}, "codex-native", receipt.get("native_capability"))
    return receipt


def install_model_identity(model, effort, receipt_path=None):
    """Select one identity in this new process, never in an existing worker or global config."""
    from . import codex_process, codex_worker
    from .native_matrix import install_identity

    install_identity(model, effort)
    if receipt_path is not None:
        original = verify_authorization(receipt_path, {SCOPE})
        if (original["model"], original["effort"]) != (model, effort):
            raise ValueError("Worker identity differs from its concrete authorization")

    def gate(path, required_scopes):
        current = verify_authorization(path, required_scopes)
        if (current["model"], current["effort"]) != (model, effort):
            raise ValueError("Model or effort changed inside a comparison worker")
        return current

    codex_process.check_dependencies = gate
    codex_worker.check_dependencies = gate
