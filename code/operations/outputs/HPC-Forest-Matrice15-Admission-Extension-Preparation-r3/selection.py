"""Read-only selection from the closed matrix; this module never admits execution.

Only data is read from the pinned source contract, using ``ast.literal_eval``.
No engine module, process census, model, job, launcher or network client is loaded.
The preparation result remains explicitly unverified even after a release is read.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
from pathlib import Path

SOURCE_SHA = "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
PLAN_SHA = "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f"
PREPARATION_SHA = "d60b93312c34319386cc7057fd77248df38282ee717ee63ca80ad911cf5e7313"
FIRST_R1_SHA = "c2fa077535e04b8d3f65ca4e4705ba178b55de6513aa4d1f071374bf9a776a16"
CONTRACT_SHA = "aef3c33b4123330a411b426b1ede766c33f95e784d94344df56c66f7e698928c"
CONTRACT_PATH = (Path(__file__).resolve().parents[2]
                 / "work/matrix15-admission-no-cycle-r2/project/src/hpc_forest/matrix15_contract.py")
SCOPE = "hpc-forest-matrix15-native-max-r2"
FIRST_CELL = "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23"
STATE_SCHEMA = "hpc-forest-matrix15-extension-state-v1"
SELECTION_SCHEMA = "hpc-forest-matrix15-extension-selection-v1"
GATE_SCHEMA = "hpc-forest-matrix15-extension-first-batch-gate-v1"
FIRST_START_SCHEMA = "hpc-forest-matrix15-first-start-v1"
HOLD_SCHEMA = "hpc-forest-matrix15-delivered-technical-hold-v1"
RESERVATION_SCHEMA = "hpc-forest-matrix15-single-slot-reservation-v1"
CELL_FIELDS = {"cell_key", "subject_id", "model", "effort", "session_id"}
BINDING_FIELDS = CELL_FIELDS | {"scope_id", "job_id", "remote_root", "source_zip_sha256",
                               "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
RESERVATION_FIELDS = BINDING_FIELDS | {"schema", "verified", "reservation_id",
    "exclusive_global_lock_held_at_census", "all_native_workers_known", "launcher_python_pairs_count_as_one",
    "observed_at", "active_native_workers_before_start", "maximum_native_workers_total", "one_cell_only",
    "one_submission_only", "consumed", "private_full_census_sha256"}
STATE_FIELDS = {"schema", "mode", "verified", "source_zip_sha256", "plan_sha256", "first_cell",
                "first_release_ref", "records"}
STATUSES = {"not_started", "reserved_for_pilot", "started", "released", "complete", "held", "failed",
            "technical_hold"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
HEX32 = re.compile(r"[a-f0-9]{32}\Z")


class SelectionError(ValueError):
    """A malformed or ambiguous ledger cannot select a native session."""


def need(condition, message):
    if not condition:
        raise SelectionError(message)


def _sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _physical(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "Absolute physical evidence path required")
    for part in (path, *path.parents):
        need(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)(),
             "Symlink/junction evidence paths are refused")
        if part.exists():
            need(not getattr(part.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400,
                 "Reparse-point evidence paths are refused")
    need(path.is_dir() if directory else path.is_file(), "Required evidence path is absent")
    return path


def _unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "Duplicate JSON field")
        value[key] = item
    return value


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                          parse_constant=lambda _: need(False, "Nonfinite JSON value"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SelectionError("Invalid evidence JSON") from exc


def _registry():
    """Read the exact data literal, without executing the source contract."""
    raw = _physical(CONTRACT_PATH).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == CONTRACT_SHA, "Pinned source127 cell contract SHA drift")
    tree = ast.parse(raw.decode("utf8"))
    assignments = [node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "REGISTERED_CELLS"
                           for target in node.targets)]
    need(len(assignments) == 1, "Exactly one closed source registry required")
    cells = ast.literal_eval(assignments[0])
    need(isinstance(cells, dict) and len(cells) == 60 and FIRST_CELL in cells,
         "Exactly sixty registered source cells required")
    need(all(isinstance(cell, dict) and set(cell) == CELL_FIELDS and key == cell["cell_key"]
             and cell["effort"] == "max" and HEX32.fullmatch(cell["session_id"])
             for key, cell in cells.items()) and len({cell["session_id"] for cell in cells.values()}) == 60,
         "Closed source registry has invalid/duplicate sessions")
    return cells


REGISTERED_CELLS = _registry()


def _reference(ref):
    return (isinstance(ref, dict) and set(ref) == {"path", "sha256"}
            and isinstance(ref["path"], str) and bool(ref["path"]) and _sha(ref["sha256"]))


def _ref_bytes(ref, read_ref=None):
    need(_reference(ref), "Exact hash-bound path/SHA reference required")
    path = _physical(ref["path"] if read_ref is None else read_ref(copy.deepcopy(ref)))
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == ref["sha256"], "Referenced evidence SHA drift")
    return raw


def _read_ref(ref, read_ref=None):
    return _json(_ref_bytes(ref, read_ref))


def _rehash_nested(value, read_ref):
    """Resolve each transported reference once; no receipt is trusted from its name."""
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            _ref_bytes(value, read_ref)
        else:
            for item in value.values():
                _rehash_nested(item, read_ref)
    elif isinstance(value, list):
        for item in value:
            _rehash_nested(item, read_ref)


def _not_fixture(value):
    need(not any(value.get(key) is True for key in ("prepared", "synthetic", "fixture", "test_only", "neutral")),
         "Prepared/synthetic receipts cannot establish a native ledger state")


def _binding(value, cell):
    need(isinstance(value, dict) and BINDING_FIELDS <= set(value)
         and all(value[key] == expected for key, expected in cell.items())
         and value["scope_id"] == SCOPE and value["source_zip_sha256"] == SOURCE_SHA
         and value["plan_sha256"] == PLAN_SHA, "Native receipt belongs to another cell/source/plan")
    need(isinstance(value["job_id"], str) and re.fullmatch(r"[1-9][0-9]*", value["job_id"])
         and value["remote_root"] == "/gpfs/scratch/nimarano/" + SCOPE + "-" + cell["session_id"]
         and value["preparation_manifest_sha256"] == PREPARATION_SHA and _sha(value["r1_contract_sha256"]),
         "Incomplete native receipt binding")
    _not_fixture(value)


def _reservation(value, cells):
    need(isinstance(value, dict) and set(value) == RESERVATION_FIELDS
         and value["schema"] == RESERVATION_SCHEMA and value["verified"] is True,
         "Exact verified current native reservation required")
    need(value.get("cell_key") in cells, "Unknown reservation cell")
    _binding(value, cells[value["cell_key"]])
    need(isinstance(value["reservation_id"], str) and HEX32.fullmatch(value["reservation_id"])
         and type(value["consumed"]) is bool and _sha(value["private_full_census_sha256"])
         and type(value["observed_at"]) in (int, float) and math.isfinite(value["observed_at"])
         and type(value["active_native_workers_before_start"]) is int
         and 0 <= value["active_native_workers_before_start"] < 4
         and type(value["maximum_native_workers_total"]) is int and value["maximum_native_workers_total"] == 4
         and all(value[key] is True for key in ("exclusive_global_lock_held_at_census", "all_native_workers_known",
                    "launcher_python_pairs_count_as_one", "one_cell_only", "one_submission_only")),
         "Invalid or incomplete native reservation ledger")
    return value


def _started_call(value, cell, read_ref):
    """A native observer's call must retain its real transfer evidence graph."""
    fields = {"request", "response", "ready", "invocation", "delivered", "process", "error_and_usage_log",
              "mission_id", "mother_call", "mother_phase", "normal_delivered", "usage_exact", "exact_tokens",
              "known_model_negative", "private_cli_review_required", "private_cli_argv_verified", "private_cli_records"}
    need(isinstance(value, dict) and set(value) == fields and value["normal_delivered"] is True
         and value["usage_exact"] is True and type(value["exact_tokens"]) is int and value["exact_tokens"] >= 0
         and isinstance(value["mission_id"], str) and bool(value["mission_id"])
         and type(value["mother_call"]) is bool and type(value["known_model_negative"]) is bool
         and value["private_cli_review_required"] is True and value["private_cli_argv_verified"] is False,
         "Actual native call reconciliation with exact evidence fields required")
    for key in ("request", "response", "ready", "invocation", "delivered", "process", "error_and_usage_log"):
        _ref_bytes(value[key], read_ref)
    private = value["private_cli_records"]
    need(isinstance(private, dict) and set(private) == {"invocation_sha256", "process_sha256", "argv_sha256",
                "skill_override_sha256", "task_cli_policy_sha256"} and all(_sha(item) for item in private.values()),
         "Native call must retain the exact private CLI digest projection")
    request, response, ready, delivered = [_read_ref(value[key], read_ref)
                                            for key in ("request", "response", "ready", "delivered")]
    _binding(delivered, cell)
    identity = {"model": cell["model"], "reasoning_effort": "max", "session_id": cell["session_id"]}
    need(isinstance(request, dict) and isinstance(response, dict) and isinstance(ready, dict)
         and all(request.get(key) == item and response.get(key) == item for key, item in identity.items())
         and isinstance(request.get("nonce"), str) and HEX32.fullmatch(request["nonce"])
         and response.get("nonce") == request["nonce"] and request.get("kind") == "source-proposal"
         and request.get("mission_id") == value["mission_id"]
         and response.get("infrastructure_error") is False
         and response.get("request_sha256") == value["request"]["sha256"]
         and delivered.get("request_sha256") == value["request"]["sha256"]
         and delivered.get("response_sha256") == value["response"]["sha256"]
         and ready.get("sha256") == value["response"]["sha256"]
         and type(ready.get("bytes")) is int and ready["bytes"] == len(_ref_bytes(value["response"], read_ref)),
         "Native request/response/ready/delivery graph differs from the exact cell")
    usage = response.get("usage", {})
    need(isinstance(usage, dict) and usage.get("token_accounting") == "exact"
         and type(usage.get("tokens")) is int and usage["tokens"] == value["exact_tokens"]
         and type(usage.get("llm_calls")) is int and usage["llm_calls"] == 1
         and usage.get("tool_events") == [] and usage.get("codex_jsonl_sha256") == value["error_and_usage_log"]["sha256"],
         "Native started call has unknown or mismatched usage")


