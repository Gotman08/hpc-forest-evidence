"""Fresh R2h cohort: one selected unused Luna/Astra/Terra/Sol MAX cell per admission."""
from __future__ import annotations

import json
import os
import platform
import re
import tarfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from .core import InfrastructureError, file_digest
from .primes_contract import (
    COMPILER_FLAGS,
    PREPARATION_MANIFEST_SHA256,
    REFERENCE_SHA256,
    specification,
    verify_preparation,
    verify_resolved_values,
)
from .primes_lane_contract import PLAN_CONTRACT, validate_lane_v2

SCOPE = 'hpc-forest-primes-native-max-r2h'
EFFORT = "max"
MAXIMUM_NATIVE_WORKERS = 4
CELLS = {'gpt-6-luna': 'd231e8f9f0ee433b8f05aa8aa3fae22f', 'gpt-6-astra': '798b99a175d4454d9371e8ba898503e4', 'gpt-5.6-terra': '7a46678417dc450c93fd23f76132e90f', 'gpt-6.1-sol': '0f1de21e9eda4fb89a8dbd66c6fa8d6c'}
LUNA_SOURCE = "3e290f835570a8746be3c52144932b8c6866564980fd858cf4c0495a7b1e68c5"
LUNA_PLAN = "54ffd49f4dc868085d22208f773c4b4883590b25251b5992232509a1dc197024"
LUNA_SESSION = "c8044062692149138d826d3f388a08ef"
DEADLINE = datetime.fromisoformat("2026-10-31T23:00:00+00:00").timestamp()
MAX_ALLOCATION_SECONDS = 10800
RECEIPT_RESERVE_SECONDS = 10800
ARTIFACTS = {"plan", "source_zip", "preparation_manifest", "preparation_review",
             "allocated_contract_qualification", "transport_admission", "cli_identity",
             "worker_lane_admission", "integration_review", "allocated_contract_reception",
             "luna_first_start", "luna_closure", "extension_admission", "session_freshness"}
SCHEMAS = {"allocated_contract_qualification": "hpc-forest-primes-r2max-allocated-contract-qualification-v1",
           "transport_admission": "hpc-forest-primes-r2max-transport-admission-v1",
           "cli_identity": "hpc-forest-primes-r2max-cli-identity-v1",
           "worker_lane_admission": "hpc-forest-primes-r2max-worker-lane-admission-v2",
           "integration_review": "hpc-forest-primes-r2max-integration-review-v1",
           "allocated_contract_reception": "hpc-forest-primes-r2max-allocated-contract-reception-v1",
           "extension_admission": "hpc-forest-primes-r2max-single-extension-admission-v1",
           "session_freshness": "hpc-forest-primes-r2max-session-freshness-v1"}


AUTHORIZATION_FIELDS = {"schema", "scope_id", "model", "effort", "session_id", "verified",
                        "expires_at", "user_messages", "old_candidates_imported",
                        "operator_algorithm_advice", "native_calls_started_at_authorization",
                        "job_id", "remote_root", "artifacts"}
COMMON_PROOF_FIELDS = {"schema", "scope_id", "verified", "source_zip_sha256", "plan_sha256",
                       "preparation_manifest_sha256", "evidence_refs"}
