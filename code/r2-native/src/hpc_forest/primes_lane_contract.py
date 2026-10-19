"""Pure lane-v2 validation of an owned projection, never a Windows observation."""
from __future__ import annotations

import json
import math
import re
import time

LANE_SCHEMA = "hpc-forest-primes-r2max-lane-freshness-v2"
PROJECTION_SCHEMA = "hpc-forest-primes-r2max-owned-lane-projection-v2"
PLAN_CONTRACT = {"version": 2, "lane_schema": LANE_SCHEMA, "projection_schema": PROJECTION_SCHEMA}
CELL_FIELDS = {"scope_id", "source_zip_sha256", "plan_sha256", "model", "effort", "session_id", "job_id", "remote_root"}
LANE_FIELDS = CELL_FIELDS | {"schema", "verified", "maximum_native_workers_total", "active_native_workers_before_start",
    "full_census_locally_verified", "source_only_preserved", "new_cache_registry_root", "native_calls_started",
    "observed_at", "private_full_census_sha256", "minimal_owned_observations", "source_only_state", "source_only_active_workers"}
PROJECTION_FIELDS = CELL_FIELDS | {"schema", "verified", "source_only_state", "source_only_preserved",
    "source_only_active_workers", "other_native_workers_count", "active_native_workers_before_start",
    "maximum_native_workers_total", "observed_at", "observation_origin", "windows_census_observed_by_arm",
    "full_census_exported", "foreign_configuration_or_credentials_exported", "evidence_sha256"}
EVIDENCE_FIELDS = {"scientific_reception", "reconciliation", "private_full_census", "source_only_absence",
    "prior_owned_census", "cold_absence_census", "owned_descendant_review", "observer_release", "local_projection_producer_review"}
ABSENCE_FIELDS = {"source_only_absence", "prior_owned_census", "cold_absence_census", "owned_descendant_review"}
SCIENCE_SHA = "6cd1f532e43bf4fae443bc58e38527847df6cb03511fa84a8d233199db1b41e7"
RECON_SHA = "0ed5c437d3737ec9a970a4183b3e80ce996e87a7f655e5fba9965a979682def8"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha_value(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate projection JSON field")
        result[key] = value
    return result


def validate_lane_v2(lane, cell, read_ref, *, initial=True, now=None):
    """Verify transported bytes/coherence; private local proofs remain local facts.

    read_ref is the existing closed, hash-checking artifact reader. The source
    does not inspect a Windows census, config, credentials or process tree.
    """
    need(isinstance(cell, dict) and set(cell) == CELL_FIELDS, "Exact lane cell identity required")
    need(isinstance(lane, dict) and set(lane) == LANE_FIELDS
         and lane["schema"] == LANE_SCHEMA and lane["verified"] is True
         and all(lane[k] == v for k, v in cell.items()), "Exact versioned lane-v2 fields/binding required")
    count = lane["active_native_workers_before_start"]
    need(type(lane["maximum_native_workers_total"]) is int and lane["maximum_native_workers_total"] == 4
         and type(count) is int and 0 <= count < 4
         and lane["full_census_locally_verified"] is True and lane["new_cache_registry_root"] is True
         and type(lane["native_calls_started"]) is int and lane["native_calls_started"] == 0,
         "Exact cap4/new-cache/zero-start lane required")
    instant = lane["observed_at"]
    now = time.time() if now is None else now
    need(number(now) and number(instant) and 0 <= now - instant and (not initial or now - instant <= 600),
         "Lane launch observation is invalid, future or stale")
    need(sha_value(lane["private_full_census_sha256"]), "Private local census SHA required")
    mode = lane["source_only_state"]
    need(mode in {"live", "received_absent"}, "Unknown source-only state")
    preserved, contribution = (True, 1) if mode == "live" else (False, 0)
    need(lane["source_only_preserved"] is preserved
         and type(lane["source_only_active_workers"]) is int and lane["source_only_active_workers"] == contribution,
         "Contradictory SO state/preservation/contribution")
    projection_path = read_ref(lane["minimal_owned_observations"])
    projection = json.loads(projection_path.read_text(encoding="utf8"), object_pairs_hook=unique_object)
    need(isinstance(projection, dict) and set(projection) == PROJECTION_FIELDS
         and projection["schema"] == PROJECTION_SCHEMA and projection["verified"] is True
         and all(projection[k] == v for k, v in cell.items()), "Exact owned projection-v2 fields/binding required")
    need(projection["observation_origin"] == "parent-private-Windows-census"
         and projection["windows_census_observed_by_arm"] is False and projection["full_census_exported"] is False
         and projection["foreign_configuration_or_credentials_exported"] is False,
         "Owned projection must not claim ARM Windows observation or export foreign private data")
    need(projection["source_only_state"] == mode and projection["source_only_preserved"] is preserved
         and type(projection["source_only_active_workers"]) is int and projection["source_only_active_workers"] == contribution
         and type(projection["other_native_workers_count"]) is int and 0 <= projection["other_native_workers_count"] < 4
         and type(projection["active_native_workers_before_start"]) is int
         and projection["active_native_workers_before_start"] == count == contribution + projection["other_native_workers_count"]
         and type(projection["maximum_native_workers_total"]) is int and projection["maximum_native_workers_total"] == 4
         and number(projection["observed_at"]) and projection["observed_at"] == instant,
         "Projection SO/count/time contradicts the launch lane")
    evidence = projection["evidence_sha256"]
    need(isinstance(evidence, dict) and set(evidence) == EVIDENCE_FIELDS
         and evidence["scientific_reception"] == SCIENCE_SHA and evidence["reconciliation"] == RECON_SHA
         and evidence["private_full_census"] == lane["private_full_census_sha256"]
         and all(sha_value(evidence[k]) for k in EVIDENCE_FIELDS - ABSENCE_FIELDS), "Closed local evidence SHA graph required")
    need(all(sha_value(evidence[k]) if mode == "received_absent" else evidence[k] is None for k in ABSENCE_FIELDS),
         "Absent SO needs all local absence/descendant digests; live SO cannot claim them")
    return lane
