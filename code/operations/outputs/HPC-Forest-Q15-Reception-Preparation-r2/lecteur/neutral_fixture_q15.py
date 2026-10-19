"""Construct NEUTRAL Q15 test data without running source, Git or an executable.

This module is test scaffolding, not received evidence. It reads the caller's
prepared package only as bytes/JSON and writes only inside the supplied fresh
NEUTRAL test directory. No generated artifact represents a real computation.
The caller must use receive(..., neutral_fixture=True); production rejects the
fixed evidence_origin="NEUTRAL". There is no CLI or origin/promotion option.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sqlite3
import statistics
import tarfile
import zlib


SCOPE = "hpc-forest-matrix15-baseline-qualification-r1"
NEUTRAL_NOTICE = "NEUTRAL fixture only: no job, compiler, program, model or measurement was run."
JOB_ID = "123456789"
REMOTE_OUTPUT = "/NEUTRAL/output"
REMOTE_PACKAGE = "/NEUTRAL/prepared-package"
TIMES = [0.01, 0.011, 0.012, 0.013, 0.014]
MAXIMUM_SECONDS = 1800
SHARED_STARTED = 1792370000


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def reference(path, raw):
    return {"path": str(path), "sha256": sha256(raw), "bytes": len(raw)}


def local_reference(path):
    return reference(path, path.read_bytes())


def read_inventory(directory):
    """Read regular prepared files as data; no received module is imported."""
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


def add_git_baseline(files, subject, official):
    """Build loose Git records manually; never call Git or hooks."""
    prefix = subject + "/repo/"
    def object_record(kind, body):
        raw = kind.encode("ascii") + b" " + str(len(body)).encode("ascii") + b"\0" + body
        oid = hashlib.sha1(raw).hexdigest()
        files[prefix + ".git/objects/" + oid[:2] + "/" + oid[2:]] = zlib.compress(raw)
        return oid

    nested = {}
    for name, raw in official.items():
        files[prefix + name] = raw
        path = PurePosixPath(name)
        node = nested
        for part in path.parts[:-1]:
            node = node.setdefault(part, {})
        node[path.name] = object_record("blob", raw)

    def tree_record(node):
        entries = []
        for name, value in node.items():
            directory = isinstance(value, dict)
            oid = tree_record(value) if directory else value
            mode = b"40000" if directory else b"100644"
            entries.append((name + ("/" if directory else ""), mode + b" " + name.encode() + b"\0" + bytes.fromhex(oid)))
        return object_record("tree", b"".join(row for _, row in sorted(entries)))

    tree = tree_record(nested)
    body = ("tree " + tree + "\nauthor NEUTRAL Fixture <neutral@example.invalid> 0 +0000\n"
            "committer NEUTRAL Fixture <neutral@example.invalid> 0 +0000\n\n" + NEUTRAL_NOTICE + "\n").encode()
    commit = object_record("commit", body)
    files[prefix + ".git/HEAD"] = b"ref: refs/heads/NEUTRAL-baseline\n"
    files[prefix + ".git/refs/heads/NEUTRAL-baseline"] = (commit + "\n").encode()
    # A real git init/commit creates these logs too. They are Git metadata,
    # never process command logs, while still bound by the exact archive manifest.
    reflog = ("0" * 40 + " " + commit + " NEUTRAL fixture <neutral@example.invalid> 0 +0000\tcommit (initial): NEUTRAL baseline\n").encode()
    files[prefix + ".git/logs/HEAD"] = reflog
    files[prefix + ".git/logs/refs/heads/NEUTRAL-baseline"] = reflog
    return commit, tree


def neutral_binary():
    """A non-executable byte marker with the header the reader checks."""
    raw = bytearray(64)
    raw[:6] = b"\x7fELF\x02\x01"
    raw[18:20] = (183).to_bytes(2, "little")
    marker = b"NEUTRAL_FIXTURE_NEVER_EXECUTE"
    raw[24:24 + len(marker)] = marker
    return bytes(raw)


def policy_for(subject, config, plan):
    row = plan["subjects"][subject]
    return {
        "mode": "command-stream-v1",
        "qualification_binding": {
            "schema": "hpc-forest-matrix15-qualification-binding-v1", "scope_id": SCOPE,
            "subject_id": subject, "job_id": JOB_ID, "remote_root": REMOTE_OUTPUT, "seed": 23,
            "prepared_manifest_sha256": plan["preparation_sha256"],
            "r1_contract_sha256": row["r1_contract_sha256"], "native_authorization": False,
        },
        "source_runtime_sha256": plan["source_bindings"]["q_runtime_manifest_sha256"],
        "subject_contract_sha256": row["r1_contract_sha256"],
        "qualification_protocol_sha256": config["source_plan"]["sha256"],
    }


def log_paths(subject, phase, warmups):
    names = ["build.log", "correctness.log"]
    if phase == "confirmation":
        names += [f"warmup-{i}.log" for i in range(warmups)] + [f"sample-{i}.log" for i in range(5)]
    stem = f"{REMOTE_OUTPUT}/{subject}/logs/e1/baseline-e1/{phase}/attempt-001/"
    return [stem + name for name in names]


def add_commands(files, subject, phase, settings, identity, policy, protocol_id, outcome, binary_raw):
    """Add synthetic observations with exactly the original command templates."""
    def add_remote(path, raw):
        relative = PurePosixPath(path).relative_to(REMOTE_OUTPUT).as_posix()
        files[relative] = raw
        return reference(path, raw)

    stem = f"{REMOTE_OUTPUT}/{subject}"
    worktree = stem + "/repo"
    build = f"{stem}/builds/e1/baseline-e1/{phase}/attempt-001"
    binary = build + "/solution"
    binary_ref = add_remote(binary, binary_raw)
    source = {"commit": outcome["commit"], "tree_hash": outcome["tree_hash"], "clean": True}
    summaries = []
    for log in outcome["logs"]:
        operation = "build" if log.endswith("/build.log") else "check" if log.endswith("/correctness.log") else "benchmark"
        variables = {"python": identity["python_executable"], "trusted": stem + "/trusted", "worktree": worktree,
                     "build": build, "binary": binary, "phase": phase}
        argv = [arg.format_map(variables) for arg in settings["protocol"][operation]]
        before, after = [], []
        for index, argument in enumerate(argv):
            path = PurePosixPath(argument) if argument.startswith("/") else PurePosixPath(worktree) / argument
            if path.is_relative_to(REMOTE_OUTPUT):
                relative = path.relative_to(REMOTE_OUTPUT).as_posix()
                raw = files.get(relative)
                if raw is None:
                    continue
            elif index == 0:
                raw = (NEUTRAL_NOTICE + " Synthetic external executable observation: " + argument).encode()
            else:
                continue
            item = {"argument_index": index, "argument": argument, **reference(str(path), raw)}
            after.append(item)
            if str(path) != binary or operation != "build":
                before.append(item)
        context = {
            "schema": "hpc-forest-matrix15-qualification-command-context-v1",
            "mode": "command-stream-v1", "never_model_input": True, "operator_binding": policy,
            "protocol_id": protocol_id, "operation": operation, "experiment_id": "baseline-e1", "epoch": 1,
            "commit": outcome["commit"], "tree_hash": outcome["tree_hash"], "phase": phase,
            "argv": argv, "worktree": worktree, "binary_path": binary,
            "environment_overrides": settings["protocol"]["environment"], "source_before": source,
            "binary_before": None if operation == "build" else binary_ref, "argument_files_before": before,
            "stdin_layout": "original_run_process_DEVNULL_unchanged", "inherited_environment_captured": False,
        }
        context_ref = add_remote(log + ".command-context.json", json_bytes(context))
        raw_log = json_bytes({"correct": True, "cases": 1, "NEUTRAL": NEUTRAL_NOTICE}) if operation == "check" else (NEUTRAL_NOTICE + "\n").encode()
        log_ref = add_remote(log, raw_log)
        seconds = TIMES[int(PurePosixPath(log).stem.split("-")[-1])] if "/sample-" in log else 0.001
        process = {"argv": argv, "returncode": 0, "seconds": seconds, "timed_out": False, "log": log}
        process_ref = add_remote(log + ".json", json_bytes(process))
        proof = {
            **context, "schema": "hpc-forest-matrix15-qualification-command-execution-v1",
            "verified": True, "context": context_ref, "source_after": source, "binary_after": binary_ref,
            "argument_files_after": after, "returncode": 0, "timed_out": False, "measured_seconds": seconds,
            "original_process_result": process_ref, "hashing_outside_measured_interval": True,
            "execution_semantics_changed": False,
            "streams": {"combined_stdout_stderr": log_ref, "separate_stdout": None, "separate_stderr": None,
                        "layout": "original_run_process_combined_unchanged"},
            "case_execution_records": [], "individual_case_provenance_verified": False,
            "independent_raw_stdout_per_candidate_verified": False, "independent_performance_audit_verified": False,
        }
        proof_ref = add_remote(log + ".command-stream.json", json_bytes(proof))
        summaries.append({**proof_ref, "mode": "command-stream-v1", "operation": operation, "verified": True,
                          "individual_case_provenance_verified": False, "independent_performance_audit_verified": False})
    return summaries


def registry_bytes(settings, identity, trusted_manifest, protocol_id, commit, result):
    """Create a fresh SQLite fixture in memory from our own literal SQL only."""
    connection = sqlite3.connect(":memory:")
    try:
        definitions = [
            "CREATE TABLE metadata (key TEXT, value TEXT)",
            "CREATE TABLE epochs (id INTEGER, base_commit TEXT, protocol_id TEXT, baseline_id TEXT)",
            "CREATE TABLE trees (NEUTRAL TEXT)", "CREATE TABLE trials (NEUTRAL TEXT)",
            "CREATE TABLE interactions (NEUTRAL TEXT)", "CREATE TABLE documents (NEUTRAL TEXT)",
            "CREATE TABLE slots (phase TEXT, purpose TEXT, tokens_reserved INTEGER, tokens_used INTEGER, usage_known INTEGER)",
            "CREATE TABLE evaluations (experiment_id TEXT, epoch INTEGER, phase TEXT, cache_key TEXT, payload TEXT)",
            "CREATE TABLE events (kind TEXT, payload TEXT)",
        ]
        for statement in definitions:
            connection.execute(statement)
        metadata = {"config": settings, "identity": identity, "manifest": trusted_manifest, "protocol_id": protocol_id,
                    "qualification_only": True, "current_epoch": 1, "status": "NEUTRAL fixture only",
                    "started": SHARED_STARTED, "deadline": SHARED_STARTED + MAXIMUM_SECONDS}
        connection.executemany("INSERT INTO metadata VALUES (?, ?)", [(key, canonical(value).decode()) for key, value in metadata.items()])
        connection.execute("INSERT INTO epochs VALUES (1, ?, ?, NULL)", (commit, protocol_id))
        connection.execute("INSERT INTO slots VALUES ('confirmation', 'Q15 official baseline only; zero model tokens', 0, 0, 1)")
        connection.execute("INSERT INTO events VALUES ('workspace_created', ?)",
                           (canonical({"base_commit": commit, "protocol_id": protocol_id}).decode(),))
        for key, phase in [("precheck", "qualification_precheck"), ("confirmation", "confirmation")]:
            connection.execute("INSERT INTO evaluations VALUES ('baseline-e1', 1, ?, ?, ?)",
                               (phase, result[key]["cache_key"], canonical(result[key]).decode()))
        connection.commit()
        return connection.serialize()
    finally:
        connection.close()


def add_subject(files, subject, package, plan, config):
    row = plan["subjects"][subject]
    commit, tree = add_git_baseline(files, subject, read_inventory(package / row["source"]))
    policy = policy_for(subject, config, plan)
    settings = json.loads((package / row["config"]).read_bytes())
    settings.update(codex={"transport": "codex-mailbox", "model": None},
                    target_id=f"romeo:slurm-{JOB_ID}:Q15-baseline-cpu4", execution_provenance=policy,
                    compiler={"path": "/NEUTRAL/compiler", "sha256": sha256(NEUTRAL_NOTICE.encode()), "flavor": NEUTRAL_NOTICE})
    trusted = read_inventory(package / row["validation"])
    trusted.update({"config.json": json_bytes(settings), "result-schema.json": b"{}\n"})
    files.update({f"{subject}/trusted/{name}": raw for name, raw in trusted.items()})
    trusted_manifest = {name: sha256(raw) for name, raw in trusted.items()}
    identity = {"machine": "aarch64", "python_executable": "/NEUTRAL/python3", "NEUTRAL": NEUTRAL_NOTICE}
    protocol_id = sha256(canonical({"protocol": settings["protocol"], "manifest": trusted_manifest, "target": identity}))
    cache_key = sha256(canonical({"tree": tree, "protocol": protocol_id, "epoch": 1}))
    binary_raw = neutral_binary()
    common = {"commit": commit, "tree_hash": tree, "binary_sha256": sha256(binary_raw), "correct": True,
              "reason": NEUTRAL_NOTICE, "cache_key": cache_key}
    precheck = {**common, "status": "development_valid", "times": [], "mean_seconds": None, "score": None,
                "logs": log_paths(subject, "search", settings["protocol"]["warmups"])}
    confirmation = {**common, "status": "valid", "times": list(TIMES), "mean_seconds": statistics.mean(TIMES), "score": 0.5,
                    "logs": log_paths(subject, "confirmation", settings["protocol"]["warmups"])}
    result = {"baseline_qualified": True, "policy": policy, "protocol_id": protocol_id, "precheck": precheck,
              "confirmation": confirmation, "r1_contract_sha256": row["r1_contract_sha256"], "case_counts": row["case_counts"],
              "costs": {"slots": 1, "tokens_used": 0, "tokens_reserved": 0, "unknown_usage_calls": 0,
                        "bounded_usage_calls": 0, "exact_tokens_used": 0}}
    result["precheck_command_streams"] = add_commands(files, subject, "search", settings, identity, policy, protocol_id, precheck, binary_raw)
    result["confirmation_command_streams"] = add_commands(files, subject, "confirmation", settings, identity, policy, protocol_id, confirmation, binary_raw)
    files[subject + "/registry.sqlite3"] = registry_bytes(settings, identity, trusted_manifest, protocol_id, commit, result)
    return result


def archive_bytes(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(files.items()):
            member = tarfile.TarInfo("output/" + name)
            member.size = len(raw)
            member.mode = 0o600
            member.mtime = 0
            archive.addfile(member, io.BytesIO(raw))
    return stream.getvalue()


def transfer_wrapper(remote, local, raw):
    checksum = sha256(raw)
    return {"isError": False, "structuredContent": {"ok": True, "verifie": True, "downloaded": remote,
            "to": str(local), "bytes": len(raw), "remote_sha256": checksum,
            "empreinte_locale": checksum, "empreinte_distante": checksum}, "NEUTRAL": NEUTRAL_NOTICE}


def build_fixture(directory, package_directory, preparation_path=None, source_archive_path=None):
    """Return pinned input paths for an explicitly NEUTRAL full-reader test.

    The supplied directory must be fresh test storage named NEUTRAL. The prepared
    package and its original source tar are read as data and are never modified.
    """
    root = Path(directory).resolve(strict=True)
    package = Path(package_directory).resolve(strict=True)
    if "NEUTRAL" not in root.name or any(root.iterdir()):
        raise ValueError("An empty explicitly NEUTRAL test directory is required")
    preparation = Path(preparation_path).resolve(strict=True) if preparation_path else package.parent / "PREPARATION-Q15.json"
    source_archive = Path(source_archive_path).resolve(strict=True) if source_archive_path else package.parent / "HPC-Forest-Q15-baseline-source-r1.tar.gz"
    config = {
        "schema": "hpc-forest-Q15-baseline-cold-reception-input-v1", "evidence_origin": "NEUTRAL",
        "job_id": JOB_ID, "remote_output_root": REMOTE_OUTPUT, "remote_package_root": REMOTE_PACKAGE,
        "maximum_seconds": MAXIMUM_SECONDS, "package_directory": str(package), "reception_directory": str(root / "NEUTRAL-reception"),
        "source_preparation": local_reference(preparation), "source_archive": local_reference(source_archive),
        "source_plan": local_reference(package / "PLAN-Q15.json"),
        "source_manifest": local_reference(package / "PACKAGE-MANIFEST.json"),
    }
    plan = json.loads((package / "PLAN-Q15.json").read_bytes())
    files = {}
    subjects = {subject: add_subject(files, subject, package, plan, config) for subject in plan["subject_order"]}
    allocation = {"job_id": JOB_ID, "nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0,
                  "affinity_cpu_ids": [0, 1, 2, 3], "machine": "aarch64", "observed_utc": "2026-10-19T00:00:00+00:00"}
    plan_ref = {"path": REMOTE_PACKAGE + "/PLAN-Q15.json", "sha256": config["source_plan"]["sha256"]}
    result = {
        "schema": "hpc-forest-matrix15-baseline-qualification-result-v1", "scope_id": SCOPE,
        "source_bindings": plan["source_bindings"], "qualification_complete": True,
        "qualified_subjects": plan["subject_order"], "subjects": subjects, "allocation": allocation,
        "plan": plan_ref, "elapsed_seconds": 1, "native_authorization": False, "native_model_calls": 0,
        "Controller_instances": 0, "Mother_instances": 0, "native_workers_started": 0,
        "individual_case_provenance_verified": False, "independent_raw_stdout_per_candidate_verified": False,
        "independent_performance_audit_verified": False, "scientific_gain_claimed": False,
        "old_candidates_or_reference_binaries_imported": False,
    }
    intent = {"schema": "hpc-forest-matrix15-baseline-qualification-intent-v1", "scope_id": SCOPE,
              "allocation": allocation, "attempt": 1, "retry": False, "maximum_seconds": MAXIMUM_SECONDS,
              "plan": plan_ref, "native_authorization": False, "native_model_calls": 0}
    files["RESULT-Q15.json"], files["INTENT-ONE-Q15.json"] = json_bytes(result), json_bytes(intent)
    files["OUTPUT-MANIFEST.json"] = json_bytes({"schema": "hpc-forest-matrix15-Q-private-output-files-v1",
                                               "files": {name: sha256(raw) for name, raw in files.items()}})
    def write(name, raw):
        path = root / name
        with path.open("xb") as handle:
            handle.write(raw)
        return path
    archive = archive_bytes(files)
    archive_path = write("NEUTRAL-output.tar.gz", archive)
    announcement = json_bytes({"schema": "hpc-forest-matrix15-Q-archive-v1", "path": REMOTE_OUTPUT + ".tar.gz",
                               "sha256": sha256(archive), "private_audit_only_never_model_context": True, "native_model_calls": 0})
    announcement_path = write("NEUTRAL-archive-announcement.json", announcement)
    common = {"ok": True, "job_id": JOB_ID, "state": "COMPLETED", "exit_code": "0:0"}
    status = {"isError": False, "NEUTRAL": NEUTRAL_NOTICE, "structuredContent": {**common, "finished": True,
              "scheduler_completed": True, "scheduler_success_observed": True,
              "observation": {"source": "slurm", "current_state_observed": True, "observed_at": 1}}}
    efficiency = {"isError": False, "NEUTRAL": NEUTRAL_NOTICE, "structuredContent": {**common,
                  "found": True, "alloc_cpus": 4, "alloc_gpus": 0, "req_mem_mb": 16384}}
    config.update(output_archive=local_reference(archive_path), archive_announcement=local_reference(announcement_path))
    for name, value in {
        "archive_transfer": transfer_wrapper(REMOTE_OUTPUT + ".tar.gz", archive_path, archive),
        "announcement_transfer": transfer_wrapper(REMOTE_OUTPUT + "-archive.json", announcement_path, announcement),
        "status": status, "efficiency": efficiency,
    }.items():
        config[name] = local_reference(write("NEUTRAL-" + name + ".json", json_bytes(value)))
    input_path = write("NEUTRAL-input.json", json_bytes(config))
    return {"input_path": input_path, "input_sha256": sha256(input_path.read_bytes()),
            "reception_directory": Path(config["reception_directory"]), "archive_path": archive_path,
            "subject_count": len(subjects), "archive_members": len(files), "NEUTRAL": True}


def reseal_fixture(prepared, transform_files):
    """Mutate NEUTRAL data and rebuild every enclosing integrity observation.

    This tests semantic rejection after intact transport and archive manifests.
    It never changes origin to received and never invokes the production reader.
    The caller's transform receives an in-memory relative-name/bytes dictionary.
    """
    input_path = Path(prepared["input_path"])
    config = json.loads(input_path.read_bytes())
    if config["evidence_origin"] != "NEUTRAL" or not prepared.get("NEUTRAL"):
        raise ValueError("Only an explicitly NEUTRAL fixture may be resealed")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(Path(prepared["archive_path"]).read_bytes()), mode="r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.parts[0] != "output" or len(path.parts) < 2:
                raise ValueError("Unexpected member in our NEUTRAL fixture")
            name = path.relative_to("output").as_posix()
            if name in files:
                raise ValueError("Duplicate member in our NEUTRAL fixture")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable NEUTRAL member")
            files[name] = stream.read()
    files.pop("OUTPUT-MANIFEST.json")
    transform_files(files)
    if any(type(raw) is not bytes for raw in files.values()):
        raise ValueError("Fixture transformations must leave byte payloads")
    files["OUTPUT-MANIFEST.json"] = json_bytes({"schema": "hpc-forest-matrix15-Q-private-output-files-v1",
                                               "files": {name: sha256(raw) for name, raw in files.items()}})
    archive = archive_bytes(files)
    archive_path = Path(prepared["archive_path"])
    archive_path.write_bytes(archive)
    announcement_path = Path(config["archive_announcement"]["path"])
    announcement = json_bytes({"schema": "hpc-forest-matrix15-Q-archive-v1", "path": REMOTE_OUTPUT + ".tar.gz",
                               "sha256": sha256(archive), "private_audit_only_never_model_context": True, "native_model_calls": 0})
    announcement_path.write_bytes(announcement)
    for name, value in {
        "archive_transfer": transfer_wrapper(REMOTE_OUTPUT + ".tar.gz", archive_path, archive),
        "announcement_transfer": transfer_wrapper(REMOTE_OUTPUT + "-archive.json", announcement_path, announcement),
    }.items():
        path = Path(config[name]["path"])
        path.write_bytes(json_bytes(value))
        config[name] = local_reference(path)
    config.update(output_archive=local_reference(archive_path), archive_announcement=local_reference(announcement_path))
    input_path.write_bytes(json_bytes(config))
    prepared.update(input_sha256=sha256(input_path.read_bytes()), archive_members=len(files))
    return prepared