PROOF_FIELDS = {
    "allocated_contract_qualification": {"allocation", "reference_source_sha256", "compiler_flags",
        "native_model_calls", "hardware_or_process_isolation_proved", "started_at", "finished_at",
        "negative_preserved_no_retry", "prepared_root", "prepared_files", "compiler_command",
        "reference_outputs_all_certified_bytes", "unique_certified_cases", "certified_expected_rows",
        "benchmark_origin", "calibration", "native_research_admitted", "error_type", "error", "reference_binary_sha256",
        "official_evaluator_trace_qualification", "official_evaluator_trace_files"},
    "allocated_contract_reception": {"archive", "audit", "qualification_sha256"},
    "transport_admission": {"model", "effort", "session_id", "job_id", "native_model_calls",
        "normal_first_call_proved", "cli_tools_disabled", "neutral_tests_passed",
        "cli_identity_sha256", "allocated_contract_qualification_sha256", "limits"},
    "cli_identity": {"version", "executable_path", "executable_sha256", "source_execution_allowed",
        "authentication", "files", "observed_at", "task_cli_policy_sha256"},
    "worker_lane_admission": {"active_native_workers_before_start", "maximum_native_workers",
        "live_worker_identities", "observed_at", "job_reservation", "lane_v2"},
    "integration_review": {"neutral_tests_passed", "blocking_findings", "reviewer", "reviewed_at",
        "limitations"},
    "extension_admission": {"model", "effort", "session_id", "job_id", "luna_first_start_sha256",
        "luna_closure_sha256", "human_max_only", "one_cell_only", "automatic_extension",
        "all_prior_calls_reconciled", "maximum_native_workers"},
    "session_freshness": {"model", "effort", "session_id", "job_id", "observed_at",
        "verified_no_prior_claims", "new_cache", "new_registry", "native_calls_started_at_admission"},
}


def selected_identity(value):
    model, session = value.get("model"), value.get("session_id")
    if (model not in CELLS or value.get("effort") != EFFORT or session != CELLS[model]):
        raise InfrastructureError("Exactly one unused registered R2h MAX identity/session is required")
    return model, session


def verify_worker_lane(value):
    """One selected cell may start only below the human-authorized global cap."""
    count = value.get("active_native_workers_before_start")
    if (type(count) is not int or not 0 <= count < MAXIMUM_NATIVE_WORKERS
            or type(value.get("maximum_native_workers")) is not int
            or value.get("maximum_native_workers") != MAXIMUM_NATIVE_WORKERS):
        raise InfrastructureError("No audited native worker lane under the explicit four-worker cap")


def verify_lane_admission(value, binding, *, initial=True, now=None):
    """Check the locally owned evidence projection, never inspect Windows from ARM."""
    verify_worker_lane(value)
    lane = value.get("lane_v2")
    try:
        validate_lane_v2(lane, binding, artifact, initial=initial, now=now)
    except (TypeError, ValueError, KeyError) as exc:
        raise InfrastructureError("Invalid R2d lane-v2 projection: " + str(exc)) from exc
    if (value.get("active_native_workers_before_start") != lane["active_native_workers_before_start"]
            or value.get("maximum_native_workers") != lane["maximum_native_workers_total"]
            or value.get("observed_at") != lane["observed_at"]):
        raise InfrastructureError("R2d wrapper contradicts its typed lane-v2 projection")


def cell_binding(authorization):
    model, session = selected_identity(authorization)
    return {"scope_id": SCOPE, "model": model, "effort": EFFORT, "session_id": session,
            "job_id": authorization["job_id"], "remote_root": authorization["remote_root"],
            "source_zip_sha256": authorization["artifacts"]["source_zip"]["sha256"],
            "plan_sha256": authorization["artifacts"]["plan"]["sha256"]}


