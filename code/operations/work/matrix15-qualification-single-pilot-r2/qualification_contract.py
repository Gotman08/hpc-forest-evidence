"""Closed baseline-only Q15 policy; never a native model authorization."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import re
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SCOPE = "hpc-forest-matrix15-baseline-qualification-r1"
SUBJECTS = ("2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
            "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
            "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci")
PREP_SHA = "829a1e96066218f08724f684f7f006935ba6f39c146141a7e918fc62e2f73963"
R1_SHA = "fd36a6c9bdd35845834053d92b83fa58c688c02f0b6443b7a2edfded96956bdf"
HARNESS_SHA = "8e98175f7f420af444df50c6029cd007662645829107608c1d357913f988d2b9"
PARENT_RUNTIME_MANIFEST_SHA256 = "73ef7751b10368d50f831af67aa7467b0bdb189252b5fa5df94c69f82896f152"
SINGLE_PILOT_PROTOCOL_SHA256 = "ae2ccbb8d10f54d022bb95248412d0fba8751b8f1c97196336e6e6b9f1fb08b2"
SHA = re.compile(r"[0-9a-f]{64}\Z")
DEADLINE = datetime(2026, 10, 31, 23, tzinfo=UTC).timestamp()
POLICY_FIELDS = {"mode", "qualification_binding", "source_runtime_sha256",
                 "subject_contract_sha256", "qualification_protocol_sha256"}
BINDING_FIELDS = {"schema", "scope_id", "subject_id", "job_id", "remote_root", "seed",
                  "prepared_manifest_sha256", "r1_contract_sha256", "native_authorization"}


class Refusal(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Refusal(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(raw):
    need(isinstance(raw, bytes) and len(raw) <= 16 * 1024**2, "Bounded JSON bytes required")

    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "Duplicate JSON member")
            result[key] = value
        return result

    def constant(_value):
        raise Refusal("Nonfinite JSON value")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def data(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def relative(value):
    need(isinstance(value, str) and value and "\\" not in value and ":" not in value, "Unsafe relative member")
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value and ".." not in path.parts
         and not any(part in {".git", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts),
         "Source/candidate/cache or traversal member refused")
    return path


def artifact(ref):
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}
         and isinstance(ref["sha256"], str) and SHA.fullmatch(ref["sha256"]), "Closed actual file/SHA reference required")
    path = Path(ref["path"])
    need(path.is_absolute() and path.is_file() and not path.is_symlink()
         and all(not parent.is_symlink() for parent in path.parents), "Physical absolute evidence file required")
    raw = path.read_bytes()
    need(sha(raw) == ref["sha256"], "Actual referenced bytes changed")
    return path, raw


def qualification_command_stream_policy(config):
    """Accepted only in the separately sealed qualification source copy."""
    need(type(config) is dict, "Qualification configuration must be an object")
    if "execution_provenance" not in config:
        return None
    policy = config["execution_provenance"]
    need(type(policy) is dict and set(policy) == POLICY_FIELDS and policy["mode"] == "command-stream-v1",
         "Explicit Q15 qualification policy required; native cell bindings are forbidden")
    protocol = config.get("protocol", {})
    need(type(protocol) is dict and protocol.get("private_execution_audit", False) is False,
         "Qualification command streams cannot claim private case-v2 provenance")
    binding = policy["qualification_binding"]
    need(type(binding) is dict and set(binding) == BINDING_FIELDS
         and binding["schema"] == "hpc-forest-matrix15-qualification-binding-v1"
         and binding["scope_id"] == SCOPE and binding["subject_id"] in SUBJECTS
         and type(binding["seed"]) is int and binding["seed"] == 23
         and binding["native_authorization"] is False
         and isinstance(binding["job_id"], str) and re.fullmatch("[1-9][0-9]*", binding["job_id"])
         and isinstance(binding["remote_root"], str) and binding["remote_root"].startswith("/")
         and ".." not in binding["remote_root"].split("/"), "Closed non-native Q15 identity required")
    need(binding["prepared_manifest_sha256"] == PREP_SHA
         and binding["r1_contract_sha256"] == policy["subject_contract_sha256"], "Exact R1 preparation/contract binding required")
    for key in ("source_runtime_sha256", "subject_contract_sha256", "qualification_protocol_sha256"):
        need(isinstance(policy[key], str) and SHA.fullmatch(policy[key]), "Qualification SHA field malformed")
    return copy.deepcopy(policy)


def allocation_guard(seconds, *, env=None, system=None, machine=None, affinity=None, now=None):
    env = os.environ if env is None else env
    system = platform.system() if system is None else system
    machine = platform.machine().lower() if machine is None else machine.lower()
    affinity = sorted(os.sched_getaffinity(0)) if affinity is None and hasattr(os, "sched_getaffinity") else affinity
    now = time.time() if now is None else now
    need(system == "Linux" and machine in {"aarch64", "arm64"}, "Q15 requires its own LinuxARM64 allocation")
    need(re.fullmatch("[1-9][0-9]*", env.get("SLURM_JOB_ID", "")), "Actual Q15 Slurm job required")
    need(all(env.get(key) == value for key, value in {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
        "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}.items()), "Q15 requires1node/1task/4CPU/16GiB")
    need(env.get("SLURM_RESTART_COUNT", "0") == "0" and env.get("CUDA_VISIBLE_DEVICES", "") == ""
         and all(env.get(key, "0") in {"", "0"} for key in
                 ("SLURM_GPUS", "SLURM_GPUS_PER_NODE", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS")), "Q15 zeroGPU/no replay required")
    need(isinstance(affinity, (tuple, list, set)) and len(set(affinity)) == 4, "Q15 requires exactly4effective CPUs")
    need(type(seconds) is int and 60 <= seconds <= 7200 and now + seconds + 120 + 10800 < DEADLINE,
         "Q15 duration plus collection and3hour reception/audit reserve exceeds exclusive deadline")
    return {"job_id": env["SLURM_JOB_ID"], "nodes": 1, "tasks": 1, "cpus_per_task": 4,
            "memory_mib": 16384, "gpus": 0, "affinity_cpu_ids": sorted(affinity), "machine": machine,
            "observed_utc": datetime.fromtimestamp(now, UTC).isoformat()}


def verify_source_bindings(plan, parent_manifest_raw, q_manifest_raw):
    """Verify the declared private source before any HPC/runtime import."""
    fields = {"schema", "parent_runtime_manifest_sha256", "q_runtime_manifest_sha256",
              "single_pilot_protocol_sha256"}
    binding = plan.get("source_bindings")
    need(type(binding) is dict and set(binding) == fields
         and binding["schema"] == "hpc-forest-Q15-single-pilot-source-binding-v1"
         and binding["parent_runtime_manifest_sha256"] == PARENT_RUNTIME_MANIFEST_SHA256
         and sha(parent_manifest_raw) == PARENT_RUNTIME_MANIFEST_SHA256
         and binding["single_pilot_protocol_sha256"] == SINGLE_PILOT_PROTOCOL_SHA256
         and sha(q_manifest_raw) == binding["q_runtime_manifest_sha256"],
         "Q15 plan is not bound to the reviewed single-pilot parent and actual Q runtime")
    return copy.deepcopy(binding)
