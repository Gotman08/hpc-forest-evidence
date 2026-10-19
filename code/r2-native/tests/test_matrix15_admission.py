"""Neutral metadata tests: no CLI, model, compiler, transport, job or old candidate."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import codex_process, codex_worker
from hpc_forest import matrix15_contract as contract
from hpc_forest import matrix15_lane_contract as lane_contract
from hpc_forest import matrix15_worker as worker
from hpc_forest import native_matrix15 as native
from hpc_forest.core import InfrastructureError, file_digest


def neutral_ref(name, sha="a" * 64):
    return {"path": "/NEUTRAL-NOT-AN-ADMISSION/" + name, "sha256": sha}


def proposed_plan():
    subjects = {key: {"subject_id": key, "official_preparation_path": "/NEUTRAL/prepared/" + key,
        "preparation_sha256": "1" * 64, "r1_contract_ref": neutral_ref(key + "-r1.json"),
        "prepared_contract_ref": neutral_ref(key + "-prepared.json"), "statement_ref": neutral_ref(key + "-statement.txt"),
        "qualification_ref": None, "reception_ref": None,
        "config": {"neutral": "metadata only", "codex": {"model": "{cell.model}", "reasoning_effort": "max"}}}
        for key in contract.SUBJECTS}
    return {"schema": "hpc-forest-matrix15-native-max-plan-v2", "scope_id": contract.SCOPE,
        "protocol": neutral_ref("protocol.json", contract.PROTOCOL_SHA256), "models": list(contract.MODELS),
        "efforts": ["max"], "subjects": list(contract.SUBJECTS), "cells": copy.deepcopy(list(contract.REGISTERED_CELLS.values())),
        "subject_bindings": subjects, "source_zip_sha256": "2" * 64,
        "runtime_manifest": neutral_ref("runtime.json"), "preparation_manifest": neutral_ref("preparation.json"),
        "artifact_aliases": neutral_ref("aliases.json"),
        "r1_contracts": neutral_ref("r1-contracts.json", contract.R1_CONTRACTS_SHA256),
        "harness": neutral_ref("harness-mixed.json", contract.HARNESS_SHA256), "primes_release": None,
        "maximum_native_workers_total": 4, "maximum_cells_per_authorization": 1,
        "budgets_per_cell": copy.deepcopy(contract.BUDGETS), "target": copy.deepcopy(contract.TARGET),
        "automatic_extension": False, "scientific_contract": "exact-R1-harness-mixed-calibration-only-excluded",
        "exclusive_deadline_utc": "2026-10-31T23:00:00Z", "reception_audit_reserve_seconds": 10800}


def binding():
    cell = next(iter(contract.REGISTERED_CELLS.values()))
    return {**cell, "scope_id": contract.SCOPE, "job_id": "123456", "remote_root": "/NEUTRAL/" + cell["session_id"],
            "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
            "preparation_manifest_sha256": "3" * 64, "r1_contract_sha256": "4" * 64}


def json_file(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf8")
    return {"path": str(path.resolve()), "sha256": file_digest(path)}


def test_proposed_plan_has_exact_sixty_distinct_cells_but_no_scientific_admission():
    plan = contract.validate_plan(proposed_plan())
    assert len(plan["cells"]) == len({cell["session_id"] for cell in plan["cells"]}) == 60
    assert plan["primes_release"] is None
    assert all(item["qualification_ref"] is None and item["reception_ref"] is None for item in plan["subject_bindings"].values())


@pytest.mark.parametrize("field", ["qualification_ref", "reception_ref"])
def test_final_receipts_cannot_be_reinjected_into_upstream_plan(field):
    plan = proposed_plan()
    plan["subject_bindings"][contract.SUBJECTS[0]][field] = neutral_ref("NEUTRAL-final.json")
    with pytest.raises(InfrastructureError, match="downstream authorization"):
        contract.validate_plan(plan)


def test_legacy_circular_plan_requires_an_explicit_revision():
    plan = proposed_plan()
    plan["schema"] = "hpc-forest-matrix15-native-max-plan-v1"
    with pytest.raises(InfrastructureError, match="scope/schema"):
        contract.validate_plan(plan)


@pytest.mark.parametrize("cell", list(contract.REGISTERED_CELLS.values()), ids=list(contract.REGISTERED_CELLS))
def test_each_registered_max_identity_is_resolved_without_open_model_session_selection(cell):
    selected = contract.resolve_subject(proposed_plan(), cell["cell_key"])
    assert {key: selected[key] for key in contract.CELL_FIELDS} == cell
    assert native.selected_identity({**cell, "scope_id": contract.SCOPE}) == (cell["model"], cell["session_id"])
    assert selected["config"]["codex"]["model"] == "{cell.model}"


@pytest.mark.parametrize("field,value", [("effort", "high"), ("model", "gpt-unknown"), ("subject_id", "primes"),
    ("session_id", "f" * 32), ("cell_key", "foreign")])
def test_registered_cell_cannot_be_rebound(field, value):
    cell = copy.deepcopy(next(iter(contract.REGISTERED_CELLS.values())))
    cell[field] = value
    with pytest.raises(InfrastructureError):
        contract.validate_cell(cell)


@pytest.mark.parametrize("field,value", [("maximum_native_workers_total", 5), ("maximum_native_workers_total", True),
    ("maximum_cells_per_authorization", 2), ("automatic_extension", True), ("efforts", ["high"]),
    ("models", list(reversed(contract.MODELS))), ("scope_id", "hpc-forest-primes-native-max-r2h"),
    ("primes_release", {"verified": True}), ("exclusive_deadline_utc", "2027-01-01T00:00:00Z")])
def test_plan_scope_and_admission_constraints_are_closed(field, value):
    plan = proposed_plan()
    plan[field] = value
    with pytest.raises(InfrastructureError):
        contract.validate_plan(plan)


def test_plan_rejects_duplicate_missing_subject_session_or_unknown_field():
    for change in (lambda plan: plan["cells"].__setitem__(1, copy.deepcopy(plan["cells"][0])),
                   lambda plan: plan["subject_bindings"].pop(contract.SUBJECTS[0]),
                   lambda plan: plan.__setitem__("future_admitted", True),
                   lambda plan: plan["subject_bindings"][contract.SUBJECTS[0]].pop("statement_ref")):
        plan = proposed_plan()
        change(plan)
        with pytest.raises(InfrastructureError):
            contract.validate_plan(plan)


def test_pair_contract_excludes_only_reference_seconds_without_mutating_inputs():
    reference = {"benchmark": {"reference_seconds": 0.1, "repetitions": 3}, "oracle": {"sha256": "a"}, "flags": ["-O3"]}
    local = copy.deepcopy(reference)
    local["benchmark"]["reference_seconds"] = 0.9
    contract.assert_r1_pair_contract(reference, local)
    assert reference["benchmark"]["reference_seconds"] == 0.1
    for field, value in (("flags", ["-O2"]), ("oracle", {"sha256": "b"}),
                         ("benchmark", {"reference_seconds": 0.1, "repetitions": 5}), ("new_field", "different")):
        changed = copy.deepcopy(local)
        changed[field] = value
        with pytest.raises(InfrastructureError):
            contract.assert_r1_pair_contract(reference, changed)


def neutral_aliases():
    return {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": contract.SCOPE,
        "source_zip_sha256": "1" * 64, "preparation_manifest_sha256": "3" * 64,
        "entries": [{"kind": "file", "canonical_path": "C:/NEUTRAL/contract.json", "windows_path": "C:/NEUTRAL/contract.json",
        "arm_path": "/scratch/NEUTRAL/contract.json", "sha256": "a" * 64}]}


def test_platform_aliases_are_closed_and_never_rewrite_r1_or_change_hash():
    aliases = native.validate_aliases(neutral_aliases(), "1" * 64)
    original = {"path": "C:/NEUTRAL/contract.json", "sha256": "a" * 64}
    assert native.alias_reference(original, aliases, platform="arm") == {
        "path": "/scratch/NEUTRAL/contract.json", "sha256": "a" * 64}
    assert native.alias_reference({"path": "/scratch/NEUTRAL/contract.json", "sha256": "a" * 64},
                                  aliases, platform="windows") == original
    assert original == {"path": "C:/NEUTRAL/contract.json", "sha256": "a" * 64}
    unmapped = neutral_ref("not-mapped.json")
    assert native.alias_reference(unmapped, aliases, platform="arm") == unmapped
    with pytest.raises(InfrastructureError):
        native.alias_reference({**original, "sha256": "b" * 64}, aliases, platform="arm")


@pytest.mark.parametrize("change", [
    lambda value: value.__setitem__("scope_id", "foreign"),
    lambda value: value.__setitem__("source_zip_sha256", "b" * 64),
    lambda value: value["entries"].append(copy.deepcopy(value["entries"][0])),
    lambda value: value["entries"][0].__setitem__("arm_path", "/scratch/../foreign.json"),
    lambda value: value["entries"][0].__setitem__("windows_path", "relative.json"),
    lambda value: value["entries"][0].__setitem__("prefix_rewrite", True),
])
def test_alias_map_rejects_scope_hash_duplicates_relative_or_prefix_rewrites(change):
    aliases = neutral_aliases()
    change(aliases)
    with pytest.raises(InfrastructureError):
        native.validate_aliases(aliases, "1" * 64)


def make_lane(tmp_path, *, count=3, observed=1000.0):
    cell = binding()
    reservation = {**cell, "schema": lane_contract.RESERVATION_SCHEMA, "verified": True, "reservation_id": "a" * 32,
        "exclusive_global_lock_held_at_census": True, "all_native_workers_known": True,
        "launcher_python_pairs_count_as_one": True, "observed_at": observed, "active_native_workers_before_start": count,
        "maximum_native_workers_total": 4, "one_cell_only": True, "one_submission_only": True, "consumed": False,
        "private_full_census_sha256": "b" * 64}
    reservation_ref = json_file(tmp_path / "NEUTRAL-reservation.json", reservation)
    evidence = {name: "c" * 64 for name in lane_contract.EVIDENCE_FIELDS}
    evidence.update(private_full_census="b" * 64, global_slot_reservation=reservation_ref["sha256"])
    projection = {**cell, "schema": lane_contract.PROJECTION_SCHEMA, "verified": True,
        "other_native_workers_count": count, "active_native_workers_before_start": count,
        "maximum_native_workers_total": 4, "observed_at": observed,
        "observation_origin": "parent-private-Windows-census", "windows_census_observed_by_arm": False,
        "full_census_exported": False, "foreign_configuration_or_credentials_exported": False,
        "evidence_sha256": evidence, "all_native_workers_known": True,
        "launcher_python_pairs_count_as_one": True, "source_only_active_workers": 0}
    projection_ref = json_file(tmp_path / "NEUTRAL-projection.json", projection)
    lane = {**cell, "schema": lane_contract.LANE_SCHEMA, "verified": True, "maximum_native_workers_total": 4,
        "active_native_workers_before_start": count, "full_census_locally_verified": True,
        "new_cache_registry_root": True, "native_calls_started": 0, "observed_at": observed,
        "private_full_census_sha256": "b" * 64, "minimal_owned_observations": projection_ref,
        "slot_reservation": reservation_ref}
    return lane, cell, projection, reservation


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_typed_global_lane_allows_only_fourth_or_lower_worker_slot(tmp_path, count):
    lane, cell, _, _ = make_lane(tmp_path, count=count)
    assert lane_contract.validate_lane(lane, cell, native.artifact, now=1000) == lane


@pytest.mark.parametrize("count", [4, 5, -1, True, 3.0])
def test_unknown_or_full_lane_never_becomes_capacity(tmp_path, count):
    lane, cell, _, _ = make_lane(tmp_path, count=count)
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=1000)


def test_initial_lane_must_be_fresh_but_frozen_subsequent_calls_do_not_reapply_initial_clock(tmp_path):
    lane, cell, _, _ = make_lane(tmp_path)
    lane_contract.validate_lane(lane, cell, native.artifact, now=1600)
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=1600.01)
    lane_contract.validate_lane(lane, cell, native.artifact, now=8200, initial=False)
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=999, initial=False)


@pytest.mark.parametrize("field,value", [("all_native_workers_known", False), ("windows_census_observed_by_arm", True),
    ("source_only_active_workers", 1), ("other_native_workers_count", 2), ("foreign_configuration_or_credentials_exported", True),
    ("launcher_python_pairs_count_as_one", False)])
def test_projection_refuses_ambiguous_census_or_private_data_claim(tmp_path, field, value):
    lane, cell, projection, _ = make_lane(tmp_path)
    projection[field] = value
    lane["minimal_owned_observations"] = json_file(tmp_path / "NEUTRAL-projection.json", projection)
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=1000)


def test_changed_projection_or_reservation_bytes_are_rejected(tmp_path):
    lane, cell, _, _ = make_lane(tmp_path)
    Path(lane["slot_reservation"]["path"]).write_text("{}", encoding="utf8")
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=1000)


def test_lane_cannot_be_reused_for_another_subject_or_session(tmp_path):
    lane, cell, _, _ = make_lane(tmp_path)
    cell["subject_id"] = contract.SUBJECTS[1]
    with pytest.raises(InfrastructureError):
        lane_contract.validate_lane(lane, cell, native.artifact, now=1000)


def test_duplicate_json_fields_and_nonordinary_artifact_refused(tmp_path):
    path = tmp_path / "NEUTRAL-duplicate.json"
    path.write_text('{"verified": false, "verified": true}', encoding="utf8")
    with pytest.raises(InfrastructureError):
        native.read_json(path)
    with pytest.raises(InfrastructureError):
        native.artifact({"path": str(path), "sha256": file_digest(path), "verified": True})


def test_cache_is_exclusive_and_cannot_silently_adopt_nonempty_or_other_binding(tmp_path, monkeypatch):
    cell = binding()
    monkeypatch.setattr(native, "cell_binding", lambda auth: cell)
    unknown = tmp_path / "NEUTRAL-unknown-cache"
    unknown.mkdir()
    (unknown / "unknown.txt").write_text("NEUTRAL metadata", encoding="utf8")
    with pytest.raises(InfrastructureError):
        native.bind_worker_cache(unknown, {})
    fresh = tmp_path / "NEUTRAL-fresh-cache"
    assert native.bind_worker_cache(fresh, {}) == cell
    assert native.bind_worker_cache(fresh, {}) == cell
    cell["session_id"] = "f" * 32
    with pytest.raises(InfrastructureError):
        native.bind_worker_cache(fresh, {})


def test_started_claim_remains_unreplayable_if_request_binding_changes(tmp_path, monkeypatch):
    cell = binding()
    monkeypatch.setattr(native, "cell_binding", lambda auth: cell)
    cache = tmp_path / "NEUTRAL-cache"
    native.bind_worker_cache(cache, {})
    episode = cache / ("a" * 32)
    episode.mkdir()
    request = episode / "downloaded-request.json"
    json_file(request, {"model": cell["model"], "session_id": cell["session_id"], "reasoning_effort": "max"})
    json_file(episode / "generation-claimed.json", {"request_sha256": file_digest(request)})
    native.bind_worker_cache(cache, {})
    json_file(request, {"model": cell["model"], "session_id": "f" * 32, "reasoning_effort": "max"})
    with pytest.raises(InfrastructureError):
        native.bind_worker_cache(cache, {})


@pytest.mark.parametrize("response", [
    {"infrastructure_error": True, "usage": {"token_accounting": "exact"}},
    {"infrastructure_error": False, "usage": {"token_accounting": "upper_bound"}},
    {"infrastructure_error": False, "usage": {"token_accounting": "exact", "usage_parse_ambiguity": True}},
])
def test_delivered_technical_or_unknown_usage_latches_hold_and_only_identical_retransmission(tmp_path, response):
    nonce = "a" * 32
    local = tmp_path / nonce
    local.mkdir()
    ref = json_file(local / "response.json", response)
    json_file(local / "delivered.json", {**binding(), "response_sha256": ref["sha256"]})
    json_file(local / "response-ready.json", {"sha256": ref["sha256"], "bytes": (local / "response.json").stat().st_size})
    worker.preserve_delivered_technical_hold(tmp_path, local)
    assert native.read_json(tmp_path / "cli-technical-hold.json")["new_generations_allowed"] is False
    worker.check_technical_hold(tmp_path, nonce + ".request.json")
    with pytest.raises(InfrastructureError):
        worker.check_technical_hold(tmp_path, "b" * 32 + ".request.json")
    (local / "response.json").write_text("{}", encoding="utf8")
    with pytest.raises(InfrastructureError):
        worker.check_technical_hold(tmp_path, nonce + ".request.json")


def test_known_algorithmic_negative_does_not_create_technical_hold(tmp_path):
    local = tmp_path / ("a" * 32)
    local.mkdir()
    json_file(local / "response.json", {"infrastructure_error": False, "error": "NEUTRAL algorithmic negative",
                                        "usage": {"token_accounting": "exact"}})
    worker.preserve_delivered_technical_hold(tmp_path, local)
    assert not (tmp_path / "cli-technical-hold.json").exists()


def test_missing_or_historical_primes_proof_cannot_admit_future_matrix(tmp_path):
    for value in ({}, {"schema": "hpc-forest-primes-r2max-luna-closure-admission-v1", "verified": True},
                  {"schema": "hpc-forest-r2h-four-cell-scientific-release-v1", "scope_id": "hpc-forest-primes-native-max-r2h",
                   "verified": True, "cells": [], "evidence_refs": []}):
        path = tmp_path / "NEUTRAL-not-a-release.json"
        json_file(path, value)
        with pytest.raises(InfrastructureError):
            native.verify_primes_release(path)


def test_exclusive_deadline_preserves_reception_and_allocation_reserve():
    native.deadline_guard(native.DEADLINE - 21601)
    for now in (native.DEADLINE - 21600, float("nan"), True):
        with pytest.raises(InfrastructureError):
            native.deadline_guard(now)


@pytest.fixture
def neutral_parsers(tmp_path, monkeypatch):
    calls = {}
    executable = tmp_path / "NEUTRAL-never-executed.bin"
    executable.write_bytes(b"NEUTRAL parser identity; no executable content")
    cli_path = tmp_path / "NEUTRAL-cli.json"
    json_file(cli_path, {"executable_path": str(executable), "executable_sha256": file_digest(executable),
                         "task_cli_policy_sha256": "b" * 64})
    for name in ("Worker", "run_codex", "validate_remote_channel"):
        monkeypatch.setattr(codex_worker, name, getattr(codex_worker, name))
    monkeypatch.setattr(codex_process, "CLI_POLICY", None)
    monkeypatch.setattr(codex_process, "load_task_cli_policy", lambda *args: {"skill_candidate_directories": []})
    monkeypatch.setattr(worker, "verify_cli_files", lambda cli: None)
    monkeypatch.setattr(worker, "artifact", lambda ref: Path(ref["path"]))
    monkeypatch.setattr(worker, "bind_worker_cache", lambda *args: None)
    monkeypatch.setattr(worker, "cell_binding", lambda auth: calls["binding"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Neutral parser test must not run CLI/transport/inference")
    monkeypatch.setattr(codex_worker.RomeoFiles, "__init__", forbidden)
    monkeypatch.setattr(codex_worker.subprocess, "run", forbidden)
    monkeypatch.setattr(codex_worker, "main_async", lambda args: SimpleNamespace(args=args))
    def inert_async_run(token):
        calls["parsed"] = token.args
        return 37
    monkeypatch.setattr(codex_worker.asyncio, "run", inert_async_run)
    def arguments(model):
        selected = next(cell for cell in contract.REGISTERED_CELLS.values() if cell["model"] == model)
        auth = {**selected, "scope_id": contract.SCOPE, "job_id": "123456", "remote_root": "/NEUTRAL/owned",
                "artifacts": {"cli_identity": {"path": str(cli_path)}, "source_zip": {"sha256": "1" * 64},
                              "plan": {"sha256": "2" * 64}}}
        calls["binding"] = {**binding(), **selected}
        monkeypatch.setattr(worker, "install_identity", lambda *args, **kwargs: auth)
        return ["--dependency-receipt", str(tmp_path / "NEUTRAL-no-admission.json"), "--session-id", selected["session_id"],
            "--required-jobs", contract.SCOPE, "--executable", str(executable), "--channel", "/NEUTRAL/owned/results-123456/mailbox",
            "--output", str(tmp_path / "NEUTRAL-cache"), "--codex-config", str(tmp_path / "NEUTRAL-not-read.toml"),
            "--cli-policy", str(tmp_path / "NEUTRAL-not-read-policy.json"), "--cli-policy-sha256", "b" * 64,
            "--once", "--max-seconds", "1800", "--poll-seconds", "0.75"]
    return calls, arguments


@pytest.mark.parametrize("model", contract.MODELS)
def test_actual_adapter_and_inherited_parser_retain_shared_arguments_without_cli(neutral_parsers, model):
    calls, arguments = neutral_parsers
    before = sys.argv
    assert worker.main(arguments(model)) == 37
    assert sys.argv is before
    parsed = calls["parsed"]
    assert parsed.max_seconds == 1800 and parsed.once is True and parsed.transport_smoke is False
    assert parsed.required_jobs == [contract.SCOPE] and parsed.poll_seconds == 0.75
    assert not hasattr(parsed, "cli_policy")


@pytest.mark.parametrize("unknown", ["--unknown", "--codex-confg"])
def test_inherited_parser_refuses_unknown_options(neutral_parsers, unknown):
    calls, arguments = neutral_parsers
    before = sys.argv
    with pytest.raises(SystemExit) as caught:
        worker.main([*arguments(contract.MODELS[0]), unknown])
    assert caught.value.code == 2 and sys.argv is before and "parsed" not in calls
