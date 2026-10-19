"""Closed matrix15 admissions, independent of primes candidate/runtime modules."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from .core import InfrastructureError, digest, file_digest
from .matrix15_contract import (
    EFFORT,
    HARNESS_SHA256,
    PROTOCOL_SHA256,
    R1_CONTRACTS_SHA256,
    SCOPE,
    SUBJECTS,
    assert_r1_pair_contract,
    need,
    reference,
    resolve_subject,
    sha_value,
    validate_cell,
    validate_plan,
)
from .matrix15_lane_contract import CELL_FIELDS, unique_object, validate_lane

MAXIMUM_NATIVE_WORKERS = 4
DEADLINE = datetime.fromisoformat("2026-10-31T23:00:00+00:00").timestamp()
MAX_ALLOCATION_SECONDS = 10800
RECEIPT_RESERVE_SECONDS = 10800
CLI_FILES = {"codex.exe": "f6dbf48cb70f62649c645f26c87dc9bf84cc36986202dfad8e12fb5b8ca70312",
    "codex-code-mode-host.exe": "3b6a9179a4da17fa5fc6948219cd61486dc3b534c683838076d8c61bd311c68e",
    "codex-command-runner.exe": "ce80b56a2f37f808815fde33cceb97ac858ceecde296425ad3860f0f37fb4877",
    "codex-windows-sandbox-setup.exe": "c4da812016cbfb92d9a62791f78460c59e9662faadb0a2720d3aa5d0535b80bd"}
AUTHORIZATION_FIELDS = {"schema", "scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "verified",
    "expires_at", "user_messages", "old_candidates_imported", "operator_algorithm_advice",
    "native_calls_started_at_authorization", "job_id", "remote_root", "artifacts"}
ARTIFACTS = {"plan", "source_zip", "runtime_manifest", "preparation_manifest", "r1_contracts", "harness", "artifact_aliases",
    "subject_qualification", "subject_reception", "cli_identity", "worker_lane_admission", "integration_review",
    "primes_release", "cell_admission", "session_freshness", "transport_admission"}
COMMON_PROOF_FIELDS = CELL_FIELDS | {"schema", "verified", "evidence_refs"}
PROOF_FIELDS = {
    "transport_admission": {"native_model_calls", "normal_first_call_proved", "cli_tools_disabled", "cli_identity_sha256",
        "subject_qualification_sha256", "neutral_tests_passed"},
    "cli_identity": {"version", "executable_path", "executable_sha256", "source_execution_allowed", "authentication",
        "files", "observed_at", "task_cli_policy_sha256"},
    "integration_review": {"neutral_tests_passed", "blocking_findings", "reviewer", "reviewed_at", "limitations",
        "reviewed_files", "reviewed_command_sha256"},
    "cell_admission": {"human_max_only", "one_cell_only", "automatic_extension", "all_prior_calls_reconciled",
        "maximum_native_workers", "primes_release_sha256", "one_submission_only"},
    "session_freshness": {"observed_at", "verified_no_prior_claims", "new_cache", "new_registry", "new_mailbox",
        "native_calls_started_at_admission"},
}
_INSTALLED_BINDING = None
_INSTALLED_ALIASES = None


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_json(path):
    path = Path(path)
    need(path.is_file() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
         for p in (path, *path.parents)) and path.stat().st_size <= 8 * 1024 * 1024,
         "Missing, linked or oversized matrix JSON artifact")
    try:
        value = json.loads(path.read_text(encoding="utf8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as exc:
        raise InfrastructureError("Malformed matrix JSON artifact") from exc
    need(isinstance(value, dict), "Matrix receipt must be a JSON object")
    return value


def validate_aliases(value, source_sha256):
    """Typed exact aliases, including manifest-bound directory inventories; no prefix rewrite."""
    need(isinstance(value, dict) and set(value) == {"schema", "scope_id", "source_zip_sha256",
                                                   "preparation_manifest_sha256", "entries"}
         and value["schema"] == "hpc-forest-matrix15-artifact-aliases-v2" and value["scope_id"] == SCOPE
         and value["source_zip_sha256"] == source_sha256 and sha_value(value["preparation_manifest_sha256"]),
         "Alias table is not bound to this matrix derivative/preparation")
    entries = value["entries"]
    need(isinstance(entries, list) and len(entries) <= 2000, "Bounded explicit artifact aliases required")
    windows_seen, arm_seen, canonical_seen = set(), set(), set()
    for entry in entries:
        need(isinstance(entry, dict) and isinstance(entry.get("kind"), str)
             and entry["kind"] in {"file", "directory"}, "Typed alias entry required")
        common = {"kind", "canonical_path", "windows_path", "arm_path"}
        expected = common | ({"sha256"} if entry["kind"] == "file" else
                             {"subject_id", "role", "inventory_prefix", "inventory_sha256"})
        need(set(entry) == expected and all(isinstance(entry[key], str) for key in common),
             "Exact typed alias fields required")
        if entry["kind"] == "file":
            need(sha_value(entry["sha256"]), "File alias needs an exact SHA256")
        else:
            prefix = PurePosixPath(entry["inventory_prefix"]) if isinstance(entry["inventory_prefix"], str) else None
            need(isinstance(entry["subject_id"], str) and entry["subject_id"] in SUBJECTS
                 and isinstance(entry["role"], str) and entry["role"] in {"official", "source", "validation"}
                 and sha_value(entry["inventory_sha256"])
                 and prefix is not None and prefix.parts and not prefix.is_absolute() and ".." not in prefix.parts
                 and prefix.as_posix() == entry["inventory_prefix"] and "\\" not in entry["inventory_prefix"]
                 and not any(char in entry["inventory_prefix"] for char in (":", "\0", "\r", "\n")),
                 "Directory alias needs exact role/subject/manifest inventory")
        windows, arm = PureWindowsPath(entry["windows_path"]), PurePosixPath(entry["arm_path"])
        canonical = entry["canonical_path"]
        canonical_windows = PureWindowsPath(canonical)
        canonical_valid = ((canonical_windows.is_absolute() and re.match(r"^[A-Za-z]:[/\\]", canonical) is not None
                            and ".." not in canonical_windows.parts) or
                           (PurePosixPath(canonical).is_absolute() and ".." not in PurePosixPath(canonical).parts
                            and "\\" not in canonical and PurePosixPath(canonical).as_posix() == canonical))
        canonical_key = canonical_windows.as_posix().casefold() if canonical_windows.is_absolute() else canonical
        need(windows.is_absolute() and re.match(r"^[A-Za-z]:[/\\]", entry["windows_path"]) is not None
             and ".." not in windows.parts and arm.is_absolute() and ".." not in arm.parts
             and "\\" not in entry["arm_path"] and arm.as_posix() == entry["arm_path"]
             and canonical_valid and not any(char in canonical + entry["windows_path"] + entry["arm_path"]
                                             for char in ("\0", "\r", "\n"))
             and windows.as_posix().casefold() not in windows_seen and arm.as_posix() not in arm_seen
             and canonical_key not in canonical_seen,
             "Alias paths must be unique absolute platform-typed files")
        windows_seen.add(windows.as_posix().casefold())
        arm_seen.add(arm.as_posix())
        canonical_seen.add(canonical_key)
    owners = {}
    for index, entry in enumerate(entries):
        for key in ("canonical_path", "windows_path", "arm_path"):
            path = entry[key]
            pure = PureWindowsPath(path)
            identity = ("windows", pure.as_posix().casefold()) if pure.is_absolute() else ("arm", path)
            need(identity not in owners or owners[identity] == index, "Cross-entry alias paths are ambiguous")
            owners[identity] = index
    return value


def _matches_alias_path(path, entry):
    candidate = PureWindowsPath(path)
    for key in ("canonical_path", "windows_path", "arm_path"):
        other = entry[key]
        if path == other or (candidate.is_absolute() and PureWindowsPath(other).is_absolute()
                             and candidate.as_posix().casefold() == PureWindowsPath(other).as_posix().casefold()):
            return True
    return False


def validate_alias_dependencies(aliases, plan_ref, aliases_ref, downstream_refs):
    """Keep the immutable alias table upstream of the plan and final admission proofs."""
    forbidden = [plan_ref, aliases_ref, *downstream_refs]
    need(all(reference(ref) for ref in forbidden), "Exact downstream references required")
    for entry in aliases["entries"]:
        if entry["kind"] == "file":
            need(not any(_matches_alias_path(ref["path"], entry) for ref in forbidden),
                 "Plan/alias/final admission artifacts cannot be dependencies of the immutable alias table")
    return aliases


def alias_reference(ref, aliases, *, platform):
    """Return a declared platform file alias; do not touch the filesystem."""
    need(reference(ref), "Artifact requires exactly a path and SHA256")
    need(platform in {"windows", "arm"}, "Unknown artifact alias platform")
    selected = ref["path"]
    if aliases is not None:
        for entry in aliases["entries"]:
            if entry["kind"] == "file" and _matches_alias_path(selected, entry):
                need(ref["sha256"] == entry["sha256"], "Alias path has another artifact digest")
                selected = entry["windows_path"] if platform == "windows" else entry["arm_path"]
                break
    return {"path": selected, "sha256": ref["sha256"]}


def directory_reference(canonical_path, *, subject_id, role, aliases, preparation_manifest_sha256, platform):
    """Resolve exactly one declared subject/role directory; never derive a prefix or subject slug."""
    need(isinstance(canonical_path, str) and bool(canonical_path)
         and platform in {"windows", "arm"} and role in {"official", "source", "validation"}
         and aliases is not None and aliases["preparation_manifest_sha256"] == preparation_manifest_sha256,
         "Explicit preparation-bound directory aliases required")
    matches = [entry for entry in aliases["entries"] if entry["kind"] == "directory"
               and entry["subject_id"] == subject_id and entry["role"] == role
               and _matches_alias_path(canonical_path, entry)]
    need(len(matches) == 1, "Directory is missing, ambiguous or bound to another role/subject")
    entry = matches[0]
    return {"path": entry["windows_path"] if platform == "windows" else entry["arm_path"],
            "inventory_prefix": entry["inventory_prefix"], "inventory_sha256": entry["inventory_sha256"]}


def directory_artifact(canonical_path, *, subject_id, role, preparation_manifest, preparation_manifest_sha256,
                       aliases=None, platform=None, verify=True):
    aliases = _INSTALLED_ALIASES if aliases is None else aliases
    projected = directory_reference(canonical_path, subject_id=subject_id, role=role, aliases=aliases,
        preparation_manifest_sha256=preparation_manifest_sha256,
        platform=platform or ("windows" if os.name == "nt" else "arm"))
    prefix = projected["inventory_prefix"] + "/"
    need(isinstance(preparation_manifest, dict), "Pinned original preparation manifest is required")
    declared = preparation_manifest.get("files", {})
    need(isinstance(declared, dict) and len(declared) <= 2000, "Bounded immutable preparation inventory required")
    inventory = {}
    for name, sha in declared.items():
        rel = PurePosixPath(name) if isinstance(name, str) else None
        need(rel is not None and rel.parts and not rel.is_absolute() and ".." not in rel.parts
             and rel.as_posix() == name and "\\" not in name
             and not any(char in name for char in (":", "\0", "\r", "\n")) and sha_value(sha),
             "Unsafe immutable preparation inventory")
        if name.startswith(prefix):
            inventory[name[len(prefix):]] = sha
    need(bool(inventory) and digest(inventory) == projected["inventory_sha256"],
         "Directory inventory differs from the pinned original preparation manifest")
    root = Path(projected["path"])
    if verify:
        need(root.is_absolute() and root.is_dir() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
             for p in (root, *root.parents)), "Missing or linked explicit preparation directory")
        actual = {}
        expected_dirs = {PurePosixPath(name).parent.as_posix() for name in inventory}
        expected_dirs |= {parent.as_posix() for name in inventory for parent in PurePosixPath(name).parents}
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                 "Preparation links/junctions are forbidden")
            if path.is_dir():
                need(relative in expected_dirs, "Extra directory outside the exact preparation inventory")
            else:
                need(path.is_file() and relative in inventory and path.stat().st_size <= 128 * 1024 * 1024,
                     "Extra/nonregular/oversized preparation member")
                actual[relative] = file_digest(path)
        need(actual == inventory, "Explicit preparation directory has changed/missing/extra bytes")
    return root, inventory


def artifact(ref, *, aliases=None):
    aliases = _INSTALLED_ALIASES if aliases is None else aliases
    selected = alias_reference(ref, aliases, platform="windows" if os.name == "nt" else "arm")["path"]
    path = Path(selected)
    need(path.is_absolute() and ".." not in path.parts and path.is_file() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
         for p in (path, *path.parents)) and file_digest(path) == ref["sha256"], "Missing or changed matrix artifact")
    return path


def same_artifact_reference(left, right, *, read_ref=artifact):
    need(reference(left) and reference(right), "Exact SHA-bound artifact references required")
    return left["sha256"] == right["sha256"] and read_ref(left).resolve() == read_ref(right).resolve()


def evidence_refs(value, read_ref=artifact):
    refs = value.get("evidence_refs")
    need(isinstance(refs, list) and bool(refs), "Concrete nonempty hashed evidence references required")
    need(len(refs) <= 1000 and all(reference(ref) for ref in refs)
         and len({(ref["path"], ref["sha256"]) for ref in refs}) == len(refs),
         "Duplicate or oversized evidence references")
    return [read_ref(ref) for ref in refs]


def selected_identity(value):
    selected = {key: value.get(key) for key in ("cell_key", "subject_id", "model", "effort", "session_id")}
    validate_cell(selected)
    need(value.get("scope_id") == SCOPE, "Wrong matrix15 scope")
    return selected["model"], selected["session_id"]


def cell_binding(authorization):
    selected_identity(authorization)
    refs = authorization["artifacts"]
    plan = validate_plan(read_json(artifact(refs["plan"])))
    subject = resolve_subject(plan, authorization["cell_key"])
    return {"scope_id": SCOPE, "cell_key": authorization["cell_key"], "subject_id": subject["subject_id"],
        "model": subject["model"], "effort": EFFORT, "session_id": subject["session_id"],
        "job_id": authorization["job_id"], "remote_root": authorization["remote_root"],
        "source_zip_sha256": refs["source_zip"]["sha256"], "plan_sha256": refs["plan"]["sha256"],
        "preparation_manifest_sha256": refs["preparation_manifest"]["sha256"],
        "r1_contract_sha256": subject["r1_contract_ref"]["sha256"]}


def bind_worker_cache(root, authorization):
    root = Path(root)
    need(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (root, *root.parents)),
         "Linked worker cache forbidden")
    root.mkdir(parents=True, exist_ok=True)
    binding = cell_binding(authorization)
    path = root / "CELL-BINDING.json"
    if not path.exists():
        need(not any(root.iterdir()), "Unbound nonempty cache cannot be reused")
        with path.open("x", encoding="utf8") as stream:
            json.dump(binding, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    need(read_json(path) == binding, "Worker cache belongs to another cell/job/session/contract")
    for claim in root.glob("*/generation-claimed.json"):
        request_path = claim.with_name("downloaded-request.json")
        request = read_json(request_path)
        need(read_json(claim).get("request_sha256") == file_digest(request_path)
             and request.get("model") == binding["model"] and request.get("session_id") == binding["session_id"]
             and request.get("reasoning_effort") == EFFORT, "Started claim differs; never regenerate it")
    return binding


def deadline_guard(now=None):
    current = time.time() if now is None else now
    need(number(current) and current + MAX_ALLOCATION_SECONDS + RECEIPT_RESERVE_SECONDS < DEADLINE,
         "Insufficient exclusive deadline reserve")


def allocation_guard():
    env = os.environ
    required = {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1", "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}
    need(platform.system() == "Linux" and platform.machine().lower() in {"aarch64", "arm64"}
         and env.get("SLURM_JOB_ID", "").isdigit() and all(env.get(key) == value for key, value in required.items())
         and all(env.get(key, "") in {"", "0"} for key in
                 ("SLURM_GPUS", "SLURM_GPUS_PER_NODE", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS", "CUDA_VISIBLE_DEVICES"))
         and hasattr(os, "sched_getaffinity") and len(os.sched_getaffinity(0)) == 4,
         "Matrix15 requires its owned ARM64 1-node/1-task/4CPU/16GiB/0GPU allocation")
    deadline_guard()
    return {"job_id": env["SLURM_JOB_ID"], "architecture": platform.machine().lower(), "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0, "affinity_cpu_ids": sorted(os.sched_getaffinity(0)),
            "affinity_cpu_count": 4}


def verify_runtime(source_zip, runtime_manifest):
    """Use the derivative's actual dynamic inventory, never the historical 113-file count."""
    root = Path(__file__).resolve().parents[2]
    declared = read_json(runtime_manifest)
    need(bool(declared) and all(isinstance(key, str) and sha_value(value) for key, value in declared.items()),
         "Runtime manifest must contain exact relative-file SHA256 entries")
    files, folded, total = {}, set(), 0
    with zipfile.ZipFile(source_zip) as archive:
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            need(not item.is_dir() and name.parts and name.parts[0] == "HPC-Forest" and len(name.parts) > 1
                 and not name.is_absolute() and ".." not in name.parts and "\\" not in item.filename
                 and name.as_posix() == item.filename and "\0" not in item.filename
                 and (item.external_attr >> 16) & 0o170000 in {0, 0o100000} and not item.flag_bits & 1,
                 "Unsafe matrix source ZIP")
            key = name.relative_to("HPC-Forest").as_posix()
            total += item.file_size
            need(key.casefold() not in folded and len(files) < 2000 and item.file_size <= 8 * 1024 * 1024 and total <= 64 * 1024 * 1024,
                 "Duplicate or oversized matrix source ZIP")
            folded.add(key.casefold())
            files[key] = archive.read(item)
    local = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()
             and not any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"} for part in p.relative_to(root).parts)}
    need(set(files) == set(declared) == set(local), "Executing source inventory differs from admitted ZIP/manifest")
    need(all(not local[key].is_symlink() and local[key].read_bytes() == raw
             and hashlib.sha256(raw).hexdigest() == declared[key] for key, raw in files.items()),
         "Executing matrix runtime bytes changed")


