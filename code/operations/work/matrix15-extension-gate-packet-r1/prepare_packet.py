"""Pure first-batch extension packet materializer; no transport or launch API."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
OWNED = BASE / "outputs/HPC-Forest-Matrice15-Extension-Gate-Packet-r1"
EXECUTION = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01"
REMOTE = "/gpfs/scratch/nimarano/hpc-forest-matrix15-first-batch-extension-gate-20261019-root-01"
BUILDER = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1/build_inputs.py"
BUILDER_SHA = "4d26cdab42a7b47cc8d326fbd638e9f44fbe404dbcac40ad64cf7dba42dd99d1"
ROOT_SHA = "20c92abe5cfb61bff5178492f9b5f4a79ddf7dd8d8c5a4634650827f092097c8"
PROPOSAL_SHA = "47c230711a7c6c3757c1495996a2c1be36b7b5afa21530541df37d4de422eb54"
ACCEPTED_SHA = "60f1bb327a0caa9fbf3d873cf7a4ab967db234728832de9a2f03206798e10c87"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf8")


def sized(path):
    path = Path(path)
    need(path.is_absolute() and path.is_file() and not any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)),
        "Ordinary absolute input required")
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def ref(path):
    item = sized(path)
    return {key: item[key] for key in ("path", "sha256")}


def read(path):
    sized(path)
    return json.loads(Path(path).read_bytes().decode("utf-8-sig"))


def emit(path, value):
    path = Path(path)
    need(path.is_absolute() and path.is_relative_to(OWNED) and path != OWNED
         and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)),
         "New output must remain in packet ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(value if isinstance(value, bytes) else raw(value))
    return ref(path)


def runtime():
    builder_raw = BUILDER.read_bytes()
    need(ref(BUILDER)["sha256"] == hashlib.sha256(builder_raw).hexdigest() == BUILDER_SHA, "Pinned operation builder changed")
    spec = importlib.util.spec_from_file_location("extension_packet_upstream", BUILDER)
    module = importlib.util.module_from_spec(spec)
    # Source-only execution of the already pinned pure builder avoids stale pyc.
    exec(compile(builder_raw, str(BUILDER), "exec", dont_inherit=True), module.__dict__)  # noqa: S102
    upstream, reader, dynamic, capacity, bootstrap = module.runtime()
    return module, upstream, reader, dynamic, capacity, bootstrap


def transfer(remote, local, receipt):
    return {"remote_ref": remote, "local_ref": sized(local), "transfer_receipt": sized(receipt)}


def prepare(destination):
    destination = Path(destination)
    need(destination.is_absolute() and destination.is_relative_to(OWNED) and not destination.exists(),
         "New packet directory required")
    _builder, _upstream, _reader, dynamic, _capacity, _bootstrap = runtime()
    gate_module = sys.modules["extension_gate"]
    selection = sys.modules["selection"]
    review_path = EXECUTION / "extension-gate-r1/ROOT-REVIEW-REEL.json"
    proposal_path = EXECUTION / "first-batch-audit-r2/RECU-PROPOSITION.json"
    accepted_path = EXECUTION / "first-batch-release-accepted-scp.json"
    need(ref(review_path)["sha256"] == ROOT_SHA and ref(proposal_path)["sha256"] == PROPOSAL_SHA
         and ref(accepted_path)["sha256"] == ACCEPTED_SHA, "Actual primary receipt changed")
    review = read(review_path)
    release_path = EXECUTION / "first-batch-audit-r2/autorisation-apres-premier-batch.PROPOSITION.json"
    projection_path = EXECUTION / "first-batch-audit-r2/audit-cli-prive-digest.json"
    release = read(release_path)
    binding = review["first_binding"]
    result_root = binding["remote_root"] + "/results-" + binding["job_id"]
    gate = {"schema": gate_module.SCHEMA, "verified": True, "evidence_origin": "received",
        "source_zip_sha256": gate_module.SOURCE_SHA, "plan_sha256": gate_module.PLAN_SHA,
        "first_binding": binding,
        "authorization": {"path": binding["remote_root"] + "-admission/authorization.json",
                          "sha256": ref(EXECUTION / "first-batch-received-wave1/authorization.json")["sha256"]},
        "paused_snapshot": release["paused_snapshot"], "first_start_receipt": release["first_start_receipt"],
        "evaluation_snapshot": release["evaluation_snapshot"],
        "release": {"path": result_root + "/autorisation-apres-premier-batch.json", "sha256": ref(release_path)["sha256"]},
        "private_cli_audit": release["private_cli_audit"],
        "engine_release_receipt": {"path": result_root + "/premier-batch-release-verifiee.json", "sha256": ACCEPTED_SHA},
        "proposal_receipt": {"path": REMOTE + "/proposal-receipt.json", "sha256": PROPOSAL_SHA},
        "root_reception_review": {"path": REMOTE + "/root-reception-review.json", "sha256": ROOT_SHA}}
    local = {"authorization": EXECUTION / "first-batch-received-wave1/authorization.json",
        "paused_snapshot": EXECUTION / "first-batch-received-wave1/paused.json",
        "first_start_receipt": EXECUTION / "first-batch-received-wave1/first.json",
        "evaluation_snapshot": EXECUTION / "first-batch-received-wave1/evaluation.json",
        "release": release_path, "private_cli_audit": projection_path,
        "engine_release_receipt": accepted_path, "proposal_receipt": proposal_path,
        "root_reception_review": review_path}
    exact_map = {(gate[name]["path"], gate[name]["sha256"]): path for name, path in local.items()}
    arm_statics = read(BASE / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2/STATIC-ARTIFACTS-ARM.json")
    exact_map[(arm_statics["plan"]["path"], arm_statics["plan"]["sha256"])] = EXECUTION / "readback-final-r2-02/plan.bin"
    actual_audit = read(BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Collecte-Preparation-r2/job-755562-collecte-r1/INPUT-AUDIT-PROPOSITION.json")
    request_transfers = []
    for call in read(local["first_start_receipt"])["all_started_calls_reconciled"]:
        matches = [entry for entry in actual_audit["received"] if entry["remote_ref"] == call["request"]]
        need(len(matches) == 1, "Exactly one actual SCP reception per source request required")
        item = matches[0]
        request_transfers.append(item)
        exact_map[(call["request"]["path"], call["request"]["sha256"])] = Path(item["local_ref"]["path"])

    def resolve(item):
        key = (item["path"], item["sha256"])
        need(key in exact_map, "Unlisted exact host reference: " + str(item["path"]))
        return exact_map[key]

    from hpc_forest import matrix15_first_batch as batch
    gate_result = gate_module.validate_gate(gate, read_ref=resolve, native=dynamic.native, batch=batch)
    gate_ref = emit(destination / "extension-gate.json", gate)
    remote_gate = {"path": REMOTE + "/extension-gate.json", "sha256": gate_ref["sha256"]}
    slot = EXECUTION / "admission-windows-r2/slot-reservation.json"
    reservation = read(slot)
    need(reservation["consumed"] is False and reservation["session_id"] == binding["session_id"],
         "Original immutable held reservation required")
    state = selection.template_state()
    state.update(mode="RECEIVED", verified=True, first_release_ref=gate_ref)
    for row in state["records"]:
        if row["cell_key"] == selection.FIRST_CELL:
            row.update(status="held", evidence_refs=[ref(slot)])
    local_map = {**exact_map, (gate_ref["path"], gate_ref["sha256"]): Path(gate_ref["path"]),
                 (str(slot), ref(slot)["sha256"]): slot}
    selection.validate_state(state, lambda item: local_map[(item["path"], item["sha256"])])
    state_ref = emit(destination / "selection-state-60.json", state)
    wave1 = read(EXECUTION / "FIRST-BATCH-WAVE1-SUMMARY.json")
    received = []
    for result in wave1["results"]:
        value = result["value"]
        if value["name"] != "origin":
            received.append(transfer(value["remote_ref"], value["local_path"], value["receipt_path"]))
    received.append(transfer(gate["engine_release_receipt"], accepted_path,
                             EXECUTION / "FIRST-BATCH-RELEASE-ACCEPTED-SCP-REEL.json"))
    received.append(transfer(arm_statics["plan"], EXECUTION / "readback-final-r2-02/plan.bin",
                             EXECUTION / "readback-final-raw-r2-02/plan.json"))
    received.extend(request_transfers)
    inventory = {"schema": "hpc-forest-matrix15-extension-received-evidence-v1", "evidence_origin": "received",
        "received": received, "local_refs": [sized(Path(gate_ref["path"])), sized(slot)]}
    # This actual eight-transfer subset is deliberately incomplete. No pending ARM
    # reference is inserted as local evidence to impersonate a real SCP readback.
    partial_ref = emit(destination / "RECEIVED-INVENTORY-PARTIAL.json", inventory)
    dynamic.received_evidence(partial_ref).recheck()
    pending = [gate[key] for key in ("release", "private_cli_audit", "proposal_receipt", "root_reception_review")]
    pending.append(remote_gate)
    pending_ref = emit(destination / "PENDING-READBACKS.json", {"schema": "hpc-forest-root-pending-readbacks-v1",
        "received": False, "refs": pending})
    uploads = [{"local": sized(proposal_path), "remote": gate["proposal_receipt"]},
               {"local": sized(review_path), "remote": gate["root_reception_review"]},
               {"local": sized(Path(gate_ref["path"])), "remote": remote_gate}]
    upload_ref = emit(destination / "PENDING-UPLOADS.json", {"schema": "hpc-forest-root-pending-uploads-v1",
        "uploaded": False, "ordered_members": uploads})
    rows = [{"remote_ref": {"path": key[0], "sha256": key[1]}, "local_ref": sized(path),
             "actual_scp_received": any(item["remote_ref"] == {"path": key[0], "sha256": key[1]} for item in received)}
            for key, path in exact_map.items()]
    emit(destination / "HOST-REF-MAP.json", {"schema": "hpc-forest-explicit-host-ref-map-v1", "entries": rows})
    return emit(destination / "PREPARATION.json", {"schema": "hpc-forest-matrix15-extension-gate-packet-preparation-v1",
        "mode": "PREPARE", "verified": False, "local_historical_gate_semantics_passed": True,
        "local_gate_check": gate_result, "gate": gate_ref, "gate_arm_pending": remote_gate,
        "selection_state": state_ref, "partial_inventory": partial_ref, "pending_readbacks": pending_ref,
        "pending_uploads": upload_ref, "native_authorization": False, "jobs_submitted": 0,
        "native_model_calls": 0, "capacity_registry_modified": False, "automatic_extension": False,
        "pilot_status_limitation": "held records the immutable unconsumed admission reservation; scientific terminal completion is separate",
        "missing_actual_readbacks": len(pending), "private_raw_audit_exported": False})


def finalize(preparation_path, catalog_path, destination):
    preparation = read(preparation_path)
    need(preparation.get("mode") == "PREPARE" and preparation.get("verified") is False,
         "Original pending preparation required")
    destination = Path(destination)
    need(destination.is_absolute() and destination.is_relative_to(OWNED) and not destination.exists(), "New final directory required")
    _builder, _upstream, _reader, dynamic, _capacity, _bootstrap = runtime()
    partial = read(preparation["partial_inventory"]["path"])
    need(ref(preparation["partial_inventory"]["path"]) == preparation["partial_inventory"], "Partial inventory changed")
    supplied = read(catalog_path)
    need(isinstance(supplied, list), "Actual received catalog list required")
    need(ref(preparation["pending_readbacks"]["path"]) == preparation["pending_readbacks"], "Pending reference list changed")
    pending = read(preparation["pending_readbacks"]["path"])["refs"]
    gate = read(preparation["gate"]["path"])
    need(ref(preparation["gate"]["path"]) == preparation["gate"] and preparation["gate_arm_pending"] ==
         {"path": REMOTE + "/extension-gate.json", "sha256": preparation["gate"]["sha256"]}, "Exact gate source and ARM destination required")
    need(pending == [gate[key] for key in ("release", "private_cli_audit", "proposal_receipt", "root_reception_review")]
         + [preparation["gate_arm_pending"]], "Predeclared five readbacks differ")
    expected = {(item["path"], item["sha256"]) for item in pending}
    need(len(supplied) == len(expected) and {(item["remote_ref"]["path"], item["remote_ref"]["sha256"]) for item in supplied} == expected,
         "Exactly the five pending real SCP readbacks are required")
    inventory = {**partial, "received": partial["received"] + supplied}
    inventory_ref = emit(destination / "RECEIVED-INVENTORY.json", inventory)
    gate_ref = preparation["gate"]
    gate_arm = preparation["gate_arm_pending"]
    evidence = dynamic.received_evidence(inventory_ref)
    evidence.resolve(gate_arm)
    gate_result, _unused = dynamic.verify_extension_gate(gate_ref, inventory_ref)
    state_ref = preparation["selection_state"]
    need(ref(state_ref["path"]) == state_ref, "Selection state changed")
    sys.modules["selection"].validate_state(read(state_ref["path"]), evidence.resolve)
    evidence.recheck()
    prerequisite_ref = emit(destination / "PREREQUISITES.json", {"first_batch_extension_gate": gate_ref,
        "gate_arm": gate_arm, "first_batch_received_evidence": inventory_ref, "selection_state": state_ref})
    return emit(destination / "RECEIPT.json", {"schema": "hpc-forest-matrix15-extension-gate-packet-receipt-v1",
        "verified": True, "evidence_origin": "received", "gate_check": gate_result,
        "received_arm_refs": len(inventory["received"]), "prerequisites": prerequisite_ref,
        "native_authorization": False, "jobs_submitted": 0, "native_model_calls": 0,
        "capacity_registry_modified": False, "automatic_extension": False})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", allow_abbrev=False)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("finalize", allow_abbrev=False)
    p.add_argument("--preparation", type=Path, required=True)
    p.add_argument("--received-catalog", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = prepare(args.output) if args.command == "prepare" else finalize(args.preparation, args.received_catalog, args.output)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
