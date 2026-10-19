"""Pure first-batch receipt frontier. Read files, list missing refs, never fetch them."""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

BASE = Path(__file__).resolve().parents[2]
DEST = BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Collecte-Preparation-r1"
AUDITOR = BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r1/lecteur/first_batch_audit.py"
AUDITOR_SHA = "dce92d6e1735a8b594528b61bc0134d6069ab524a5fecc0eb08c1d5a024d4e13"
SCHEMA = "hpc-forest-matrix15-first-batch-collection-input-v1"
LEAVES = {"raw", "request", "response", "ready", "delivered", "invocation", "process", "owner", "worker", "plan"}
CALL_REFS = {"request": "request", "response": "response", "ready": "ready", "invocation": "invocation",
             "delivered": "delivered", "process": "process", "error_and_usage_log": "raw"}


def runtime():
    class PinnedLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            raw = Path(self.path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != AUDITOR_SHA:
                raise ValueError("Pinned first-batch auditor changed")
            return compile(raw, self.path, "exec", dont_inherit=True)
    loader = PinnedLoader("matrix15_collection_auditor", str(AUDITOR))
    spec = importlib.util.spec_from_file_location(loader.name, AUDITOR, loader=loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def owned_output(reader, value):
    path = Path(value)
    reader.need(path.is_absolute() and ".." not in path.parts and path.is_relative_to(DEST), "Owned absolute collection output required")
    reader.need(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)),
                "Linked collection output refused")
    path = path.resolve()
    reader.need(path.is_relative_to(DEST.resolve()) and path != DEST.resolve() and not path.exists(), "Fresh collection output required")
    return path


def short_ref(reader, value):
    reader.need(isinstance(value, dict) and {"path", "sha256"} <= set(value)
                and isinstance(value["path"], str) and reader.HASH.fullmatch(str(value["sha256"])), "Exact hashed evidence reference required")
    result = {"path": value["path"], "sha256": value["sha256"]}
    if "bytes" in value:
        reader.need(type(value["bytes"]) is int and value["bytes"] >= 0, "Reference byte count must be exact")
        result["bytes"] = value["bytes"]
    return result


def inventory(reader, catalog, locals_):
    # The pinned auditor performs the strict raw-SCP checks. Empty inventories are
    # useful before the first received snapshot, so avoid its nonempty precondition.
    if catalog:
        return reader.Evidence(catalog, locals_)
    evidence = reader.Evidence.__new__(reader.Evidence)
    evidence.map, evidence.inventory = {}, []
    reader.need(isinstance(locals_, list), "Local reference list required")
    for item in locals_:
        evidence.add(reader.ref2(item), reader.checked_local(item))
        evidence.inventory.append({"local_ref": item})
    return evidence