SOL_PILOT_RELEASE_SHA256 = "ce06f8435526826051e66adc3f779436aeb97c7204c6b1f3a89a58bc9cb7efb0"
SOL_PILOT_FINAL_AUDIT_SHA256 = "b8bfd8c55dc0c4b02bed058cb58e17178400fa026cd53655ec987af0f8e0222e"
SOL_PILOT_EXTERNAL_AUDIT_SHA256 = "86da0f5789ed1f6c9926289d92d198b4c2399626df5664afb58a9d6d3a71913a"


def verify_primes_release(path, read_ref=artifact):
    """Accept only the already audited Sol pilot; subject/capacity gates remain separate."""
    value = read_json(path)
    identity = {"schema": "hpc-forest-r2h-first-cell-scientific-release-v1",
                "scope_id": "hpc-forest-primes-native-max-r2h", "model": "gpt-6.1-sol",
                "effort": EFFORT, "session_id": "0f1de21e9eda4fb89a8dbd66c6fa8d6c", "job_id": "755306",
                "source_zip_sha256": "1eea1a11a5f6bdcadedbb295d708bcb0b67c428ea623c80c5391a884bdb8dba7",
                "plan_sha256": "9b060aa89f278bfd124da607f25c119654eb5dd21d7f19e2ecb0f8acf5ca5a72"}
    need(all(value.get(key) == expected for key, expected in identity.items()),
         "The exact already received Sol MAX primes pilot is required")
    flags = ("verified", "pipeline_complete", "five_confirmations_verified", "received_native_cohort_audited",
             "all_started_calls_reconciled", "independent_performance_remeasurement_verified",
             "owned_worker_and_passives_absent", "complete_52_file_cache_preserved",
             "reference_and_winner_sources_commits_trees_outcomes_equal_before_and_after_owned_stop")
    need(all(value.get(key) is True for key in flags)
         and all(value.get(key) is False for key in ("prepared", "synthetic", "old_cohort", "budget_or_chronology_reset"))
         and all(type(value.get(key)) is int and value[key] == expected for key, expected in
                 (("exact_known_native_calls", 3), ("exact_known_tokens", 59037), ("unknown_usage_calls", 0), ("replayed_claims", 0))),
         "Sol pilot is incomplete, synthetic, unreconciled or has unknown/replayed usage")
    need(file_digest(path) == SOL_PILOT_RELEASE_SHA256, "Sol pilot release SHA differs from the reviewed immutable receipt")
    paths = evidence_refs(value, read_ref)
    proofs = {ref["sha256"]: read_json(proof) for ref, proof in zip(value["evidence_refs"], paths, strict=True)}
    need(SOL_PILOT_FINAL_AUDIT_SHA256 in proofs and SOL_PILOT_EXTERNAL_AUDIT_SHA256 in proofs,
         "The real final audit and independent external measurement are required")
    audit = proofs[SOL_PILOT_FINAL_AUDIT_SHA256]
    measurement = proofs[SOL_PILOT_EXTERNAL_AUDIT_SHA256]
    need(all(audit.get(key) == identity[key] for key in ("scope_id", "model", "effort", "session_id", "job_id",
                                                        "source_zip_sha256", "plan_sha256"))
         and audit.get("terminal_pipeline", {}).get("pipeline_complete") is True
         and audit.get("campaign", {}).get("lineage_and_five_confirmations_verified") is True
         and audit.get("transport_cost_reconciliation", {}).get("exact_known_native_invocations") == 3
         and audit.get("transport_cost_reconciliation", {}).get("exact_known_tokens") == 59037
         and audit.get("transport_cost_reconciliation", {}).get("unknown_native_invocations") == 0,
         "The bounded final audit does not prove five confirmations and exact usage")
    need(measurement.get("schema") == "hpc-forest-r2h-independent-cold-audit-v1"
         and measurement.get("verified") is True and measurement.get("model") == identity["model"]
         and measurement.get("effort") == EFFORT and measurement.get("original_search_job_id") == identity["job_id"]
         and measurement.get("job_id") == value.get("external_pair", {}).get("job_id")
         and measurement.get("independent_from_search") is True
         and measurement.get("frozen_winner_reconfirmed") is True
         and measurement.get("independent_performance_audit_verified") is True
         and measurement.get("unique_certified_inputs") == 12 and measurement.get("blocking_findings") == [],
         "The separate bounded external remesurement is unproved")
    read_ref(measurement["archive"])
    return value