def bind_worker_cache(root, authorization):
    """A reusable cache must carry the exact cell binding; unknown old caches fail closed."""
    root = Path(root)
    if root.is_symlink():
        raise InfrastructureError("Linked worker cache forbidden")
    root.mkdir(parents=True, exist_ok=True)
    binding = cell_binding(authorization)
    path = root / "CELL-BINDING.json"
    if not path.exists():
        if any(root.iterdir()):
            raise InfrastructureError("Unbound nonempty worker cache cannot be reused")
        with path.open("x", encoding="utf8") as stream:
            json.dump(binding, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    if read_json(path) != binding:
        raise InfrastructureError("Worker cache belongs to a different source/plan/job/session")
    for claim in root.glob("*/generation-claimed.json"):
        request_path = claim.with_name("downloaded-request.json")
        request = read_json(request_path)
        if (read_json(claim).get("request_sha256") != file_digest(request_path)
                or request.get("model") != binding["model"] or request.get("session_id") != binding["session_id"]
                or request.get("reasoning_effort") != EFFORT):
            raise InfrastructureError("Started claim has a different request/identity; never regenerate")
    return binding


def verify_luna_release(paths):
    first, closure = read_json(paths["luna_first_start"]), read_json(paths["luna_closure"])
    common = {"model": "gpt-6-luna", "effort": "max", "session_id": LUNA_SESSION,
              "job_id": "751992", "source_zip_sha256": LUNA_SOURCE, "plan_sha256": LUNA_PLAN}
    if (first.get("schema") != "hpc-forest-primes-r2max-first-start-verified-v1"
            or first.get("verified") is not True
            or any(first.get(k) != v for k, v in common.items())
            or first.get("technical_errors_found") is not False or first.get("invocation_unknown") is not False
            or not first.get("first_normal_delivered_call") or not first.get("first_real_evaluation")
            or closure.get("schema") != "hpc-forest-primes-r2max-luna-closure-admission-v1"
            or any(closure.get(k) != v for k, v in common.items())
            or closure.get("first_start_sha256") != file_digest(paths["luna_first_start"])
            or closure.get("independent_performance_validation") is not False
            or any(closure.get(k) is not True for k in ("operator_bounded_acceptance",
                    "received_cohort_audited_with_explicit_raw_attribution_limit", "raw_attribution_limit_preserved",
                    "all_started_calls_reconciled", "owned_worker_absence_verified"))):
        raise InfrastructureError("Actual received Luna first-start/closure/audit/reconciliation/worker absence required")
    for key in ("archive", "audit", "reconciliation", "owned_worker_absence"):
        artifact(closure.get(key))
    audit = read_json(artifact(closure["audit"]))
    if (audit.get("schema") != "hpc-forest-primes-r2max-readonly-audit-v1"
            or audit.get("scope_id") != "hpc-forest-primes-native-max-r1"
            or any(audit.get(k) != v for k, v in common.items())
            or audit.get("preparation_manifest_sha256") != PREPARATION_MANIFEST_SHA256
            or audit.get("received_cohort_audited_with_explicit_raw_attribution_limit") is not True
            or audit.get("verified") is not False
            or audit.get("independent_raw_stdout_per_candidate_verified") is not False
            or audit.get("independent_performance_audit_verified") is not False):
        raise InfrastructureError("Bounded Luna receipt must preserve the actual audit's explicit raw attribution limit")


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise InfrastructureError("Missing, linked or oversized R2 JSON artifact")
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise InfrastructureError("R2 receipt must be a JSON object")
    return value


def artifact(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise InfrastructureError("Artifact requires an exact absolute path and SHA-256")
    path = Path(ref["path"])
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])
            or file_digest(path) != ref["sha256"]):
        raise InfrastructureError("Missing or changed R2 admission artifact")
    return path


def verify_runtime(source_zip):
    """Actual executing project files must equal the newly admitted derivative ZIP."""
    root = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(source_zip) as archive:
        files = {}
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if (item.is_dir() or name.parts[0] != "HPC-Forest" or ".." in name.parts
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise InfrastructureError("Unsafe R2 source ZIP")
            key = name.relative_to("HPC-Forest").as_posix()
            if key in files:
                raise InfrastructureError("Duplicate R2 source ZIP member")
            files[key] = archive.read(item)
    local = {p.relative_to(root).as_posix(): p for p in root.rglob("*")
             if p.is_file() and not any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
                                       for part in p.relative_to(root).parts)}
    if files.keys() != local.keys() or any(local[n].is_symlink() or local[n].read_bytes() != raw
                                          for n, raw in files.items()):
        raise InfrastructureError("Executing R2 runtime differs from its admitted source ZIP")


def deadline_guard(now=None):
    if (time.time() if now is None else now) + MAX_ALLOCATION_SECONDS + RECEIPT_RESERVE_SECONDS >= DEADLINE:
        raise InfrastructureError("Insufficient exclusive deadline reserve; recheck after waiting")


