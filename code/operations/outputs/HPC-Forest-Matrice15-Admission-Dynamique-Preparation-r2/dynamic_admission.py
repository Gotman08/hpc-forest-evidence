"""Prepare and assemble observed matrix15 admissions; never start jobs or models."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
PROJECT = BASE / "work/matrix15-admission-no-cycle-r2/project"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT / "src"))
from hpc_forest import codex_process as cp  # noqa: E402
from hpc_forest import matrix15_contract as contract  # noqa: E402
from hpc_forest import native_matrix15 as native  # noqa: E402
from hpc_forest.core import InfrastructureError  # noqa: E402

FIRST_CELL = "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23"
STATIC_KEYS = {"plan", "source_zip", "runtime_manifest", "preparation_manifest", "r1_contracts",
               "harness", "artifact_aliases", "primes_release"}
INPUT_SCHEMA = "hpc-forest-matrix15-dynamic-input-v1"
ARM_SCHEMA = "hpc-forest-matrix15-real-zero-model-observation-v1"
MARKER_SCHEMA = "hpc-forest-matrix15-zero-model-allocation-marker-v1"
OBS_SCHEMA = "hpc-forest-primary-tool-observation-v1"
TOOLS = {"mcp__romeo__upload_to_romeo", "mcp__romeo__download_from_romeo",
         "mcp__romeo__read_remote_file", "mcp__romeo__job_prepare", "mcp__romeo__plan_get",
         "mcp__romeo__job_status", "mcp__romeo__job_efficiency"}


def need(condition, message):
    if not condition:
        raise InfrastructureError(message)


def raw_json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ordinary(path, *, exists=True):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts
         and not any(part.is_symlink() or getattr(part, "is_junction", lambda: False)()
                     for part in (path, *path.parents)), "Physical absolute path required")
    if exists:
        need(path.is_file(), "Required input file is absent")
    return path


def read(path):
    return native.read_json(ordinary(path))


def reference(path):
    path = ordinary(path)
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def verified_ref(ref):
    need(contract.reference(ref), "Exact path/SHA reference required")
    path = ordinary(ref["path"])
    need(sha(path.read_bytes()) == ref["sha256"], "Referenced evidence bytes changed")
    return path


def create(path, value):
    path = ordinary(Path(path).resolve(), exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(value if isinstance(value, bytes) else raw_json(value))
        target.flush()
        os.fsync(target.fileno())
    return reference(path)


def reject_fixture(value):
    """Operational paths have no fixture override, even when tests call the assembler."""
    if isinstance(value, dict):
        need(value.get("verified") is not False,
             "An explicitly negative receipt cannot be promoted to operational evidence")
        need(not any(value.get(key) is True for key in ("synthetic", "prepared", "test_only", "fixture", "neutral")),
             "Prepared/synthetic data is not operational evidence")
        for item in value.values():
            reject_fixture(item)
    elif isinstance(value, list):
        for item in value:
            reject_fixture(item)
    elif isinstance(value, str):
        need(not any(word in value.casefold() for word in ("neutral", "not-an-admission", "fixture")),
             "Fixture data cannot be promoted to operational admission")


def fresh(observed, now, maximum=600):
    need(type(now) in (int, float) and type(observed) in (int, float)
         and 0 <= now - observed <= maximum, "Observation stale, future or untyped")


def admission_clock(marker, now):
    fresh(marker["observed_at"], now)
    need(type(marker.get("admission_started_at")) in (int, float)
         and marker["admission_started_at"] <= marker["observed_at"] <= now
         and now < marker["admission_started_at"] + 600
         and type(marker.get("allocation_outer_deadline")) in (int, float)
         and marker["admission_started_at"] < marker["allocation_outer_deadline"],
         "Initial admission must remain inside the immutable bootstrap's 600-second window")


def authorization_clock(marker, expires_at, now):
    need(type(expires_at) in (int, float)
         and now < expires_at <= min(marker["admission_started_at"] + 3300,
                                     marker["allocation_outer_deadline"], native.DEADLINE),
         "Authorization must expire within the immutable allocation envelope, not the initial admission window")


def load_runtime():
    revision = read(BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json")
    native.verify_runtime(verified_ref(revision["source_zip"]), verified_ref(revision["runtime_manifest"]))
    return revision


def filesystem_metadata(roots):
    """Inspect directory entries and SKILL.md metadata; never open instruction bodies."""
    entries, candidates, skipped = [], set(), []
    pending = [(ordinary(Path(root).resolve(), exists=False), 0) for root in roots]
    while pending:
        root, depth = pending.pop()
        if not root.exists():
            entries.append({"path": str(root), "exists": False})
            continue
        need(depth <= 16 and len(entries) < 100000, "Bounded metadata scan exceeded")
        need(root.is_dir(), "Skill candidate scan root is not a directory")
        with os.scandir(root) as listing:
            children = sorted(list(listing), key=lambda item: item.name.casefold())
        for entry in children:
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            linked = entry.is_symlink() or getattr(path, "is_junction", lambda: False)()
            entries.append({"path": str(path), "directory": entry.is_dir(follow_symlinks=False),
                            "linked": linked, "size": info.st_size, "mtime_ns": info.st_mtime_ns})
            if linked:
                skipped.append(str(path))
            elif entry.name == "SKILL.md" and entry.is_file(follow_symlinks=False):
                candidates.add(str(root))
            elif entry.is_dir(follow_symlinks=False) and entry.name not in {".git", ".venv", "__pycache__"}:
                pending.append((path, depth + 1))
    need(0 < len(candidates) <= 512, "No bounded explicit skill candidate inventory")
    return {"schema": "hpc-forest-skill-paths-filesystem-only-candidates-v1", "roots": list(map(str, roots)),
            "entries": entries, "skill_candidate_directories": sorted(candidates), "skipped_links": skipped,
            "instruction_or_SKILL_body_read": False, "is_actual_CLI_discovery_receipt": False}


def probe_cli(executable, roots, output):
    """The only CLI calls are immutable --version and login status probes."""
    need(os.name == "nt", "CLI observation requires its actual Windows host")
    output = Path(output).resolve()
    need(not output.exists(), "Observation output already exists")
    output.mkdir(parents=True)
    executable = ordinary(Path(executable).resolve())
    files = {name: reference(executable.parent / name) for name in native.CLI_FILES}
    need({name: ref["sha256"] for name, ref in files.items()} == native.CLI_FILES, "Pinned four CLI binaries differ")
    need(executable.name == "codex.exe" and reference(executable) == files["codex.exe"],
         "Only the exact pinned codex.exe may receive the two read-only probes")
    probes = {}
    for name, tail in (("version", ["--version"]), ("authentication", ["login", "status"])):
        started = time.time()
        completed = subprocess.run([str(executable), *tail], capture_output=True, timeout=30, check=False)
        stdout = create(output / (name + ".stdout"), completed.stdout)
        stderr = create(output / (name + ".stderr"), completed.stderr)
        probes[name] = create(output / (name + ".json"), {"argv": [str(executable), *tail],
            "started_at": started, "finished_at": time.time(), "returncode": completed.returncode,
            "stdout": stdout, "stderr": stderr})
    metadata = create(output / "filesystem-metadata.json", filesystem_metadata(roots))
    observation = {"schema": "hpc-forest-matrix15-cli-readonly-observation-v1", "observed_at": time.time(),
                   "executable": str(executable), "files": files, "probes": probes, "filesystem_metadata": metadata,
                   "native_model_calls": 0}
    result = create(output / "CLI-OBSERVATION.json", observation)
    validate_cli_observation(result, now=time.time())
    return result


def validate_cli_observation(ref, *, now):
    value = read(verified_ref(ref))
    reject_fixture(value)
    need(value.get("schema") == "hpc-forest-matrix15-cli-readonly-observation-v1"
         and type(value.get("native_model_calls")) is int and value["native_model_calls"] == 0,
         "Actual read-only CLI observation required")
    fresh(value["observed_at"], now)
    need(set(value["files"]) == set(native.CLI_FILES), "Four CLI binary observations required")
    for name, expected in native.CLI_FILES.items():
        need(value["files"][name]["sha256"] == expected, "CLI binary pin changed")
        verified_ref(value["files"][name])
    for name, tail in (("version", ["--version"]), ("authentication", ["login", "status"])):
        probe = read(verified_ref(value["probes"][name]))
        need(probe["argv"] == [value["executable"], *tail] and probe["returncode"] == 0
             and 0 <= probe["finished_at"] - probe["started_at"] <= 35, "CLI readonly probe failed/changed")
        stdout = verified_ref(probe["stdout"]).read_text(encoding="utf8").strip()
        stderr = verified_ref(probe["stderr"]).read_text(encoding="utf8").strip()
        need(stdout == "codex-cli 0.163.0-alpha.10.2" if name == "version" else
             "Logged in using ChatGPT" in stdout + stderr, "CLI version or existing authentication differs")
    metadata = read(verified_ref(value["filesystem_metadata"]))
    need(metadata.get("instruction_or_SKILL_body_read") is False
         and metadata.get("is_actual_CLI_discovery_receipt") is False
         and 0 < len(metadata["skill_candidate_directories"]) <= 512, "Filesystem-only CLI metadata required")
    return value, metadata


def pointer(value, path):
    need(isinstance(path, list) and path, "Explicit raw structured-content path required")
    for item in path:
        need(type(item) in (str, int), "Typed structured-content pointer required")
        value = value[item]
    return value


def primary(claim, expected, *, tools):
    """Metadata lookup only; operational ARM facts use tool-specific decoders below."""
    value = read(verified_ref(claim["raw"]))
    reject_fixture(value)
    need(value.get("schema") == OBS_SCHEMA and value.get("tool") in tools
         and value["tool"] in TOOLS and isinstance(value.get("arguments"), dict), "Actual named primary MCP observation required")
    need(value["response"].get("isError") is not True
         and value["response"].get("structuredContent", {}).get("ok") is not False,
         "Errored MCP observation cannot prove a fact")
    need(pointer(value["response"], claim["pointer"]) == expected, "Primary structuredContent contradicts projected observation")
    return claim["raw"]


def mcp_observation(ref, tool, *, now):
    value = read(verified_ref(ref))
    reject_fixture(value)
    need(value.get("schema") == OBS_SCHEMA and value.get("tool") == tool
         and isinstance(value.get("arguments"), dict), "Exact primary MCP tool required")
    fresh(value["observed_at"], now)
    response = value["response"]
    need(isinstance(response, dict) and response.get("isError") is not True, "MCP tool reported an error")
    payload = response.get("structuredContent")
    if payload is None:
        blocks = response.get("content")
        need(isinstance(blocks, list) and len(blocks) == 1 and blocks[0].get("type") == "text",
             "One complete structured MCP result is required")
        payload = json.loads(blocks[0]["text"])
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    need(isinstance(payload, dict) and payload.get("ok") is True and not payload.get("error"),
         "MCP payload is not a successful observation")
    return value["arguments"], payload


def check_arm(ref, binding, static_refs, qualification_ref, *, now):
    value = read(verified_ref(ref))
    reject_fixture(value)
    need(value.get("schema") == ARM_SCHEMA and value.get("binding") == binding, "Actual ARM job/source/plan binding required")
    fresh(value["observed_at"], now)
    marker_path = verified_ref(value["marker"])
    marker = read(marker_path)
    reject_fixture(marker)
    need(marker.get("schema") == MARKER_SCHEMA and marker.get("binding") == binding
         and type(marker.get("native_model_calls")) is int and marker["native_model_calls"] == 0,
         "Actual zero-model allocation marker missing")
    admission_clock(marker, now)
    need(marker.get("admission_root") == binding["remote_root"] + "-admission",
         "Zero-model marker must be written in the separate admission sibling")
    output_root = binding["remote_root"] + "/results-" + binding["job_id"]
    need(marker.get("scientific_paths") == {"root": binding["remote_root"], "mailbox": output_root + "/mailbox",
         "registry": output_root + "/" + binding["subject_id"] + "/registry.sqlite3"},
         "Absence observations must name the runner's exact scientific targets")
    allocation = marker["allocation"]
    need(allocation.get("job_id") == binding["job_id"] and allocation.get("architecture") in {"aarch64", "arm64"}
         and all(type(allocation.get(key)) is int and allocation[key] == expected for key, expected in
                 {"nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0,
                  "affinity_cpu_count": 4}.items()), "Actual runtime allocation guard is not the native target")
    need(all(marker.get(key) is True for key in ("source_runtime_verified", "scientific_root_observed_absent",
            "scientific_mailbox_observed_absent", "scientific_registry_observed_absent")),
         "Source and unused scientific target paths must be observed before runner creation")
    evidence = [ref, value["marker"]]
    marker_remote = binding["remote_root"] + "-admission/ZERO-MODEL-MARKER.json"
    arguments, payload = mcp_observation(value["marker_readback"], "mcp__romeo__read_remote_file", now=now)
    total_lines = payload.get("total_lines")
    need((type(total_lines) is int and total_lines >= 1)
         or (type(total_lines) is str and re.fullmatch(r"[1-9][0-9]*", total_lines)),
         "Readback total_lines must be a positive integer or canonical decimal string")
    need(arguments.get("path") == marker_remote and arguments.get("offset", 1) == 1
         and payload.get("path") == marker_remote and payload.get("offset") == 1
         and payload.get("truncated") is False and type(payload.get("limit")) is int
         and 1 <= int(total_lines) <= payload["limit"]
         and payload.get("content") == marker_path.read_text(encoding="utf8"),
         "Whole exact allocation marker readback required")
    evidence.append(value["marker_readback"])
    arguments, payload = mcp_observation(value["job_id_observation"], "mcp__romeo__job_status", now=now)
    need(arguments.get("job_id") == binding["job_id"] and payload.get("job_id") == binding["job_id"]
         and payload.get("state") == "RUNNING" and payload.get("finished") is False,
         "Fresh RUNNING observation of the exact allocation required")
    evidence.append(value["job_id_observation"])
    needed = dict(static_refs)
    needed["subject_qualification"] = qualification_ref
    need(set(value["transfers"]) == set(needed), "Exact source/plan/preparation/Q transfer census required")
    for key, local in needed.items():
        transfer = value["transfers"][key]
        verified_ref(local)
        need(transfer["local"] == local and transfer["sha256"] == local["sha256"]
             and transfer["bytes"] == Path(local["path"]).stat().st_size
             and isinstance(transfer["remote_path"], str) and transfer["remote_path"].startswith("/")
             and ".." not in transfer["remote_path"].split("/"), "Transport path/bytes/SHA differ")
        tool = read(verified_ref(transfer["raw"]))["tool"]
        need(tool in {"mcp__romeo__upload_to_romeo", "mcp__romeo__download_from_romeo"}, "Only exact SCP file tools prove transfer")
        arguments, payload = mcp_observation(transfer["raw"], tool, now=now)
        if tool == "mcp__romeo__upload_to_romeo":
            direction_matches = (arguments.get("local_path") == local["path"] and payload.get("sent") == local["path"]
                                 and payload.get("to") == transfer["remote_path"])
        else:
            readback = transfer["readback"]
            downloaded = verified_ref(readback)
            direction_matches = (readback["sha256"] == local["sha256"] and downloaded.stat().st_size == transfer["bytes"]
                and arguments.get("local_path") == readback["path"] and payload.get("to") == readback["path"]
                and payload.get("downloaded") == transfer["remote_path"] and arguments.get("recursive", False) is False)
            evidence.append(readback)
        need(direction_matches and arguments.get("remote_path") == transfer["remote_path"]
             and arguments.get("verify", True) is True and payload.get("transport") == "scp"
             and payload.get("verifie") is True and type(payload.get("bytes")) is int
             and payload["bytes"] == transfer["bytes"] and payload.get("empreinte_locale") == local["sha256"]
             and payload.get("empreinte_distante") == local["sha256"]
             and ("remote_sha256" not in payload or payload["remote_sha256"] == local["sha256"]),
             "One successful exact SCP receipt must prove path, bytes and both hashes together")
        evidence.append(transfer["raw"])
    return value, marker, evidence


def proof(binding, kind, extra, evidence, *, checks):
    verified = bool(checks) and all(item is True for item in checks)
    need(verified, "Unproved dynamic admission: " + kind)
    unique_evidence = list({(ref["path"], ref["sha256"]): ref for ref in evidence}.values())
    return {**binding, "schema": "hpc-forest-matrix15-" + kind.replace("_", "-") + "-v1",
            "verified": verified, "evidence_refs": unique_evidence, **extra}


def template():
    return {"schema": INPUT_SCHEMA, "mode": "PREPARE", "cell_key": FIRST_CELL,
        "statics": None, "statics_arm": None, "subject_qualification": None, "subject_reception": None,
        "cli_observation": None, "arm_observation": None, "integration_review": None,
        "user_instructions": None, "job_id": None, "remote_root": None,
        "windows_cache": None, "output_windows": None,
        "output_arm": None, "capacity_lock": None, "capacity_registry": None,
        "capacity_evidence": None, "expires_at": None, "codex_config": None}


def worker_template():
    return ["{python}", "-B", "-m", "hpc_forest.matrix15_worker", "--dependency-receipt", "{authorization}",
        "--session-id", "{session_id}", "--required-jobs", contract.SCOPE, "--executable", "{executable}",
        "--channel", "{channel}", "--output", "{cache}", "--cli-policy", "{policy}", "--cli-policy-sha256", "{policy_sha256}",
        "--max-seconds", "2000", "--poll-seconds", "2", "--codex-config", "{codex_config}"]


def static_inputs(ref):
    value = read(verified_ref(ref))
    reject_fixture(value)
    need(value.get("schema") == "hpc-forest-matrix15-native-static-package-v1"
         and set(value.get("artifacts", {})) == STATIC_KEYS, "Exact static package required")
    refs = value["artifacts"]
    for artifact in refs.values():
        verified_ref(artifact)
    plan = contract.validate_plan(read(verified_ref(refs["plan"])))
    aliases = native.validate_aliases(read(verified_ref(refs["artifact_aliases"])), refs["source_zip"]["sha256"])
    native.verify_runtime(verified_ref(refs["source_zip"]), verified_ref(refs["runtime_manifest"]))
    need(plan["source_zip_sha256"] == refs["source_zip"]["sha256"]
         and all(plan[key]["sha256"] == refs[key]["sha256"] for key in
                 ("runtime_manifest", "preparation_manifest", "r1_contracts", "harness", "artifact_aliases")),
         "Static plan/source/preparation pins differ")
    native.verify_primes_release(verified_ref(refs["primes_release"]), lambda ref: native.artifact(ref, aliases=aliases))
    return refs, plan, aliases


def build_policy(output, binding, observation_ref, *, now):
    observation, metadata = validate_cli_observation(observation_ref, now=now)
    policy = {**binding, "schema": cp.TASK_CLI_POLICY_SCHEMA,
        "cli_executable_sha256": native.CLI_FILES["codex.exe"],
        "code_mode_host_executable_sha256": cp.CODE_MODE_HOST_SHA256,
        "skill_candidate_directories": metadata["skill_candidate_directories"],
        "filesystem_metadata_sha256": observation["filesystem_metadata"]["sha256"],
        "is_actual_CLI_discovery_receipt": metadata["is_actual_CLI_discovery_receipt"],
        "instruction_or_SKILL_body_read": metadata["instruction_or_SKILL_body_read"],
        "cli_feature_overrides": dict(cp.TASK_CLI_FEATURES)}
    ref = create(output / ("cli-policy-" + binding["session_id"] + ".json"), policy)
    cp.load_task_cli_policy(Path(ref["path"]), ref["sha256"], binding, native.CLI_FILES["codex.exe"])
    return ref, observation


def review_input(ref, binding, required_refs):
    value = read(verified_ref(ref))
    reject_fixture(value)
    need(value.get("schema") == "hpc-forest-matrix15-observed-integration-review-v1"
         and value.get("source_zip_sha256") == binding["source_zip_sha256"]
         and value.get("plan_sha256") == binding["plan_sha256"]
         and value.get("blocking_findings") == [] and value.get("neutral_tests_passed") is True
         and isinstance(value.get("reviewer"), str) and bool(value["reviewer"])
         and value.get("worker_argv_template") == worker_template(), "Actual source/plan/closed-command integration review required")
    for file_ref in value["reviewed_files"]:
        verified_ref(file_ref)
    need({(item["path"], item["sha256"]) for item in value["reviewed_files"]}
         == {(item["path"], item["sha256"]) for item in required_refs},
         "Integration review requires exactly source/plan/producer/helper; private policy stays local")
    return value


def arm_projection(output, remote_root, authorization, arm, aliases, public_cli_ref, public_review_ref):
    """Prepare host documents locally; ROOT transfers and validates them on ARM."""
    need(remote_root == authorization["remote_root"] + "-admission",
         "ARM dynamic documents belong to the separate exact admission sibling")
    stage = output / "arm-stage"
    stage.mkdir()
    exported, members = {}, []
    def emit(name, raw):
        local = create(stage / name, raw)
        remote = {"path": remote_root.rstrip("/") + "/" + name, "sha256": local["sha256"]}
        members.append({"local": local, "remote": remote, "bytes": Path(local["path"]).stat().st_size})
        return remote
    def leaf(ref):
        verified_ref(ref)
        key = (ref["path"], ref["sha256"])
        if key in exported:
            return exported[key]
        alias = native.alias_reference(ref, aliases, platform="arm")
        if alias["path"] != ref["path"]:
            return alias
        remote = emit("evidence-" + ref["sha256"] + Path(ref["path"]).suffix,
                      Path(ref["path"]).read_bytes())
        exported[key] = remote
        return remote
    original = authorization["artifacts"]
    refs = {key: {"path": arm["transfers"][key]["remote_path"], "sha256": original[key]["sha256"]}
            for key in STATIC_KEYS}
    # Qualification bytes are immutable. Its inner evidence must already have
    # static aliases; this check prevents silently rewriting a received receipt.
    qualification = read(verified_ref(original["subject_qualification"]))
    for ref in qualification["evidence_refs"]:
        need(native.alias_reference(ref, aliases, platform="arm")["path"] != ref["path"]
             or str(ref["path"]).startswith("/"), "Qualification evidence lacks a pre-plan ARM alias")
    refs["subject_qualification"] = emit("subject_qualification.json",
        verified_ref(original["subject_qualification"]).read_bytes())
    reception = read(verified_ref(original["subject_reception"]))
    reception.update(qualification=refs["subject_qualification"], archive=leaf(reception["archive"]),
                     audit=leaf(reception["audit"]), evidence_refs=[leaf(ref) for ref in reception["evidence_refs"]])
    refs["subject_reception"] = emit("subject_reception.json", raw_json(reception))
    lane = read(verified_ref(original["worker_lane_admission"]))
    lane.update(minimal_owned_observations=leaf(lane["minimal_owned_observations"]),
                slot_reservation=leaf(lane["slot_reservation"]))
    refs["worker_lane_admission"] = emit("worker_lane_admission.json", raw_json(lane))
    for kind in native.PROOF_FIELDS:
        value = read(verified_ref(original[kind]))
        value["evidence_refs"] = ([leaf(public_cli_ref)] if kind == "cli_identity" else
                                 [leaf(public_review_ref)] if kind == "integration_review" else
                                 [leaf(ref) for ref in value["evidence_refs"]])
        if kind == "integration_review":
            value["reviewed_files"] = [leaf(ref) for ref in value["reviewed_files"]]
        if kind == "transport_admission":
            continue  # cli_identity hash is a host-specific downstream dependency.
        refs[kind] = emit(kind + ".json", raw_json(value))
    transport = read(verified_ref(original["transport_admission"]))
    transport.update(evidence_refs=[leaf(ref) for ref in transport["evidence_refs"]],
                     cli_identity_sha256=refs["cli_identity"]["sha256"])
    refs["transport_admission"] = emit("transport_admission.json", raw_json(transport))
    projected = {**authorization, "artifacts": refs}
    auth = emit("authorization.json", raw_json(projected))
    emit("authorization.sha256.json", raw_json({"sha256": auth["sha256"],
        "bytes": len(raw_json(projected)), "authorization": auth["path"]}))
    return create(output / "ARM-TRANSFER-PENDING.json", {
        "schema": "hpc-forest-matrix15-arm-dynamic-transfer-preparation-v1", "verified": False,
        "authorization": auth, "members": members, "source_authorization": reference(output / "authorization.json"),
        "remote_runtime_validation_required": True, "raw_private_census_exported": False,
        "private_cli_metadata_exported": False, "native_model_calls": 0})


def assemble(input_ref, *, now=None):
    """Only real complete inputs can create operational documents; capacity is last."""
    from capacity import exclusive_capacity

    revision = load_runtime()
    inputs = read(verified_ref(input_ref))
    reject_fixture(inputs)
    need(set(inputs) == set(template()) and inputs.get("schema") == INPUT_SCHEMA
         and inputs.get("mode") == "ASSEMBLE" and inputs.get("cell_key") == FIRST_CELL
         and all(value is not None for value in inputs.values()), "PREPARE/missing inputs cannot create an authorization")
    current = time.time() if now is None else now
    need(now is None, "Operational clock cannot be overridden")
    refs, plan, aliases = static_inputs(inputs["statics"])
    arm_static_refs = read(verified_ref(inputs["statics_arm"]))
    need(set(arm_static_refs) == STATIC_KEYS and all(contract.reference(arm_static_refs[key])
         and arm_static_refs[key]["sha256"] == refs[key]["sha256"] for key in STATIC_KEYS),
         "Exact matching static ARM path projection required")
    for key in STATIC_KEYS - {"plan", "artifact_aliases"}:
        need(native.alias_reference(refs[key], aliases, platform="arm") == arm_static_refs[key],
             "ARM static target differs from its explicit pre-plan alias")
    cell = contract.validate_cell(contract.REGISTERED_CELLS[FIRST_CELL])
    authorization = {**cell, "scope_id": contract.SCOPE, "job_id": inputs["job_id"],
                     "remote_root": inputs["remote_root"], "artifacts": dict(refs)}
    need(isinstance(inputs["job_id"], str) and re.fullmatch(r"[1-9][0-9]*", inputs["job_id"])
         and inputs["remote_root"].startswith("/") and ".." not in inputs["remote_root"].split("/")
         and inputs["remote_root"].endswith(contract.SCOPE + "-" + cell["session_id"]), "Real job and fresh registered ARM root required")
    binding = native.cell_binding(authorization)
    output = ordinary(Path(inputs["output_windows"]).resolve(), exists=False)
    need(not output.exists(), "Dynamic output cannot be reused")
    output.mkdir(parents=True)
    policy_ref, cli = build_policy(output, binding, inputs["cli_observation"], now=current)
    subject = contract.resolve_subject(plan, FIRST_CELL)
    qualification_ref, reception_ref = inputs["subject_qualification"], inputs["subject_reception"]
    qualification, reception = read(verified_ref(qualification_ref)), read(verified_ref(reception_ref))
    reject_fixture(qualification)
    reject_fixture(reception)
    native.verify_qualification(qualification, reception, subject, binding, qualification_ref=qualification_ref,
        prepared=True, read_ref=lambda ref: native.artifact(ref, aliases=aliases), aliases=aliases,
        preparation_manifest=read(verified_ref(refs["preparation_manifest"])))
    arm, marker, transport_evidence = check_arm(inputs["arm_observation"], binding, refs, qualification_ref, now=current)
    need(all(arm["transfers"][key]["remote_path"] == arm_static_refs[key]["path"] for key in STATIC_KEYS),
         "Transport readback must name the static package's final shared paths")
    instructions = verified_ref(inputs["user_instructions"]).read_text(encoding="utf8").strip()
    reject_fixture({"user_instructions": instructions})
    need(instructions and "max" in instructions.casefold(), "Real human MAX instruction reference required")
    native.deadline_guard(current)
    authorization_clock(marker, inputs["expires_at"], current)
    cache = ordinary(Path(inputs["windows_cache"]).resolve(), exists=False)
    need(not cache.exists(), "The new Windows worker cache path must be absent")
    # These creations are exclusive evidence; an interruption leaves them reserved.
    cache.mkdir(parents=True)
    codex_config = ordinary(inputs["codex_config"])
    substitutions = {"python": sys.executable, "authorization": str(output / "authorization.json"),
        "session_id": cell["session_id"], "executable": cli["executable"], "channel": inputs["remote_root"] + "/results-" + inputs["job_id"] + "/mailbox",
        "cache": str(cache), "policy": policy_ref["path"], "policy_sha256": policy_ref["sha256"], "codex_config": str(codex_config)}
    command = [item.format(**substitutions) for item in worker_template()]
    command_ref = create(output / "WORKER-ARGV.json", {"argv": command, "persistent": "--once" not in command,
        "cwd": str(PROJECT), "environment": {"PYTHONPATH": str(PROJECT / "src")}})
    review = review_input(inputs["integration_review"], binding,
                          [refs["source_zip"], refs["plan"], reference(Path(__file__).resolve()),
                           reference(Path(__file__).resolve().with_name("capacity.py"))])
    evidence_refs = inputs["capacity_evidence"]
    need(isinstance(evidence_refs, dict), "Capacity evidence mapping required")
    reconciled_observation = {}
    def capacity_evidence(census_ref, analysis):
        static_roles = {"reservation_producer_review", "local_projection_producer_review", "source_only_received_closure"}
        need(set(evidence_refs) <= static_roles | {"owned_worker_receipts"} and static_roles <= set(evidence_refs),
             "Three typed capacity reviews/closure and optional ownership receipts required")
        result = {key: evidence_refs[key] for key in static_roles}
        receipts = evidence_refs.get("owned_worker_receipts", [])
        by_session = {}
        for ref in receipts:
            receipt = read(verified_ref(ref))
            need(receipt["session_id"] not in by_session, "Duplicate owned-worker receipt")
            by_session[receipt["session_id"]] = ref
        reconciled = set(by_session) == set(analysis["session_ids"])
        need(reconciled and analysis["source_only_active_workers"] == 0, "Unreconciled or source-only worker present")
        common = {**binding, "verified": reconciled, "observed_at": analysis["observed_at"],
                  "private_full_census_sha256": census_ref["sha256"], "all_native_workers_known": analysis["all_native_workers_known"]}
        result["source_only_absence"] = create(output / "source_only_absence.json", {
            **common, "schema": "hpc-forest-matrix15-source-only-absence-v1", "source_only_active_workers": analysis["source_only_active_workers"],
            "source_only_received_closure_sha256": result["source_only_received_closure"]["sha256"]})
        result["other_owned_worker_reconciliation"] = create(output / "other_owned_worker_reconciliation.json", {
            **common, "schema": "hpc-forest-matrix15-other-owned-worker-reconciliation-v1",
            "other_native_workers_count": analysis["native_workers_count"], "launcher_python_pairs_count_as_one": analysis["launcher_python_pairs_count_as_one"],
            "reconciled_session_ids": analysis["session_ids"], "owned_worker_receipts": [by_session[session] for session in analysis["session_ids"]],
            "all_workers_owned_and_reconciled": reconciled})
        reconciled_observation["all_prior_calls_reconciled"] = reconciled
        return result
    with exclusive_capacity(inputs["capacity_lock"], inputs["capacity_registry"], binding, output,
                            evidence_factory=capacity_evidence) as capacity:
        need(capacity["verified"] is True, "Fixture collector never creates operational capacity")
        observed = time.time()
        fresh(arm["observed_at"], observed)
        fresh(cli["observed_at"], observed)
        need(observed < marker["admission_started_at"] + 600
             and observed < inputs["expires_at"], "Initial bootstrap window expired during local assembly")
        paths = {**refs, "subject_qualification": qualification_ref, "subject_reception": reception_ref,
                 "worker_lane_admission": capacity["lane"]}
        extras = {
            "cli_identity": {"version": "codex-cli 0.163.0-alpha.10.2", "executable_path": cli["executable"],
                "executable_sha256": native.CLI_FILES["codex.exe"], "source_execution_allowed": False,
                "authentication": "existing-local-ChatGPT", "files": cli["files"], "observed_at": cli["observed_at"],
                "task_cli_policy_sha256": policy_ref["sha256"]},
            "integration_review": {key: review[key] for key in ("neutral_tests_passed", "blocking_findings", "reviewer",
                "reviewed_at", "limitations", "reviewed_files")},
            "cell_admission": {"human_max_only": "max" in instructions.casefold(), "one_cell_only": True,
                "automatic_extension": plan["automatic_extension"],
                "all_prior_calls_reconciled": reconciled_observation["all_prior_calls_reconciled"],
                "maximum_native_workers": plan["maximum_native_workers_total"],
                "primes_release_sha256": refs["primes_release"]["sha256"], "one_submission_only": True},
            "session_freshness": {"observed_at": observed,
                "verified_no_prior_claims": capacity["verified"] and marker["native_model_calls"] == 0
                and marker["scientific_root_observed_absent"],
                "new_cache": cache.is_dir() and not any(cache.iterdir()),
                "new_registry": marker["scientific_registry_observed_absent"],
                "new_mailbox": marker["scientific_mailbox_observed_absent"],
                "native_calls_started_at_admission": marker["native_model_calls"]}}
        extras["integration_review"]["reviewed_command_sha256"] = command_ref["sha256"]
        for kind, extra in extras.items():
            evidence = [inputs["cli_observation"], policy_ref] if kind == "cli_identity" else [
                inputs["integration_review"], command_ref] if kind == "integration_review" else [
                inputs["user_instructions"], capacity["lane"], inputs["arm_observation"]]
            paths[kind] = create(output / (kind + ".json"), proof(binding, kind, extra, evidence,
                checks=[capacity["verified"], marker["native_model_calls"] == 0]))
        paths["transport_admission"] = create(output / "transport_admission.json", proof(binding, "transport_admission", {
            "native_model_calls": marker["native_model_calls"], "normal_first_call_proved": False,
            "cli_tools_disabled": all(enabled is False for name, enabled in cp.TASK_CLI_FEATURES.items() if name != "code_mode_host"),
            "cli_identity_sha256": paths["cli_identity"]["sha256"], "subject_qualification_sha256": qualification_ref["sha256"],
            "neutral_tests_passed": review["neutral_tests_passed"]}, transport_evidence,
            checks=[marker["source_runtime_verified"], capacity["verified"]]))
        authorization.update(schema="hpc-forest-matrix15-authorization-v1", verified=capacity["verified"],
            expires_at=inputs["expires_at"], user_messages=[instructions], old_candidates_imported=False,
            operator_algorithm_advice=False, native_calls_started_at_authorization=marker["native_model_calls"], artifacts=paths)
        auth_ref = create(output / "authorization.json", authorization)
        native.validate_receipt(Path(auth_ref["path"]), {contract.SCOPE}, runtime=True, prepared=True)
        public_cli_ref = create(output / "CLI-PUBLIC-PROJECTION.json", {
            "schema": "hpc-forest-matrix15-local-cli-observation-public-projection-v1",
            "verified": capacity["verified"], "observed_at": cli["observed_at"],
            "version": extras["cli_identity"]["version"], "authentication": extras["cli_identity"]["authentication"],
            "binary_sha256": dict(native.CLI_FILES), "task_cli_policy_sha256": policy_ref["sha256"],
            "private_observation_sha256": inputs["cli_observation"]["sha256"],
            "private_skill_paths_exported": False, "native_model_calls": 0})
        public_review_ref = create(output / "REVIEW-PUBLIC-PROJECTION.json", {
            "schema": "hpc-forest-matrix15-integration-review-public-projection-v1",
            "verified": capacity["verified"], "reviewer": review["reviewer"], "source_zip_sha256": binding["source_zip_sha256"],
            "plan_sha256": binding["plan_sha256"], "private_review_sha256": inputs["integration_review"]["sha256"],
            "reviewed_command_sha256": command_ref["sha256"], "private_worker_argv_exported": False})
        arm_ref = arm_projection(output, inputs["output_arm"], authorization, arm, aliases, public_cli_ref, public_review_ref)
        create(output / "ASSEMBLAGE-VERIFIE.json", {"schema": "hpc-forest-matrix15-observed-dynamic-assembly-v1",
            "verified": capacity["verified"], "authorization": auth_ref, "policy": policy_ref,
            "worker_argv": command_ref, "arm_output_root": inputs["output_arm"], "arm_transfer_preparation": arm_ref,
            "arm_authorization_pending_transport_and_host_references": True,
            "source_revision": revision["source_zip"], "native_model_calls": 0, "jobs_submitted": 0})
        return auth_ref


def prepare(output):
    load_runtime()
    output = Path(output).resolve()
    result = create(output / "ENTREES-A-RENSEIGNER.json", template())
    create(output / "WORKER-TEMPLATE.json", {"argv": worker_template(), "persistent": True,
        "environment": {"PYTHONPATH": str(PROJECT / "src")}, "cwd": str(PROJECT)})
    create(output / "PREPARATION.json", {"schema": "hpc-forest-matrix15-dynamic-preparation-v1",
        "verified": False, "mode": "PREPARE", "inputs": result,
        "native_model_calls": 0, "jobs_submitted": 0, "capacity_observed": False,
        "missing": [key for key, value in template().items() if value is None]})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("assemble")
    p.add_argument("--input", type=Path, required=True)
    p = commands.add_parser("observe-cli")
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--skill-root", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.output)
        elif args.command == "assemble":
            result = assemble(reference(args.input.resolve()))
        else:
            result = probe_cli(args.executable, args.skill_root, args.output)
        print(json.dumps(result))
    except (InfrastructureError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"verified": False, "error": str(error)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