def verify_qualification(qualification, reception, subject, binding, *, qualification_ref, prepared, read_ref=artifact,
                         aliases=None, preparation_manifest=None):
    """Future generic qualification schema; absent/proposed receipts cannot open the gate."""
    common = {key: binding[key] for key in ("scope_id", "subject_id", "source_zip_sha256", "plan_sha256",
                                           "preparation_manifest_sha256", "r1_contract_sha256")}
    need(reference(qualification_ref) and read_json(read_ref(qualification_ref)) == qualification,
         "Qualification must be the exact final artifact bound by the authorization")
    q_fields = set(common) | {"schema", "verified", "observation_mode", "allocation", "native_model_calls",
        "r1_paired_contract_verified", "execution_semantics_changed", "independent_raw_stdout_per_candidate_verified",
        "independent_performance_audit_verified", "prepared_contract", "prepared_root", "prepared_files", "evidence_refs"}
    need(set(qualification) == q_fields and qualification["schema"] == "hpc-forest-matrix15-subject-qualification-v1"
         and qualification["verified"] is True and all(qualification[key] == value for key, value in common.items())
         and qualification["observation_mode"] == "command-stream-v1" and type(qualification["native_model_calls"]) is int
         and qualification["native_model_calls"] == 0 and qualification["r1_paired_contract_verified"] is True
         and all(qualification[key] is False for key in ("execution_semantics_changed",
                     "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified")),
         "Actual generic zero-model qualification with explicit attribution limits is required")
    allocation = qualification["allocation"]
    need(isinstance(allocation, dict) and allocation.get("architecture") in {"aarch64", "arm64"}
         and isinstance(allocation.get("job_id"), str) and allocation["job_id"].isdigit()
         and all(type(allocation.get(key)) is int and allocation[key] == value
                 for key, value in {"nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0}.items()),
         "Actual allocated subject contract qualification required")
    need(same_artifact_reference(qualification["prepared_contract"], subject["prepared_contract_ref"], read_ref=read_ref),
         "Qualified contract differs from the same explicitly resolved selected subject file")
    assert_r1_pair_contract(read_json(read_ref(subject["r1_contract_ref"])), read_json(read_ref(qualification["prepared_contract"])))
    evidence_refs(qualification, read_ref)
    r_fields = set(common) | {"schema", "verified", "qualification", "archive", "audit", "evidence_refs"}
    need(set(reception) == r_fields and reception["schema"] == "hpc-forest-matrix15-subject-reception-v1"
         and reception["verified"] is True and all(reception[key] == value for key, value in common.items())
         and same_artifact_reference(reception["qualification"], qualification_ref, read_ref=read_ref),
         "Actual received subject qualification is required")
    read_ref(reception["qualification"])
    archive_path, audit_path = read_ref(reception["archive"]), read_ref(reception["audit"])
    audit = read_json(audit_path)
    need(audit.get("schema") == "hpc-forest-matrix15-subject-reception-audit-v1" and audit.get("verified") is True
         and all(audit.get(key) == value for key, value in common.items())
         and audit.get("qualification_sha256") == reception["qualification"]["sha256"]
         and audit.get("archive_sha256") == file_digest(archive_path)
         and all(audit.get(key) is True for key in ("all_members_regular_unique", "restored_files_byte_identical",
                "r1_paired_contract_verified", "actual_official_evaluator_trace_verified"))
         and audit.get("independent_raw_stdout_per_candidate_verified") is False
         and audit.get("independent_performance_audit_verified") is False, "Concrete cold received subject audit missing")
    evidence_refs(reception, read_ref)
    files = qualification["prepared_files"]
    need(isinstance(files, dict) and bool(files) and all(isinstance(name, str) and sha_value(sha) for name, sha in files.items()),
         "Qualified preparation file inventory missing")
    for name in files:
        rel = PurePosixPath(name)
        need(not rel.is_absolute() and ".." not in rel.parts and "\\" not in name and rel.parts,
             "Unsafe prepared subject inventory")
    root, inventory = directory_artifact(subject["official_preparation_path"], subject_id=subject["subject_id"],
        role="official", preparation_manifest=preparation_manifest,
        preparation_manifest_sha256=binding["preparation_manifest_sha256"], aliases=aliases, verify=prepared)
    received_root, received_inventory = directory_artifact(qualification["prepared_root"], subject_id=subject["subject_id"],
        role="official", preparation_manifest=preparation_manifest,
        preparation_manifest_sha256=binding["preparation_manifest_sha256"], aliases=aliases, verify=False)
    need(root == received_root and inventory == received_inventory == files,
         "Qualified directory is not the same explicit preparation inventory/root")


def validate_receipt(path, required_jobs, *, runtime=True, prepared=True, initial_lane=True, now=None):
    data = read_json(path)
    selected_identity(data)
    current = time.time() if now is None else now
    need(set(data) == AUTHORIZATION_FIELDS and data["schema"] == "hpc-forest-matrix15-authorization-v1"
         and data["scope_id"] == SCOPE and required_jobs == {SCOPE} and data["verified"] is True
         and number(data["expires_at"]) and current < data["expires_at"] <= DEADLINE
         and isinstance(data["user_messages"], list) and bool(data["user_messages"])
         and all(isinstance(message, str) and message.strip() for message in data["user_messages"])
         and data["old_candidates_imported"] is False and data["operator_algorithm_advice"] is False
         and type(data["native_calls_started_at_authorization"]) is int and data["native_calls_started_at_authorization"] == 0
         and isinstance(data["job_id"], str) and data["job_id"].isdigit(), "Matrix authorization is absent/expired/unrelated")
    deadline_guard(current)
    refs = data["artifacts"]
    need(isinstance(refs, dict) and set(refs) == ARTIFACTS, "Every exact matrix admission artifact is required")
    # These two bootstraps use actual host paths, pinned by the authorization.
    # Aliases are finalized before the plan; final proofs use direct host paths.
    plan = validate_plan(read_json(artifact(refs["plan"])))
    aliases = validate_aliases(read_json(artifact(refs["artifact_aliases"])), refs["source_zip"]["sha256"])
    downstream_keys = ARTIFACTS - {"plan", "artifact_aliases", "source_zip", "runtime_manifest",
                                  "preparation_manifest", "r1_contracts", "harness", "primes_release"}
    validate_alias_dependencies(aliases, refs["plan"], refs["artifact_aliases"],
                                [refs[key] for key in sorted(downstream_keys)])
    need(refs["artifact_aliases"]["sha256"] == plan["artifact_aliases"]["sha256"], "Alias table differs from immutable plan")
    need(aliases["preparation_manifest_sha256"] == plan["preparation_manifest"]["sha256"],
         "Alias directory inventories bind another preparation manifest")
    def read_ref(ref):
        return artifact(ref, aliases=aliases)
    def same_ref(left, right):
        return same_artifact_reference(left, right, read_ref=read_ref)
    paths = {key: read_ref(ref) for key, ref in refs.items()}
    subject = resolve_subject(plan, data["cell_key"])
    need(refs["source_zip"]["sha256"] == plan["source_zip_sha256"]
         and all(same_ref(refs[key], plan[key]) for key in ("runtime_manifest", "preparation_manifest", "r1_contracts", "harness"))
         and plan["protocol"]["sha256"] == PROTOCOL_SHA256 and file_digest(read_ref(plan["protocol"])) == PROTOCOL_SHA256
         and refs["r1_contracts"]["sha256"] == R1_CONTRACTS_SHA256 and refs["harness"]["sha256"] == HARNESS_SHA256,
         "Admitted plan/source/protocol/preparation/R1/harness binding changed")
    need(plan["primes_release"] is not None and same_ref(refs["primes_release"], plan["primes_release"]),
         "Prepared plan cannot launch without the reviewed single Sol primes pilot")
    verify_primes_release(paths["primes_release"], read_ref)
    r1 = read_json(paths["r1_contracts"])
    need(r1.get("schema") == "hpc-forest-harness-reference-contracts-v1"
         and r1.get("subjects", {}).get(subject["subject_id"], {}).get("contract") == subject["r1_contract_ref"],
         "Subject contract is not its exact canonical R1 reference")
    preparation = read_json(paths["preparation_manifest"])
    record = preparation.get("records", {}).get(subject["subject_id"])
    need(isinstance(record, dict) and record.get("status") == "ready" and digest(record) == subject["preparation_sha256"],
         "Prepared subject record changed or was not ready in the immutable R1 preparation")
    need(isinstance(record.get("prepared"), dict), "Original prepared subject directory record missing")
    roots = {}
    for role, canonical in (("official", subject["official_preparation_path"]),
                            ("source", record["prepared"].get("source")),
                            ("validation", record["prepared"].get("validation"))):
        need(isinstance(canonical, str) and bool(canonical), "Canonical prepared directory path missing")
        roots[role], _ = directory_artifact(canonical, subject_id=subject["subject_id"], role=role,
            preparation_manifest=preparation, preparation_manifest_sha256=refs["preparation_manifest"]["sha256"],
            aliases=aliases, verify=prepared)
    need(roots["source"].is_relative_to(roots["official"]) and roots["validation"].is_relative_to(roots["official"])
         and len(set(roots.values())) == 3, "Official/source/validation aliases must be separately bound inside the official root")
    need(read_ref(subject["prepared_contract_ref"]).resolve() == (roots["validation"] / "contract.json").resolve(),
         "Prepared contract is not inside the same explicitly resolved validation directory")
    read_ref(subject["statement_ref"])
    assert_r1_pair_contract(read_json(read_ref(subject["r1_contract_ref"])), read_json(read_ref(subject["prepared_contract_ref"])))
    binding = cell_binding(data)
    remote = PurePosixPath(data["remote_root"])
    need(remote.is_absolute() and ".." not in remote.parts and "\\" not in data["remote_root"]
         and remote.name == SCOPE + "-" + data["session_id"], "Fresh absolute session-bound ARM root required")
    qualification = read_json(paths["subject_qualification"])
    reception = read_json(paths["subject_reception"])
    lane = read_json(paths["worker_lane_admission"])
    validate_alias_dependencies(aliases, refs["plan"], refs["artifact_aliases"],
        [reception.get("archive"), reception.get("audit"), lane.get("minimal_owned_observations"),
         lane.get("slot_reservation")])
    verify_qualification(qualification, reception, subject, binding,
                         qualification_ref=refs["subject_qualification"], prepared=prepared, read_ref=read_ref,
                         aliases=aliases, preparation_manifest=preparation)
    for key, extra in PROOF_FIELDS.items():
        proof = read_json(paths[key])
        need(set(proof) == COMMON_PROOF_FIELDS | extra and proof["schema"] == "hpc-forest-matrix15-" + key.replace("_", "-") + "-v1"
             and proof["verified"] is True and all(proof[name] == value for name, value in binding.items()),
             "Exact closed verified matrix proof missing: " + key)
        evidence_refs(proof, read_ref)
        if key == "transport_admission":
            need(type(proof["native_model_calls"]) is int and proof["native_model_calls"] == 0
                 and proof["normal_first_call_proved"] is False and proof["cli_tools_disabled"] is True
                 and proof["neutral_tests_passed"] is True and proof["cli_identity_sha256"] == refs["cli_identity"]["sha256"]
                 and proof["subject_qualification_sha256"] == refs["subject_qualification"]["sha256"], "Pre-call exact transport proof missing")
        elif key == "cli_identity":
            files = proof["files"]
            need(proof["version"] == "codex-cli 0.163.0-alpha.10.2" and proof["source_execution_allowed"] is False
                 and proof["authentication"] == "existing-local-ChatGPT" and sha_value(proof["task_cli_policy_sha256"])
                 and isinstance(files, dict) and set(files) == set(CLI_FILES)
                 and all(reference(files[name]) and files[name]["sha256"] == sha for name, sha in CLI_FILES.items())
                 and proof["executable_path"] == files["codex.exe"]["path"]
                 and proof["executable_sha256"] == CLI_FILES["codex.exe"] and number(proof["observed_at"]), "Pinned current CLI/host files missing")
        elif key == "integration_review":
            need(proof["neutral_tests_passed"] is True and proof["blocking_findings"] == []
                 and isinstance(proof["reviewer"], str) and bool(proof["reviewer"]) and number(proof["reviewed_at"])
                 and isinstance(proof["limitations"], list) and isinstance(proof["reviewed_files"], list)
                 and bool(proof["reviewed_files"]) and sha_value(proof["reviewed_command_sha256"]), "Unresolved/missing concrete integration review")
            for ref in proof["reviewed_files"]:
                read_ref(ref)
        elif key == "cell_admission":
            need(all(proof[name] is True for name in ("human_max_only", "one_cell_only", "all_prior_calls_reconciled", "one_submission_only"))
                 and proof["automatic_extension"] is False and type(proof["maximum_native_workers"]) is int
                 and proof["maximum_native_workers"] == 4 and proof["primes_release_sha256"] == refs["primes_release"]["sha256"],
                 "A new explicit single-cell submission admission is required")
        elif key == "session_freshness":
            need(all(proof[name] is True for name in ("verified_no_prior_claims", "new_cache", "new_registry", "new_mailbox"))
                 and type(proof["native_calls_started_at_admission"]) is int and proof["native_calls_started_at_admission"] == 0
                 and number(proof["observed_at"]) and 0 <= current - proof["observed_at"]
                 and (not initial_lane or current - proof["observed_at"] <= 600), "Fresh unused one-cell session/cache/registry/mailbox proof required")
    validate_lane(lane, binding, read_ref, initial=initial_lane, now=current)
    if runtime:
        verify_runtime(paths["source_zip"], paths["runtime_manifest"])
    return data


def install_identity(receipt, *, prepared=True):
    global _INSTALLED_BINDING, _INSTALLED_ALIASES
    receipt = Path(receipt)
    frozen_sha = file_digest(receipt)
    authorization = validate_receipt(receipt, {SCOPE}, prepared=prepared)
    binding = cell_binding(authorization)
    need(file_digest(receipt) == frozen_sha, "Authorization changed during initial admission")
    need(_INSTALLED_BINDING is None or _INSTALLED_BINDING == binding, "A worker process may select only one matrix cell for its lifetime")
    _INSTALLED_BINDING = dict(binding)
    _INSTALLED_ALIASES = validate_aliases(read_json(artifact(authorization["artifacts"]["artifact_aliases"])),
                                          authorization["artifacts"]["source_zip"]["sha256"])
    refs = {key: dict(ref) for key, ref in authorization["artifacts"].items()}
    model, _ = selected_identity(authorization)
    from . import codex_mailbox, codex_process, codex_worker
    for module in (codex_mailbox, codex_process, codex_worker):
        module.MODEL, module.EFFORT = model, EFFORT

    def gate(path, required_jobs):
        need(file_digest(Path(path)) == frozen_sha, "Authorization replaced after initial admission")
        fresh = validate_receipt(path, required_jobs, prepared=prepared, initial_lane=False)
        need(file_digest(Path(path)) == frozen_sha and cell_binding(fresh) == binding and fresh["artifacts"] == refs,
             "Immutable cell/source/plan/admission binding changed")
        return fresh
    codex_process.check_dependencies = gate
    codex_worker.check_dependencies = gate
    return authorization