def allocation_guard():
    """No subprocess or channel may be created before this exact allocated target gate."""
    env = os.environ
    required = {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
                "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}
    if (platform.system() != "Linux" or platform.machine().lower() not in {"aarch64", "arm64"}
            or not env.get("SLURM_JOB_ID", "").isdigit()
            or any(env.get(key) != value for key, value in required.items())
            or any(env.get(key, "") not in {"", "0"} for key in
                   ("SLURM_GPUS", "SLURM_GPUS_PER_NODE", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS", "CUDA_VISIBLE_DEVICES"))
            or not hasattr(os, "sched_getaffinity") or len(os.sched_getaffinity(0)) != 4):
        raise InfrastructureError("R2 requires its own Linux ARM64 Slurm 1-node/1-task/4-CPU/16-GiB/0-GPU allocation")
    deadline_guard()
    return {"job_id": env["SLURM_JOB_ID"], "architecture": platform.machine().lower(),
            "nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0,
            "affinity_cpu_ids": sorted(os.sched_getaffinity(0)), "affinity_cpu_count": 4}


def verify_qualification_members(value, read_member, data):
    required = {"reference-build/compiler-command.json", "reference-build/compiler.stdout",
                "reference-build/compiler.stderr", "reference-build/solution",
                "source/src/model-view/primetest.c", "source/Makefile", "source/run.sh",
                "validation/contract_tool.py", "validation/contract.json",
                "certified-preparation-receipt.json", "execution-contract.json"}
    if not required <= set(value.get("prepared_files", {})):
        raise InfrastructureError("Final qualification lacks actual build/source/contract evidence")
    import hashlib
    source = read_member("source/src/model-view/primetest.c")
    if hashlib.sha256(source).hexdigest() != REFERENCE_SHA256:
        raise InfrastructureError("Qualification did not compile the unchanged official C")
    command = json.loads(read_member("reference-build/compiler-command.json"))
    original = PurePosixPath(value["prepared_root"])
    if not original.is_absolute() or ".." in original.parts or "\\" in str(original):
        raise InfrastructureError("Qualification original ARM64 prepared path must be absolute POSIX")
    argv = command.get("argv", [])
    expected = [argv[0] if argv else "", "-I", str(original / "source/src"),
                str(original / "source/src/model-view/primetest.c"), *COMPILER_FLAGS,
                "-o", str(original / "reference-build/solution")]
    if (not argv or not PurePosixPath(argv[0]).is_absolute() or argv != expected
            or command.get("compiler_flags") != COMPILER_FLAGS or value.get("compiler_command") != command):
        raise InfrastructureError("Actual compiler command does not prove final flags and official source")
    if json.loads(read_member("execution-contract.json")) != specification(data):
        raise InfrastructureError("Actual execution contract differs from the twelve certified cases")
    from . import contracts
    if read_member("validation/contract_tool.py") != Path(contracts.__file__).read_bytes():
        raise InfrastructureError("Allocated protected checker differs from the admitted privacy-fixed source")
    resolved = json.loads(read_member("validation/contract.json"))
    rows = verify_resolved_values(resolved, data, lambda name: read_member("validation/" + name))
    preparation = json.loads(read_member("certified-preparation-receipt.json"))
    binary = read_member("reference-build/solution")
    binary_sha = hashlib.sha256(binary).hexdigest()
    if (len(binary) < 64 or binary[:6] != b"\x7fELF\x02\x01" or binary[18:20] != b"\xb7\x00"
            or value.get("reference_binary_sha256") != binary_sha
            or preparation.get("reference_binary_sha256") != binary_sha
            or preparation.get("certified_expected_compared_byte_for_byte") is not True
            or preparation.get("compiler_flags") != COMPILER_FLAGS
            or preparation.get("certified_expected_rows") != rows or value.get("certified_expected_rows") != rows
            or preparation.get("native_model_calls") != 0
            or preparation.get("calibration") is not False):
        raise InfrastructureError("Final qualification binary or certified byte comparison evidence missing")


def verify_qualification(value, binding, *, prepared=True, package=None):
    allocation = value.get("allocation", {})
    if (value.get("compiler_flags") != COMPILER_FLAGS
            or value.get("reference_source_sha256") != REFERENCE_SHA256
            or value.get("reference_outputs_all_certified_bytes") is not True
            or value.get("unique_certified_cases") != 12 or value.get("native_model_calls") != 0
            or allocation.get("architecture") not in {"aarch64", "arm64"}
            or any(allocation.get(k) != v for k, v in {"nodes": 1, "tasks": 1, "cpus_per_task": 4,
                                                       "memory_mib": 16384, "gpus": 0}.items())
            or not str(allocation.get("job_id", "")).isdigit()
            or value.get("source_zip_sha256") != binding):
        raise InfrastructureError("Final allocated contract flags/bytes/zero-inference/allocation proof missing")
    if not prepared:
        # Local worker must still pass the archived reception gate below; booleans alone cannot admit it.
        return
    root = Path(value.get("prepared_root", ""))
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise InfrastructureError("Allocated prepared root unavailable")
    files = value.get("prepared_files")
    if not isinstance(files, dict) or not files:
        raise InfrastructureError("Allocated prepared inventory missing")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if actual != set(files):
        raise InfrastructureError("Allocated preparation has extra or missing files")
    for name, expected in files.items():
        path = root / name
        if (PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name
                or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve())
                or file_digest(path) != expected):
            raise InfrastructureError("Allocated prepared bytes changed")
    verify_qualification_members(value, lambda name: (root / name).read_bytes(), verify_preparation(package))
    trace_root = root.parent / "official-evaluator-trace"
    trace_files = value.get("official_evaluator_trace_files", {})
    actual_trace = {p.relative_to(trace_root).as_posix(): file_digest(p) for p in trace_root.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts}
    if not trace_files or actual_trace != trace_files:
        raise InfrastructureError("Real official Evaluator trace inventory is missing or changed")
    verify_trace_members(value, lambda name: (trace_root / name).read_bytes(),
                         read_prepared_member=lambda name: (root / name).read_bytes())


def verify_trace_members(value, read_member, *, read_prepared_member=None):
    from .r2max_archive_trace import verify_archive_trace
    return verify_archive_trace(value, read_member, read_prepared_member=read_prepared_member)


def verify_reception(value, qualification_path, package):
    """Both environments verify the actual received archive and its independently hashed audit."""
    import hashlib
    qualification = read_json(qualification_path)
    if value.get("qualification_sha256") != file_digest(qualification_path):
        raise InfrastructureError("Reception is unrelated to the exact final qualification")
    archive_path, audit_path = artifact(value.get("archive")), artifact(value.get("audit"))
    audit = read_json(audit_path)
    expected = {"schema": "hpc-forest-primes-r2max-allocated-contract-reception-audit-v1",
                "scope_id": SCOPE, "verified": True, "source_zip_sha256": value["source_zip_sha256"],
                "plan_sha256": value["plan_sha256"], "preparation_manifest_sha256": PREPARATION_MANIFEST_SHA256,
                "qualification_sha256": file_digest(qualification_path), "archive_sha256": file_digest(archive_path),
                "all_members_regular_unique": True, "restored_files_byte_identical": True,
                "actual_compiler_command_verified": True, "certified_twelve_case_contract_verified": True,
                "native_model_calls": 0}
    if any(audit.get(k) != v for k, v in expected.items()):
        raise InfrastructureError("Exact allocated-contract reception audit missing")
    members, total = {}, 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or ".." in name.parts or not name.parts
                    or name.parts[0] != "qualification" or len(members) >= 1000):
                raise InfrastructureError("Unsafe qualification reception archive")
            key = name.relative_to("qualification").as_posix()
            total += member.size
            if key in members or total > 64 * 1024 * 1024:
                raise InfrastructureError("Duplicate or oversized qualification reception")
            stream = archive.extractfile(member)
            members[key] = stream.read()
    files = qualification.get("prepared_files", {})
    trace_files = qualification.get("official_evaluator_trace_files", {})
    expected_names = {"qualification.json", *("prepared/" + name for name in files),
                      *("official-evaluator-trace/" + name for name in trace_files)}
    if (set(members) != expected_names
            or hashlib.sha256(members.get("qualification.json", b"")).hexdigest() != file_digest(qualification_path)):
        raise InfrastructureError("Reception archive does not contain the exact qualified inventory")
    for name, expected_sha in files.items():
        if hashlib.sha256(members["prepared/" + name]).hexdigest() != expected_sha:
            raise InfrastructureError("Received qualified bytes differ from the audited inventory")
    for name, expected_sha in trace_files.items():
        if hashlib.sha256(members["official-evaluator-trace/" + name]).hexdigest() != expected_sha:
            raise InfrastructureError("Received official Evaluator trace bytes differ")
    verify_trace_members(qualification, lambda name: members["official-evaluator-trace/" + name],
                         read_prepared_member=lambda name: members["prepared/" + name])
    verify_qualification_members(qualification, lambda name: members["prepared/" + name], verify_preparation(package))


def validate_receipt(path: Path, required_jobs: set[str], *, runtime=True, prepared=True,
                     initial_lane=True):
    data = read_json(path)
    model, session = selected_identity(data)
    if set(data) != AUTHORIZATION_FIELDS:
        raise InfrastructureError("R2 authorization has missing or unknown fields")
    if (data.get("schema") != "hpc-forest-primes-r2max-authorization-v2"
            or data.get("scope_id") != SCOPE or required_jobs != {SCOPE}
            or data.get("verified") is not True
            or type(data.get("expires_at")) not in {int, float} or data["expires_at"] <= time.time()
            or not data.get("user_messages") or data.get("old_candidates_imported") is not False
            or data.get("operator_algorithm_advice") is not False
            or data.get("native_calls_started_at_authorization") != 0
            or not str(data.get("job_id", "")).isdigit()):
        raise InfrastructureError("R2 MAX authorization is missing, expired, unrelated or not verified")
    deadline_guard()
    refs = data.get("artifacts", {})
    if set(refs) != ARTIFACTS:
        raise InfrastructureError("Every exact R2 admission artifact is required")
    paths = {key: artifact(ref) for key, ref in refs.items()}
    source_sha = refs["source_zip"]["sha256"]
    if refs["preparation_manifest"]["sha256"] != PREPARATION_MANIFEST_SHA256:
        raise InfrastructureError("Unreviewed preparation manifest")
    plan = read_json(paths["plan"])
    if (plan.get("schema") != "hpc-forest-primes-native-max-plan-v2" or plan.get("scope_id") != SCOPE
            or plan.get("source_zip_sha256") != source_sha
            or plan.get("preparation_manifest_sha256") != PREPARATION_MANIFEST_SHA256
            or plan.get("cells") != CELLS or plan.get("efforts") != [EFFORT]
            or plan.get("luna_source_zip_sha256") != LUNA_SOURCE
            or plan.get("maximum_native_workers_total") != MAXIMUM_NATIVE_WORKERS
            or plan.get("maximum_cells_per_authorization") != 1
            or plan.get("worker_lane_contract") != PLAN_CONTRACT
            or plan.get("automatic_extension") is not False):
        raise InfrastructureError("R2 source/plan binding changed")
    verify_luna_release(paths)
    review = read_json(paths["preparation_review"])
    if (review.get("schema") != "hpc-forest-primes-certified-max-independent-final-review-v1"
            or review.get("blocking_findings") != []
            or review.get("package", {}).get("manifest_sha256") != PREPARATION_MANIFEST_SHA256):
        raise InfrastructureError("Independent finite preparation review missing")
    for key, schema in SCHEMAS.items():
        item = read_json(paths[key])
        if set(item) - (COMMON_PROOF_FIELDS | PROOF_FIELDS[key]):
            raise InfrastructureError("Unknown fields in closed R2 proof: " + key)
        if (item.get("schema") != schema or item.get("scope_id") != SCOPE
                or item.get("verified") is not True or item.get("source_zip_sha256") != source_sha
                or item.get("preparation_manifest_sha256") != PREPARATION_MANIFEST_SHA256
                or item.get("plan_sha256") != refs["plan"]["sha256"]):
            raise InfrastructureError("Missing verified exact-scope R2 proof: " + key)
        if key == "allocated_contract_qualification":
            verify_qualification(item, source_sha, prepared=prepared, package=paths["preparation_manifest"].parent)
        elif key == "allocated_contract_reception":
            verify_reception(item, paths["allocated_contract_qualification"], paths["preparation_manifest"].parent)
        elif key == "transport_admission":
            if (item.get("model") != model or item.get("effort") != EFFORT
                    or item.get("session_id") != session or item.get("job_id") != data["job_id"]
                    or item.get("native_model_calls") != 0
                    or item.get("normal_first_call_proved") is not False
                    or item.get("cli_tools_disabled") is not True):
                raise InfrastructureError("Transport admission must be pre-call and exact selected MAX cell")
        elif key == "cli_identity":
            if (not isinstance(item.get("version"), str) or not item["version"]
                    or not isinstance(item.get("executable_path"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item.get("executable_sha256", ""))
                    or not re.fullmatch(r"[0-9a-f]{64}", item.get("task_cli_policy_sha256", ""))
                    or item.get("source_execution_allowed") is not False):
                raise InfrastructureError("Immutable CLI identity metadata missing")
        elif key == "worker_lane_admission":
            verify_lane_admission(item, cell_binding(data), initial=initial_lane)
        elif key == "integration_review":
            if item.get("neutral_tests_passed") is not True or item.get("blocking_findings") != []:
                raise InfrastructureError("R2 integration review has unresolved findings")
        elif key in {"extension_admission", "session_freshness"}:
            if (item.get("model") != model or item.get("effort") != EFFORT
                    or item.get("session_id") != session or item.get("job_id") != data["job_id"]):
                raise InfrastructureError("Extension/freshness proof is for a different cell")
            if key == "extension_admission":
                if (item.get("luna_first_start_sha256") != file_digest(paths["luna_first_start"])
                        or item.get("luna_closure_sha256") != file_digest(paths["luna_closure"])
                        or item.get("maximum_native_workers") != MAXIMUM_NATIVE_WORKERS
                        or item.get("automatic_extension") is not False
                        or any(item.get(k) is not True for k in
                               ("human_max_only", "one_cell_only", "all_prior_calls_reconciled"))):
                    raise InfrastructureError("Explicit single-cell extension after audited Luna required")
            elif (item.get("native_calls_started_at_admission") != 0
                    or any(item.get(k) is not True for k in ("verified_no_prior_claims", "new_cache", "new_registry"))
                    or not item.get("observed_at")):
                raise InfrastructureError("No fresh unused cell/session/cache/registry proof")
    remote = PurePosixPath(data.get("remote_root", ""))
    if not remote.is_absolute() or ".." in remote.parts or remote.name != SCOPE + "-" + session:
        raise InfrastructureError("R2 root must be fresh, absolute, and session-bound")
    if runtime:
        verify_runtime(paths["source_zip"])
    return data


def install_identity(receipt: Path, *, prepared=True):
    frozen_receipt_sha = file_digest(receipt)
    authorization = validate_receipt(receipt, {SCOPE}, prepared=prepared)
    if file_digest(receipt) != frozen_receipt_sha:
        raise InfrastructureError("R2 authorization changed during its initial admission")
    frozen_binding = cell_binding(authorization)
    frozen_artifacts = {key: dict(ref) for key, ref in authorization["artifacts"].items()}
    model, session = selected_identity(authorization)
    from . import codex_mailbox, codex_process, codex_worker
    for module in (codex_mailbox, codex_process, codex_worker):
        module.MODEL, module.EFFORT = model, EFFORT

    def gate(path, required_jobs):
        if file_digest(Path(path)) != frozen_receipt_sha:
            raise InfrastructureError("R2 authorization replaced after initial admission")
        # This gate exists only after the initial fresh admission and frozen
        # receipt/binding capture above. It grants no new worker or session.
        fresh = validate_receipt(path, required_jobs, prepared=prepared, initial_lane=False)
        if (file_digest(Path(path)) != frozen_receipt_sha or cell_binding(fresh) != frozen_binding
                or fresh["artifacts"] != frozen_artifacts):
            raise InfrastructureError("R2 cell/admission/CLI binding changed")
        # Rehash every immutable artifact, including CLI proof, source and admissions.
        for ref in frozen_artifacts.values():
            artifact(ref)
        return fresh
    codex_process.check_dependencies = gate
    codex_worker.check_dependencies = gate
    return authorization