def _evidence(ref, cell, status, cells, read_ref):
    value = _read_ref(ref, read_ref)
    _binding(value, cell)
    schema = value.get("schema")
    if schema == RESERVATION_SCHEMA:
        _reservation(value, cells)
        need(status in {"started", "held"} and (status != "started" or value["consumed"] is True),
             "Reservation does not prove the declared native state")
    elif schema == FIRST_START_SCHEMA:
        need(status == "started" and type(value.get("verified")) is bool
             and _sha(value.get("protocol_id")) and isinstance(value.get("allocation"), dict)
             and value["allocation"].get("job_id") == value["job_id"]
             and isinstance(value.get("all_started_calls_reconciled"), list)
             and bool(value["all_started_calls_reconciled"]), "Actual native first-start calls required")
        for call in value["all_started_calls_reconciled"]:
            _started_call(call, cell, read_ref)
    elif schema == HOLD_SCHEMA:
        need(status in {"held", "technical_hold", "failed"}
             and HEX32.fullmatch(str(value.get("nonce", ""))) and _sha(value.get("response_sha256"))
             and _sha(value.get("delivered_sha256")) and value.get("new_generations_allowed") is False
             and value.get("byte_identical_retransmissions_only") is True
             and value.get("process_stop_or_retry") is False
             and value.get("model_algorithmic_negative_repaired") is False,
             "Actual delivered technical hold required")
    else:
        raise SelectionError("No current native receipt schema proves this ledger state")
    _rehash_nested(value, read_ref)