def collect(value, reader):
    fields = {"schema", "mode", "authorization", "paused_snapshot", "catalog", "local_refs", "cache_root", "policy_ref",
              "audit_output_directory", "output_directory"}
    reader.need(set(value) == fields and value.get("schema") == SCHEMA, "Exact collection input fields required")
    reader.need(value.get("mode") in {"PREPARE", "COLLECT"}, "Only PREPARE/COLLECT modes exist")
    if value["mode"] == "PREPARE":
        return {"schema": "hpc-forest-matrix15-first-batch-collection-frontier-v1", "collection_complete": False,
                "verified": False, "prepared_only": True, "required_references": 0, "received_downloads": 0,
                "missing_remote": [], "missing_private": [], "blockers": ["No actual reception requested"],
                "audit_input": None, "audit_invoked": False, "independent_sqlite_backup_claimed": False,
                "network_or_job_or_model_or_process_action": False}
    reader.need(isinstance(value["catalog"], list) and isinstance(value["local_refs"], list), "Actual download/local catalogs required")
    evidence = inventory(reader, value["catalog"], value["local_refs"])
    local_refs = {item["path"]: item for item in value["local_refs"]}
    pending, required, parsed, blockers, missing_private = [], {}, set(), [], []
    first = None
    authorization = None

    def add(ref, role):
        item = short_ref(reader, ref)
        path, checksum = item["path"], item["sha256"]
        name = PurePosixPath(path.replace("\\", "/")).name.casefold()
        reader.need(not name.endswith((".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm")),
                    "Mutable SQLite/WAL files are outside this receipt collector")
        reader.need(path.startswith("/") or PureWindowsPath(path).is_absolute(), "Only original absolute ARM/Windows refs accepted")
        if path.startswith("/"):
            reader.remote_ref({"path": path, "sha256": checksum})
        known = required.get(path)
        reader.need(known is None or known["sha256"] == checksum, "Conflicting SHA for one original path: " + path)
        if known is None:
            required[path] = {**item, "roles": set()}
        elif "bytes" in item:
            reader.need("bytes" not in known or known["bytes"] == item["bytes"], "Conflicting byte counts for one ref")
            known["bytes"] = item["bytes"]
        if role not in required[path]["roles"]:
            required[path]["roles"].add(role)
            pending.append((path, role))

    add(value["authorization"], "authorization")
    add(value["paused_snapshot"], "snapshot")
    missing = {}
    while pending:
        original, role = pending.pop(0)
        item = required[original]
        key = (original, item["sha256"])
        if key not in evidence.map:
            if original.startswith("/"):
                missing[original] = {"remote_ref": {k: item[k] for k in ("path", "sha256")}, "roles": sorted(item["roles"])}
                continue
            # Windows refs are actual local artifacts, never renamed ARM files.
            path = Path(original)
            if not path.is_file():
                missing_private.append({"path": original, "sha256": item["sha256"], "reason": "Local dependency missing"})
                continue
            actual = reader.local_ref(path)
            reader.need(actual["sha256"] == item["sha256"], "Actual local dependency digest differs: " + original)
            if "bytes" in item:
                reader.need(actual["bytes"] == item["bytes"], "Actual local dependency byte count differs")
            evidence.add({"path": original, "sha256": item["sha256"]}, path)
            evidence.inventory.append({"local_ref": actual})
            local_refs[original] = actual
        if (original, role) in parsed:
            continue
        parsed.add((original, role))
        file_ref = {k: item[k] for k in ("path", "sha256")}
        if "bytes" in item:
            file_ref["bytes"] = item["bytes"]
        path = evidence.resolve(file_ref)
        if role in LEAVES:
            continue  # Never traverse model-provided request/response data or raw logs.
        document = evidence.read(file_ref)
        if role == "authorization":
            reader.need(document.get("schema") == "hpc-forest-matrix15-authorization-v1" and document.get("verified") is True,
                        "Unknown/negative original authorization")
            authorization = document
            for name, child_role in (("plan", "plan"), ("cli_identity", "cli")):
                add(document["artifacts"][name], child_role)
        elif role == "snapshot":
            reader.need(document.get("schema") == "hpc-forest-matrix15-first-batch-paused-v1"
                        and document.get("waiting_for_external_root_audit") is True,
                        "Unknown/unpaused first-batch snapshot")
            add(document["first_start_receipt"], "first")
            add(document["evaluation_snapshot"], "evaluation")
        elif role == "first":
            reader.need(document.get("schema") == "hpc-forest-matrix15-first-start-v1"
                        and document.get("verified") is True and document.get("technical_errors_found") is False
                        and document.get("invocation_unknown") is False, "Unknown/technical first batch cannot be closed")
            first = document
            for name, child_role in (("channel_owner", "owner"), ("worker_identity", "worker"),
                                     ("runtime_reference_origin", "origin"), ("evaluation_snapshot", "evaluation")):
                add(document[name], child_role)
            for call in document["all_started_calls_reconciled"]:
                for name, child_role in CALL_REFS.items():
                    add(call[name], child_role)
            for item in document["first_real_evaluation"].get("logs", []):
                add(item, "raw")
            for item in document["command_stream_provenance"]:
                add(item, "stream")
        elif role == "cli":
            reader.need(isinstance(document.get("files"), dict)
                        and set(document["files"]) == {"codex.exe", "codex-code-mode-host.exe", "codex-command-runner.exe",
                                                    "codex-windows-sandbox-setup.exe"}, "All four exact local CLI binaries required")
            for item in document["files"].values():
                add(item, "raw")
        elif role == "evaluation":
            reader.need(document.get("never_model_input") is True and isinstance(document.get("outcome"), dict),
                        "Unknown evaluation snapshot")
        elif role == "origin":
            reader.need(document.get("schema") == "hpc-forest-matrix15-runtime-reference-origin-v1" and document.get("verified") is True,
                        "Unknown/negative runtime reference origin")
            for item in document["command_stream_provenance"]:
                add(item, "stream")
        elif role in {"stream", "context"}:
            expected = "hpc-forest-matrix15-command-execution-v1" if role == "stream" else "hpc-forest-matrix15-command-context-v1"
            reader.need(document.get("schema") == expected, "Unknown command-stream schema")
            if role == "stream":
                reader.need(document.get("verified") is True, "Negative command stream")
                add(document["context"], "context")
                add(document["original_process_result"], "process")
                add(document["streams"]["combined_stdout_stderr"], "raw")
            for name in ("binary_before", "binary_after"):
                if document.get(name) is not None:
                    add(document[name], "raw")
            for name in ("argument_files_before", "argument_files_after"):
                for item in document.get(name, []):
                    add(item, "raw")
        else:
            raise reader.Refusal("Unknown traversal role")
    private_nonces = {}
    cache = Path(value["cache_root"])
    if first is not None:
        expected_nonces = []
        for call in first["all_started_calls_reconciled"]:
            match = re.fullmatch(r"([a-f0-9]{32})\.request\.json", PurePosixPath(call["request"]["path"]).name)
            reader.need(match is not None and match[1] not in expected_nonces, "Unknown/duplicate first-batch nonce")
            nonce = match[1]
            expected_nonces.append(nonce)
            request_ref = call["request"]
            if (request_ref["path"], request_ref["sha256"]) in evidence.map:
                reader.need(evidence.read(request_ref).get("nonce") == nonce, "Received request has an unknown/foreign nonce")
            response_ref = call["response"]
            successful = ((response_ref["path"], response_ref["sha256"]) in evidence.map
                          and evidence.read(response_ref).get("error") is None)
            files = {}
            for name in sorted(reader.CACHE_FILES | {"agent-result.json"}):
                path = cache / nonce / name
                if path.is_file():
                    files[name] = reader.local_ref(path)
                elif name != "agent-result.json" or successful:
                    missing_private.append({"path": str(path), "reason": "Required private nonce file missing"})
            private_nonces[nonce] = files
        if cache.is_dir():
            actual = {p.name for p in cache.iterdir() if p.is_dir() and reader.NONCE.fullmatch(p.name)}
            if actual - set(expected_nonces):
                blockers.append("Private cache has started/foreign nonces absent from immutable first receipt: " + ",".join(sorted(actual - set(expected_nonces))))
            if (cache / "cli-technical-hold.json").exists():
                blockers.append("Actual private technical hold blocks audit input")
            for claim in cache.rglob("generation-claimed.json"):
                if claim.parent.parent != cache or claim.parent.name not in expected_nonces:
                    blockers.append("Unresolved/foreign private generation claim: " + str(claim))
        binding_file = cache / "CELL-BINDING.json"
        if not binding_file.is_file():
            missing_private.append({"path": str(binding_file), "reason": "Private cache binding missing"})
        elif authorization:
            cache_binding = reader.parse(reader.ordinary(binding_file).read_bytes())
            if any(cache_binding.get(k) != authorization.get(k) for k in
                   ("scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id", "remote_root")):
                blockers.append("Private cache binding differs from received authorization")
    try:
        reader.checked_local(value["policy_ref"])
    except (ValueError, OSError, TypeError) as exc:
        missing_private.append({"reason": "Exact private policy unavailable", "detail": str(exc)})
    missing_remote = [{**item, "roles": sorted(required[path]["roles"])} for path, item in missing.items()]
    complete = bool(first and authorization) and not missing_remote and not missing_private and not blockers
    audit_input = None
    if complete:
        source_root = BASE / "outputs/HPC-Forest-Matrice15-Admission-r2"
        audit_input = {"schema": reader.INPUT_SCHEMA, "evidence_origin": "received", "source": {
            "project_root": str(BASE / "work/matrix15-admission-no-cycle-r2/project"),
            "source_zip": reader.local_ref(source_root / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"),
            "runtime_manifest": reader.local_ref(source_root / "RUNTIME-PRIVE-LOCAL.json")},
            "authorization": value["authorization"], "paused_snapshot": value["paused_snapshot"],
            "received": value["catalog"], "local_refs": list(local_refs.values()), "cache_root": str(cache),
            "private_nonces": private_nonces, "policy_ref": value["policy_ref"], "output_directory": value["audit_output_directory"]}
        evidence.recheck()
    return {"schema": "hpc-forest-matrix15-first-batch-collection-frontier-v1", "verified": False,
            "collection_complete": complete, "required_references": len(required), "received_downloads": len(value["catalog"]),
            "missing_remote": missing_remote, "missing_private": missing_private, "blockers": blockers,
            "audit_input": audit_input, "audit_invoked": False, "independent_sqlite_backup_claimed": False,
            "network_or_job_or_model_or_process_action": False}


def run(input_path, checksum):
    reader = runtime()
    path = reader.ordinary(input_path)
    reader.need(reader.sha(path.read_bytes()) == checksum, "Sealed collection input changed")
    value = reader.parse(path.read_bytes())
    output = owned_output(reader, value["output_directory"])
    output.mkdir(parents=True, exist_ok=False)
    try:
        result = collect(value, reader)
        audit_input = result.pop("audit_input")
        reader.need(reader.sha(path.read_bytes()) == checksum, "Collection input changed during read")
        if audit_input is not None:
            result["audit_input_proposal"] = reader.write_exclusive(output / "INPUT-AUDIT-PROPOSITION.json", audit_input)
        else:
            result["audit_input_proposal"] = None
        receipt = reader.write_exclusive(output / "NEXT-DOWNLOADS.json", result)
        return receipt
    except Exception as exc:
        reader.write_exclusive(output / "REFUS.json", {"verified": False, "reason": type(exc).__name__ + ": " + str(exc),
            "audit_invoked": False, "network_or_job_or_model_or_process_action": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.input, args.input_sha256)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
