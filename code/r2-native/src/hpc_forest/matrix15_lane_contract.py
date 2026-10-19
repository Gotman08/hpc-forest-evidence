"""Typed minimal matrix lane projection; ARM never observes the Windows census."""
from __future__ import annotations

import json
import math
import time

from .matrix15_contract import need, reference, sha_value

LANE_SCHEMA = "hpc-forest-matrix15-worker-lane-admission-v1"
PROJECTION_SCHEMA = "hpc-forest-matrix15-owned-lane-projection-v1"
RESERVATION_SCHEMA = "hpc-forest-matrix15-single-slot-reservation-v1"
CELL_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
               "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
LANE_FIELDS = CELL_FIELDS | {"schema", "verified", "maximum_native_workers_total", "active_native_workers_before_start",
    "full_census_locally_verified", "new_cache_registry_root", "native_calls_started", "observed_at",
    "private_full_census_sha256", "minimal_owned_observations", "slot_reservation"}
PROJECTION_FIELDS = CELL_FIELDS | {"schema", "verified", "other_native_workers_count", "active_native_workers_before_start",
    "maximum_native_workers_total", "observed_at", "observation_origin", "windows_census_observed_by_arm",
    "full_census_exported", "foreign_configuration_or_credentials_exported", "evidence_sha256",
    "all_native_workers_known", "launcher_python_pairs_count_as_one", "source_only_active_workers"}
EVIDENCE_FIELDS = {"private_full_census", "global_slot_reservation", "reservation_producer_review",
                   "source_only_received_closure", "source_only_absence", "other_owned_worker_reconciliation",
                   "local_projection_producer_review"}
RESERVATION_FIELDS = CELL_FIELDS | {"schema", "verified", "reservation_id", "exclusive_global_lock_held_at_census",
    "all_native_workers_known", "launcher_python_pairs_count_as_one", "observed_at", "active_native_workers_before_start",
    "maximum_native_workers_total", "one_cell_only", "one_submission_only", "consumed", "private_full_census_sha256"}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "Duplicate matrix lane JSON field")
        value[key] = item
    return value


def validate_lane(lane, cell_binding, read_ref, *, initial=True, now=None):
    """Rehash transported projections; subsequent calls retain the initial immutable admission."""
    need(isinstance(cell_binding, dict) and set(cell_binding) == CELL_FIELDS, "Exact twelve-field matrix binding required")
    need(isinstance(lane, dict) and set(lane) == LANE_FIELDS and lane["schema"] == LANE_SCHEMA
         and lane["verified"] is True and all(lane[key] == value for key, value in cell_binding.items()),
         "Matrix lane belongs to another cell/source/contract")
    count = lane["active_native_workers_before_start"]
    need(type(count) is int and 0 <= count < 4 and type(lane["maximum_native_workers_total"]) is int
         and lane["maximum_native_workers_total"] == 4 and lane["full_census_locally_verified"] is True
         and lane["new_cache_registry_root"] is True and type(lane["native_calls_started"]) is int
         and lane["native_calls_started"] == 0, "No new global slot under cap4")
    instant = lane["observed_at"]
    current = time.time() if now is None else now
    need(number(current) and number(instant) and 0 <= current - instant
         and (not initial or current - instant <= 600), "Initial matrix lane is stale/future/invalid")
    need(sha_value(lane["private_full_census_sha256"]), "Private census digest required")
    projection = json.loads(read_ref(lane["minimal_owned_observations"]).read_text(encoding="utf8"),
                            object_pairs_hook=unique_object)
    need(isinstance(projection, dict) and set(projection) == PROJECTION_FIELDS
         and projection["schema"] == PROJECTION_SCHEMA and projection["verified"] is True
         and all(projection[key] == value for key, value in cell_binding.items()), "Exact minimal lane projection required")
    need(projection["observation_origin"] == "parent-private-Windows-census"
         and projection["windows_census_observed_by_arm"] is False and projection["full_census_exported"] is False
         and projection["foreign_configuration_or_credentials_exported"] is False
         and projection["all_native_workers_known"] is True and projection["launcher_python_pairs_count_as_one"] is True,
         "Unknown workers/private data/ARM Windows observation cannot admit a slot")
    need(type(projection["other_native_workers_count"]) is int and projection["other_native_workers_count"] == count
         and type(projection["source_only_active_workers"]) is int and projection["source_only_active_workers"] == 0
         and type(projection["active_native_workers_before_start"]) is int
         and projection["active_native_workers_before_start"] == count
         and type(projection["maximum_native_workers_total"]) is int and projection["maximum_native_workers_total"] == 4
         and number(projection["observed_at"]) and projection["observed_at"] == instant,
         "Worker counts or census timestamps contradict the lane")
    need(reference(lane["slot_reservation"]), "Hash-bound single-slot reservation required")
    evidence = projection["evidence_sha256"]
    need(isinstance(evidence, dict) and set(evidence) == EVIDENCE_FIELDS and all(sha_value(value) for value in evidence.values())
         and evidence["private_full_census"] == lane["private_full_census_sha256"]
         and evidence["global_slot_reservation"] == lane["slot_reservation"]["sha256"], "Closed current evidence graph required")
    reservation = json.loads(read_ref(lane["slot_reservation"]).read_text(encoding="utf8"), object_pairs_hook=unique_object)
    need(isinstance(reservation, dict) and set(reservation) == RESERVATION_FIELDS
         and reservation["schema"] == RESERVATION_SCHEMA and reservation["verified"] is True
         and all(reservation[key] == value for key, value in cell_binding.items())
         and isinstance(reservation["reservation_id"], str) and len(reservation["reservation_id"]) == 32
         and all(char in "0123456789abcdef" for char in reservation["reservation_id"]), "Exact exclusive reservation required")
    need(all(reservation[key] is True for key in ("exclusive_global_lock_held_at_census", "all_native_workers_known",
              "launcher_python_pairs_count_as_one", "one_cell_only", "one_submission_only"))
         and reservation["consumed"] is False and type(reservation["active_native_workers_before_start"]) is int
         and reservation["active_native_workers_before_start"] == count
         and type(reservation["maximum_native_workers_total"]) is int and reservation["maximum_native_workers_total"] == 4
         and number(reservation["observed_at"]) and reservation["observed_at"] == instant
         and reservation["private_full_census_sha256"] == evidence["private_full_census"],
         "Reservation is consumed, ambiguous or inconsistent with initial census")
    return lane