def _release(ref, cells, read_ref):
    if ref is None:
        return False
    value = _read_ref(ref, read_ref)
    need(isinstance(value, dict) and value.get("schema") == GATE_SCHEMA and value.get("verified") is True
         and value.get("evidence_origin") == "received"
         and value.get("source_zip_sha256") == SOURCE_SHA and value.get("plan_sha256") == PLAN_SHA,
         "A received, verified first-batch extension gate for the exact pilot/source/plan is required")
    binding = value.get("first_binding")
    need(isinstance(binding, dict) and set(binding) == BINDING_FIELDS,
         "Exact twelve-field first pilot binding required")
    _binding(binding, cells[FIRST_CELL])
    need(binding["r1_contract_sha256"] == FIRST_R1_SHA, "First pilot R1 contract pin differs")
    _not_fixture(value)
    _rehash_nested(value, read_ref)
    return True


def template_state():
    """Return all sixty preparation records; the unique pilot is never selectable."""
    cells = _registry()
    return {"schema": STATE_SCHEMA, "mode": "PREPARE", "verified": False,
            "source_zip_sha256": SOURCE_SHA, "plan_sha256": PLAN_SHA, "first_cell": cells[FIRST_CELL],
            "first_release_ref": None, "records": [
                {**cell, "status": "reserved_for_pilot" if key == FIRST_CELL else "not_started", "evidence_refs": []}
                for key, cell in cells.items()]}


