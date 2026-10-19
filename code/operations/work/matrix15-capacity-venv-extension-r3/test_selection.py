"""Neutral, local-file evidence tests; none of these files is an admission."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("neutral_matrix15_selection", Path(__file__).with_name("selection.py"))
selection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selection)


def file_ref(tmp_path, name, value):
    path = (tmp_path / name).resolve()
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def row_for(state, key):
    return next(row for row in state["records"] if row["cell_key"] == key)


def cell_for(index=0):
    return list(cell for key, cell in selection.REGISTERED_CELLS.items() if key != selection.FIRST_CELL)[index]


def binding(cell):
    return {**cell, "scope_id": selection.SCOPE, "job_id": "123456",
            "remote_root": "/gpfs/scratch/nimarano/" + selection.SCOPE + "-" + cell["session_id"],
            "source_zip_sha256": selection.SOURCE_SHA, "plan_sha256": selection.PLAN_SHA,
            "preparation_manifest_sha256": selection.PREPARATION_SHA, "r1_contract_sha256": selection.FIRST_R1_SHA}


def reservation(cell, *, consumed=False):
    return {**binding(cell), "schema": selection.RESERVATION_SCHEMA, "verified": True,
            "reservation_id": "3" * 32, "exclusive_global_lock_held_at_census": True,
            "all_native_workers_known": True, "launcher_python_pairs_count_as_one": True,
            "observed_at": 1000.0, "active_native_workers_before_start": 0,
            "maximum_native_workers_total": 4, "one_cell_only": True, "one_submission_only": True,
            "consumed": consumed, "private_full_census_sha256": "4" * 64}


def first_start(cell, tmp_path=None):
    calls = [{"normal_delivered": True}]
    if tmp_path is not None:
        identity = {"model": cell["model"], "reasoning_effort": "max", "session_id": cell["session_id"]}
        request = file_ref(tmp_path, "NEUTRAL-request.json", {**identity, "nonce": "9" * 32,
            "kind": "source-proposal", "mission_id": "NEUTRAL-mission"})
        log = file_ref(tmp_path, "NEUTRAL-raw.log", b"not JSON\x00\n")
        response = file_ref(tmp_path, "NEUTRAL-response.json", {**identity, "nonce": "9" * 32,
            "request_sha256": request["sha256"], "infrastructure_error": False,
            "usage": {"token_accounting": "exact", "tokens": 1, "llm_calls": 1,
                      "tool_events": [], "codex_jsonl_sha256": log["sha256"]}})
        ready = file_ref(tmp_path, "NEUTRAL-ready.json", {"sha256": response["sha256"],
            "bytes": Path(response["path"]).stat().st_size})
        delivered = file_ref(tmp_path, "NEUTRAL-delivered.json", {**binding(cell),
            "request_sha256": request["sha256"], "response_sha256": response["sha256"]})
        metadata = file_ref(tmp_path, "NEUTRAL-cli-projection.json", {"receipt": "NEUTRAL"})
        calls = [{"request": request, "response": response, "ready": ready, "invocation": metadata,
            "delivered": delivered, "process": metadata, "error_and_usage_log": log,
            "mission_id": "NEUTRAL-mission", "mother_call": False, "mother_phase": None,
            "normal_delivered": True, "usage_exact": True, "exact_tokens": 1,
            "known_model_negative": False, "private_cli_review_required": True, "private_cli_argv_verified": False,
            "private_cli_records": {key: "a" * 64 for key in ("invocation_sha256", "process_sha256", "argv_sha256",
                "skill_override_sha256", "task_cli_policy_sha256")}}]
    return {**binding(cell), "schema": selection.FIRST_START_SCHEMA, "verified": True,
            "protocol_id": "5" * 64, "allocation": {"job_id": "123456"},
            "all_started_calls_reconciled": calls,
            "extension_to_other_cells_allowed": False}


def hold(cell):
    return {**binding(cell), "schema": selection.HOLD_SCHEMA, "nonce": "6" * 32,
            "response_sha256": "7" * 64, "delivered_sha256": "8" * 64,
            "new_generations_allowed": False, "byte_identical_retransmissions_only": True,
            "process_stop_or_retry": False, "model_algorithmic_negative_repaired": False}


def received_state(tmp_path, **gate_changes):
    state = selection.template_state()
    gate = {"schema": selection.GATE_SCHEMA, "verified": True, "evidence_origin": "received",
            "first_binding": binding(state["first_cell"]), "source_zip_sha256": selection.SOURCE_SHA,
            "plan_sha256": selection.PLAN_SHA, **gate_changes}
    state.update(mode="RECEIVED", verified=True,
                 first_release_ref=file_ref(tmp_path, "NEUTRAL-gate.json", gate))
    return state


def snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_template_is_exact_closed_sixty_and_never_an_admission():
    state = selection.template_state()
    assert state["mode"] == "PREPARE" and state["verified"] is False
    assert len(state["records"]) == 60
    assert {row["cell_key"] for row in state["records"]} == set(selection.REGISTERED_CELLS)
    assert len({row["session_id"] for row in state["records"]}) == 60
    pilot = row_for(state, selection.FIRST_CELL)
    assert pilot["status"] == "reserved_for_pilot"
    assert all(row["status"] == "not_started" for row in state["records"] if row != pilot)
    result = selection.select_cells(state, limit=60)
    assert result["verified"] is False and result["prerequisite_pending"] is True
    assert result["commands_to_execute"] == [] and len(result["candidates"]) == 59
    assert all(cell["cell_key"] != selection.FIRST_CELL and cell["effort"] == "max" for cell in result["candidates"])


def test_selection_is_read_only_and_returns_detached_values(tmp_path):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    state = received_state(tmp_path)
    original, before = copy.deepcopy(state), snapshot(tmp_path)
    checked = selection.validate_state(state)
    selected = selection.selection_for_cell(state, cell_for()["cell_key"], registry)
    assert selected == cell_for() and set(selected) == selection.CELL_FIELDS
    checked["records"][0]["model"] = "changed"
    selected["model"] = "changed"
    selection.select_cells(state, registry, limit=60)
    assert state == original and snapshot(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"), ("source_zip_sha256", "0" * 64), ("plan_sha256", "0" * 64),
    ("mode", "RUN"), ("verified", True), ("records", []), ("first_cell", {}),
])
def test_state_drift_and_incomplete_ledger_are_refused(field, value):
    state = selection.template_state()
    state[field] = value
    with pytest.raises(selection.SelectionError):
        selection.select_cells(state)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unknown", "session", "model", "effort", "subject"])
def test_closed_identity_has_no_unknown_or_reused_cells(mutation):
    state = selection.template_state()
    if mutation == "duplicate":
        state["records"][1] = copy.deepcopy(state["records"][0])
    elif mutation == "missing":
        state["records"].pop()
    else:
        field = {"unknown": "cell_key", "session": "session_id", "subject": "subject_id"}.get(mutation, mutation)
        state["records"][0][field] = "nonmax" if mutation == "effort" else "unknown"
    with pytest.raises(selection.SelectionError):
        selection.validate_state(state)


@pytest.mark.parametrize("status", ["started", "released", "complete", "held", "failed", "technical_hold"])
def test_status_without_actual_receipt_is_never_a_selection_hint(status):
    state = selection.template_state()
    row_for(state, cell_for()["cell_key"])["status"] = status
    with pytest.raises(selection.SelectionError, match="real hash-bound"):
        selection.select_cells(state)


@pytest.mark.parametrize("status", ["released", "complete", "failed"])
def test_first_start_never_fabricates_a_terminal_scientific_outcome(tmp_path, status):
    state, cell = selection.template_state(), cell_for()
    row_for(state, cell["cell_key"]).update(status=status,
        evidence_refs=[file_ref(tmp_path, "NEUTRAL-start.json", first_start(cell))])
    with pytest.raises(selection.SelectionError):
        selection.validate_state(state)


@pytest.mark.parametrize("kind,status", [("first_start", "started"), ("consumed", "started"),
    ("pending", "held"), ("hold", "technical_hold"), ("hold", "held"), ("hold", "failed")])
def test_real_file_native_status_receipts_exclude_cells(tmp_path, kind, status):
    state, cell = selection.template_state(), cell_for()
    value = (first_start(cell, tmp_path) if kind == "first_start" else hold(cell) if kind == "hold"
             else reservation(cell, consumed=kind == "consumed"))
    row_for(state, cell["cell_key"]).update(status=status,
        evidence_refs=[file_ref(tmp_path, "NEUTRAL-native-receipt.json", value)])
    selected = selection.select_cells(state, limit=60)
    assert cell not in selected["candidates"] and len(selected["candidates"]) == 58
    assert selected["verified"] is False


def test_pending_reservation_does_not_claim_started(tmp_path):
    state, cell = selection.template_state(), cell_for()
    row_for(state, cell["cell_key"]).update(status="started",
        evidence_refs=[file_ref(tmp_path, "NEUTRAL-reservation.json", reservation(cell))])
    with pytest.raises(selection.SelectionError):
        selection.validate_state(state)


@pytest.mark.parametrize("consumed", [False, True])
def test_registry_excludes_both_pending_and_consumed_sessions(tmp_path, consumed):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    state, cell = received_state(tmp_path), cell_for()
    file_ref(registry, "NEUTRAL.reservation.json", reservation(cell, consumed=consumed))
    selected = selection.select_cells(state, registry, limit=60)
    assert cell not in selected["candidates"] and len(selected["candidates"]) == 58
    with pytest.raises(selection.SelectionError, match="pending or consumed"):
        selection.selection_for_cell(state, cell["cell_key"], registry)


@pytest.mark.parametrize("change", ["unknown", "wrongsession", "wrongsource", "wrongplan", "nonmax", "unverified", "incomplete", "duplicate"])
def test_invalid_registry_never_silently_disappears(tmp_path, change):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    value = reservation(cell_for(), consumed=True)
    if change == "incomplete":
        value.pop("one_submission_only")
    elif change != "duplicate":
        field = {"unknown": "cell_key", "wrongsession": "session_id", "wrongsource": "source_zip_sha256",
                 "wrongplan": "plan_sha256", "nonmax": "effort", "unverified": "verified"}[change]
        value[field] = False if change == "unverified" else "unknown"
    file_ref(registry, "NEUTRAL-a.reservation.json", value)
    if change == "duplicate":
        file_ref(registry, "NEUTRAL-b.reservation.json", value)
    with pytest.raises(selection.SelectionError):
        selection.select_cells(selection.template_state(), registry)


def test_receipt_rehash_and_exact_cell_binding_are_required(tmp_path):
    state, cell = selection.template_state(), cell_for()
    ref = file_ref(tmp_path, "NEUTRAL-start.json", first_start(cell, tmp_path))
    row_for(state, cell["cell_key"]).update(status="started", evidence_refs=[ref])
    selection.validate_state(state, lambda reference: Path(reference["path"]))
    Path(ref["path"]).write_text("{}")
    with pytest.raises(selection.SelectionError, match="SHA drift"):
        selection.validate_state(state)
    ref = file_ref(tmp_path, "NEUTRAL-wrongcell.json", first_start(cell_for(1)))
    row_for(state, cell["cell_key"])["evidence_refs"] = [ref]
    with pytest.raises(selection.SelectionError, match="another cell"):
        selection.validate_state(state)


def test_nested_refs_include_raw_logs_and_are_rehashed(tmp_path):
    state, cell = selection.template_state(), cell_for()
    value = first_start(cell, tmp_path)
    log = value["all_started_calls_reconciled"][0]["error_and_usage_log"]
    row_for(state, cell["cell_key"]).update(status="started",
        evidence_refs=[file_ref(tmp_path, "NEUTRAL-start.json", value)])
    selection.validate_state(state)
    Path(log["path"]).write_bytes(b"changed")
    with pytest.raises(selection.SelectionError, match="SHA drift"):
        selection.validate_state(state)


def test_a_generic_true_call_list_is_not_a_native_started_receipt(tmp_path):
    state, cell = selection.template_state(), cell_for()
    row_for(state, cell["cell_key"]).update(status="started",
        evidence_refs=[file_ref(tmp_path, "NEUTRAL-generic-true.json", first_start(cell))])
    with pytest.raises(selection.SelectionError, match="exact evidence fields"):
        selection.validate_state(state)


def test_first_start_is_never_a_first_release_gate(tmp_path):
    state = received_state(tmp_path)
    state["first_release_ref"] = file_ref(tmp_path, "NEUTRAL-first-start.json",
                                        first_start(selection.REGISTERED_CELLS[selection.FIRST_CELL]))
    with pytest.raises(selection.SelectionError, match="first-batch extension gate"):
        selection.validate_state(state)


@pytest.mark.parametrize("field,value", [("verified", False), ("evidence_origin", "prepared"),
    ("source_zip_sha256", "0" * 64), ("plan_sha256", "0" * 64), ("first_binding", binding(cell_for())),
    ("synthetic", True)])
def test_release_gate_is_pinned_and_received(tmp_path, field, value):
    state = received_state(tmp_path, **{field: value})
    with pytest.raises(selection.SelectionError):
        selection.validate_state(state)


def test_release_gate_proofs_cannot_drift(tmp_path):
    log = file_ref(tmp_path, "NEUTRAL-received-proof.json", {"receipt": "NEUTRAL"})
    state = received_state(tmp_path, evidence_refs=[log])
    selection.validate_state(state)
    Path(log["path"]).write_bytes(b"{}")
    with pytest.raises(selection.SelectionError, match="SHA drift"):
        selection.validate_state(state)


@pytest.mark.parametrize("field,value", [("job_id", "0"), ("job_id", "00123456"), ("job_id", 123456),
    ("remote_root", "/gpfs/scratch/nimarano/another-cell"), ("preparation_manifest_sha256", "0" * 64),
    ("r1_contract_sha256", "0" * 64), ("session_id", "0" * 32)])
def test_first_release_has_exact_twelve_field_native_pilot_binding(tmp_path, field, value):
    first = binding(selection.REGISTERED_CELLS[selection.FIRST_CELL])
    first[field] = value
    with pytest.raises(selection.SelectionError):
        selection.validate_state(received_state(tmp_path, first_binding=first))


def test_explicit_received_transport_resolver_is_rehashed_for_selection_apis(tmp_path):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    local = file_ref(tmp_path, "NEUTRAL-transported.json", {"receipt": "NEUTRAL"})
    remote = {"path": "/gpfs/scratch/nimarano/received-native-proof.json", "sha256": local["sha256"]}
    state = received_state(tmp_path, received_proof=remote)
    gate_local = copy.deepcopy(state["first_release_ref"])
    gate_remote = {"path": "/gpfs/scratch/nimarano/received-native-gate.json", "sha256": gate_local["sha256"]}
    state["first_release_ref"] = gate_remote
    transported = {(remote["path"], remote["sha256"]): Path(local["path"]),
                   (gate_remote["path"], gate_remote["sha256"]): Path(gate_local["path"])}

    def resolve(ref):
        return transported[(ref["path"], ref["sha256"])]

    with pytest.raises(selection.SelectionError):
        selection.select_cells(state, registry)
    assert selection.select_cells(state, registry, read_ref=resolve)["prerequisite_pending"] is False
    assert selection.selection_for_cell(state, cell_for()["cell_key"], registry, read_ref=resolve) == cell_for()
    Path(local["path"]).write_text("{}")
    with pytest.raises(selection.SelectionError, match="SHA drift"):
        selection.selection_for_cell(state, cell_for()["cell_key"], registry, read_ref=resolve)


def test_pilot_preparation_and_absent_registry_cannot_operationally_select(tmp_path):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    with pytest.raises(selection.SelectionError):
        selection.selection_for_cell(selection.template_state(), cell_for()["cell_key"], registry)
    state = received_state(tmp_path)
    with pytest.raises(selection.SelectionError, match="non-pilot"):
        selection.selection_for_cell(state, selection.FIRST_CELL, registry)
    with pytest.raises(selection.SelectionError, match="current native reservation registry"):
        selection.selection_for_cell(state, cell_for()["cell_key"], None)
    state["mode"], state["verified"] = "PREPARE", False
    assert selection.select_cells(state)["verified"] is False
    with pytest.raises(selection.SelectionError, match="received verified"):
        selection.selection_for_cell(state, cell_for()["cell_key"], registry)


def test_received_mode_cannot_omit_release(tmp_path):
    state = selection.template_state()
    state.update(mode="RECEIVED", verified=True)
    with pytest.raises(selection.SelectionError):
        selection.validate_state(state)


def test_duplicate_json_fields_in_real_registry_are_refused(tmp_path):
    registry = tmp_path / "NEUTRAL-registry"
    registry.mkdir()
    file_ref(registry, "NEUTRAL.reservation.json", b'{"schema":"one","schema":"two"}')
    with pytest.raises(selection.SelectionError, match="Duplicate JSON"):
        selection.select_cells(selection.template_state(), registry)


def test_contract_drift_is_checked_before_ast_is_used(tmp_path, monkeypatch):
    path = tmp_path / "NEUTRAL-contract.py"
    path.write_text("raise RuntimeError('must never execute')\nREGISTERED_CELLS = {}")
    monkeypatch.setattr(selection, "CONTRACT_PATH", path.resolve())
    with pytest.raises(selection.SelectionError, match="source127 cell contract SHA drift"):
        selection.template_state()


@pytest.mark.parametrize("limit", [0, 61, True, 1.0, "1", None])
def test_limit_is_typed_and_bounded(limit):
    with pytest.raises(selection.SelectionError):
        selection.select_cells(selection.template_state(), limit=limit)