def validate_state(state, read_ref=None):
    """Validate complete identities and rehash every state proof, without writing."""
    cells = _registry()
    need(isinstance(state, dict) and set(state) == STATE_FIELDS and state["schema"] == STATE_SCHEMA
         and ((state["mode"] == "PREPARE" and state["verified"] is False)
              or (state["mode"] == "RECEIVED" and state["verified"] is True))
         and state["source_zip_sha256"] == SOURCE_SHA and state["plan_sha256"] == PLAN_SHA
         and state["first_cell"] == cells[FIRST_CELL], "Closed preparation state/source/plan required")
    records = state["records"]
    need(isinstance(records, list) and len(records) == 60, "Complete sixty-cell ledger required")
    seen = set()
    for row in records:
        need(isinstance(row, dict) and set(row) == CELL_FIELDS | {"status", "evidence_refs"},
             "Exact cell/status/evidence ledger fields required")
        key = row["cell_key"]
        need(isinstance(key, str) and key in cells and key not in seen
             and {field: row[field] for field in CELL_FIELDS} == cells[key],
             "Unknown, duplicated or drifted cell/model/MAX/session identity")
        seen.add(key)
        status, refs = row["status"], row["evidence_refs"]
        need(isinstance(status, str) and status in STATUSES and isinstance(refs, list), "Unknown native ledger status")
        if status in {"not_started", "reserved_for_pilot"}:
            need(not refs and ((key == FIRST_CELL) == (status == "reserved_for_pilot")),
                 "Only the pilot may be reserved; unstarted records carry no asserted execution proof")
        else:
            need(bool(refs), "Every started/held/terminal record needs real hash-bound native receipts")
            need(len({json.dumps(ref, sort_keys=True) for ref in refs}) == len(refs), "Repeated native evidence reference")
            for ref in refs:
                _evidence(ref, cells[key], status, cells, read_ref)
    need(seen == set(cells), "Missing registered native cells")
    _release(state["first_release_ref"], cells, read_ref)
    need(state["mode"] != "RECEIVED" or state["first_release_ref"] is not None,
         "A received root state requires the real first-batch extension release")
    return copy.deepcopy(state)


def _reserved(registry_root, cells):
    if registry_root is None:
        return set()
    root = _physical(registry_root, directory=True)
    sessions, identifiers = set(), set()
    for path in sorted(root.glob("*.reservation.json")):
        value = _reservation(_json(_physical(path).read_bytes()), cells)
        need(value["session_id"] not in sessions and value["reservation_id"] not in identifiers,
             "Duplicate pending/consumed session or reservation in registry")
        sessions.add(value["session_id"])
        identifiers.add(value["reservation_id"])
    return sessions


def select_cells(state, registry_root=None, limit=1, read_ref=None):
    """List preparation candidates, excluding every reserved or used native session."""
    need(type(limit) is int and 1 <= limit <= 60, "Selection limit must be an integer from one to sixty")
    checked = validate_state(state, read_ref)
    cells = _registry()
    reserved = _reserved(registry_root, cells)
    candidates = [{key: row[key] for key in CELL_FIELDS} for row in checked["records"]
                  if row["cell_key"] != FIRST_CELL and row["status"] == "not_started"
                  and row["session_id"] not in reserved][:limit]
    return {"schema": SELECTION_SCHEMA, "mode": "PREPARE", "verified": False,
            "source_zip_sha256": SOURCE_SHA, "plan_sha256": PLAN_SHA,
            "prerequisite_pending": checked["first_release_ref"] is None,
            "candidates": candidates, "commands_to_execute": []}


def selection_for_cell(state, cell_key, registry_root, read_ref=None):
    """Return the exact single cell, refusing missing release or session reuse."""
    checked = validate_state(state, read_ref)
    cells = _registry()
    need(isinstance(cell_key, str) and cell_key in cells and cell_key != FIRST_CELL,
         "Extension may select only registered non-pilot cells")
    need(checked["mode"] == "RECEIVED" and checked["verified"] is True,
         "Operational extension requires a received verified root state")
    need(checked["first_release_ref"] is not None, "First-batch extension release prerequisite pending")
    need(registry_root is not None, "Operational selection requires the current native reservation registry")
    row = next(row for row in checked["records"] if row["cell_key"] == cell_key)
    need(row["status"] == "not_started", "Cell has already started or is held/terminal")
    need(row["session_id"] not in _reserved(registry_root, cells), "Session already has a pending or consumed reservation")
    return copy.deepcopy(cells[cell_key])
