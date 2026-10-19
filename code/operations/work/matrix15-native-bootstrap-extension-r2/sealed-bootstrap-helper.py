"""Once-only ARM bootstrap; source verification precedes a bounded authorization wait.

The input is an operator preparation, never a research authorization.  This file
uses no controller, model, worker or Mother code before the exact authorization
has passed the unchanged native validator with runtime=True.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

SCOPE = "hpc-forest-matrix15-native-max-r2"
SESSION = "9a681c2826854a4b885e94c5e6243f0a"
CELL_KEY = "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23"
SHARED_ROOT = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared"
SCIENTIFIC_ROOT = "/gpfs/scratch/nimarano/" + SCOPE + "-" + SESSION
PYTHON = "/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python"
SOURCE_SHA256 = "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
RUNTIME_MANIFEST_SHA256 = "91684ae8d3d0457d81d049bf6e096c02601fdbdc67fc762fdf697bdc23c35f2b"
DEADLINE = datetime(2026, 10, 31, 23, tzinfo=UTC).timestamp()
ADMISSION_SECONDS, RUNNER_SECONDS = 600, 2700
MAX_FILE = 8 * 1024**2
MAX_ARCHIVE = 64 * 1024**2
MAX_TOTAL = 128 * 1024**2
MAX_MEMBERS = 4000
SHA = re.compile(r"[0-9a-f]{64}\Z")
BINDING_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
                  "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256",
                  "r1_contract_sha256"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(raw):
    need(isinstance(raw, bytes) and len(raw) <= MAX_FILE, "Bounded JSON bytes required")

    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_value):
        raise ValueError("Nonfinite JSON")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    need(type(value) is dict, "JSON object required")
    return value


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode()


def physical(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path
         and not any(item.is_symlink() for item in (path, *path.parents)),
         "Canonical existing nonlinked path required")
    return path


def absent(path):
    """lexists semantics: broken symlinks and any existing object are not absent."""
    try:
        Path(path).lstat()
    except FileNotFoundError:
        return True
    return False


def regular_bytes(path, limit=MAX_FILE):
    path = physical(path)
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "Bounded regular file required")
    raw = path.read_bytes()
    need(len(raw) == info.st_size and path.lstat().st_size == info.st_size,
         "File length changed while reading")
    return raw


def read_ref(ref, *, limit=MAX_FILE):
    need(type(ref) is dict and set(ref) == {"path", "sha256", "bytes"}
         and isinstance(ref["path"], str) and SHA.fullmatch(str(ref["sha256"]))
         and type(ref["bytes"]) is int and 0 <= ref["bytes"] <= limit,
         "Exact bounded path/SHA/bytes reference required")
    raw = regular_bytes(ref["path"], limit)
    need(len(raw) == ref["bytes"] and sha(raw) == ref["sha256"], "Referenced file bytes differ")
    return raw


def save(path, value):
    raw = encode(value)
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}


def canonical_member(name):
    need(isinstance(name, str) and name and len(name) <= 1024 and "\\" not in name and ":" not in name
         and all(ord(char) >= 32 for char in name), "Unsafe member name")
    path = PurePosixPath(name)
    need(path.parts and not path.is_absolute() and path.as_posix() == name and ".." not in path.parts
         and not any(part in {".git", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts),
         "Noncanonical/forbidden member name")
    return path


def read_archive(path, manifest):
    need(type(manifest) is dict and set(manifest) == {"schema", "files"}
         and manifest["schema"] == "hpc-forest-matrix15-shared-files-v1"
         and type(manifest["files"]) is dict and 1 <= len(manifest["files"]) <= MAX_MEMBERS,
         "Exact external shared inventory required")
    declared = manifest["files"]
    for name, ref in declared.items():
        canonical_member(name)
        need(type(ref) is dict and set(ref) == {"sha256", "bytes"}
             and SHA.fullmatch(str(ref["sha256"])) and type(ref["bytes"]) is int
             and 0 <= ref["bytes"] <= MAX_FILE, "Exact member SHA/bytes required")
    need("SHARED-FILES-MANIFEST.json" not in declared, "External inventory must not contain itself")
    material, folded, total = {}, set(), 0
    with tarfile.open(path, "r:gz") as archive:
        need(not archive.pax_headers, "Global PAX refused")
        for member in archive:
            canonical_member(member.name)
            need(member.type in {tarfile.REGTYPE, tarfile.AREGTYPE} and member.isfile()
                 and not member.issym() and not member.islnk() and not member.linkname
                 and not member.pax_headers and not member.sparse,
                 "Only regular members without links/PAX/sparse metadata allowed")
            need(member.name in declared and member.name not in material
                 and member.name.casefold() not in folded and len(material) < MAX_MEMBERS
                 and 0 <= member.size <= MAX_FILE, "Unknown/duplicate/excess/oversized member")
            total += member.size
            need(total <= MAX_TOTAL, "Shared archive exceeds uncompressed bound")
            stream = archive.extractfile(member)
            need(stream is not None, "Missing member stream")
            raw = stream.read(MAX_FILE + 1)
            need(len(raw) == member.size and declared[member.name] == {"sha256": sha(raw), "bytes": len(raw)},
                 "Member bytes differ from exact shared inventory")
            material[member.name] = raw
            folded.add(member.name.casefold())
        need(not archive.pax_headers, "Global PAX refused")
    need(set(material) == set(declared), "Shared archive inventory incomplete")
    return material


def inventory(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        need(not path.is_symlink(), "Linked shared member refused")
        if path.is_file():
            raw = regular_bytes(path)
            result[path.relative_to(root).as_posix()] = {"sha256": sha(raw), "bytes": len(raw)}
    return result


def extract_shared(root, material, declared):
    root = Path(root)
    physical(root.parent)
    need(absent(root), "Shared root already exists; preserve without repair/replay")
    root.mkdir(exist_ok=False)
    for name, raw in material.items():
        path = root.joinpath(*canonical_member(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    need(inventory(root) == declared, "Written shared inventory differs")


def validate_input(value):
    fields = {"schema", "evidence_origin", "native_execution_authorized_by_this_input", "shared_root",
              "scientific_root", "admission_root", "python", "shared_archive", "shared_files_manifest",
              "binding_without_job_id", "source_zip_relative", "runtime_manifest_relative", "plan_relative",
              "maximum_admission_seconds", "maximum_runner_seconds", "scientific_wall_seconds",
              "confirmation_seconds", "collection_reserve_seconds"}
    need(type(value) is dict and set(value) == fields
         and value["schema"] == "hpc-forest-matrix15-bootstrap-input-v1"
         and value["evidence_origin"] == "operator-prepared"
         and value["native_execution_authorized_by_this_input"] is False, "Exact prepared bootstrap input required")
    need(value["shared_root"] == SHARED_ROOT and value["scientific_root"] == SCIENTIFIC_ROOT
         and value["admission_root"] == SCIENTIFIC_ROOT + "-admission" and value["python"] == PYTHON,
         "Only the expressly owned first-cell deployment is allowed")
    expected_numbers = {"maximum_admission_seconds": ADMISSION_SECONDS, "maximum_runner_seconds": RUNNER_SECONDS,
                        "scientific_wall_seconds": 1800, "confirmation_seconds": 120,
                        "collection_reserve_seconds": 180}
    need(all(type(value[key]) is int and value[key] == expected for key, expected in expected_numbers.items()),
         "Separate admission/scientific/confirmation/collection bounds differ")
    binding = value["binding_without_job_id"]
    need(type(binding) is dict and set(binding) == BINDING_FIELDS - {"job_id"}
         and all(isinstance(item, str) and item for item in binding.values()), "Exact upstream eleven-field binding required")
    fixed = {"scope_id": SCOPE, "cell_key": CELL_KEY, "subject_id": "2020-quicksort", "model": "gpt-6-luna",
             "effort": "max", "session_id": SESSION, "remote_root": SCIENTIFIC_ROOT,
             "source_zip_sha256": SOURCE_SHA256}
    need(all(binding[key] == item for key, item in fixed.items())
         and all(SHA.fullmatch(binding[key]) for key in ("plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256")),
         "First Luna/MAX/quicksort binding changed")
    for key in ("source_zip_relative", "runtime_manifest_relative", "plan_relative"):
        canonical_member(value[key])
    need(value["source_zip_relative"] == "native-source.zip"
         and value["runtime_manifest_relative"] == "runtime-manifest.json"
         and value["plan_relative"] == "plan-60-v2.json", "Shared source/runtime/plan paths changed")
    return value


def allocation_guard(*, env=None, system=None, machine=None, affinity=None, now=None):
    env = os.environ if env is None else env
    system = platform.system() if system is None else system
    machine = platform.machine().lower() if machine is None else machine.lower()
    affinity = sorted(os.sched_getaffinity(0)) if affinity is None and hasattr(os, "sched_getaffinity") else affinity
    now = time.time() if now is None else now
    need(system == "Linux" and machine in {"aarch64", "arm64"}
         and re.fullmatch(r"[1-9][0-9]*", env.get("SLURM_JOB_ID", "")), "Actual LinuxARM64 Slurm allocation required")
    need(all(env.get(key) == item for key, item in {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
         "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}.items())
         and env.get("SLURM_RESTART_COUNT", "0") == "0"
         and all(env.get(key, "") in {"", "0"} for key in
                 ("SLURM_GPUS", "SLURM_GPUS_PER_NODE", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS", "CUDA_VISIBLE_DEVICES")),
         "Exact1node1task4CPU16GiB0GPU without restart required")
    need(isinstance(affinity, (list, tuple, set)) and len(set(affinity)) == 4
         and all(type(cpu) is int and cpu >= 0 for cpu in affinity), "Four actual CPU affinity ids required")
    need(type(now) in {int, float} and math.isfinite(now) and now + 3600 + 10800 < DEADLINE,
         "Allocation1h plus reception3h exceeds exclusive deadline")
    return {"job_id": env["SLURM_JOB_ID"], "architecture": machine, "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0,
            "affinity_cpu_ids": sorted(affinity), "affinity_cpu_count": 4}


def native_api(shared):
    # All 127 source files have already been SHA-checked by the external tar inventory.
    # This module imports only native guards/contracts/core; Mother is imported by the runner after admission.
    sys.path.insert(0, str(Path(shared) / "project" / "src"))
    return importlib.import_module("hpc_forest.native_matrix15")


def interpreter_guard():
    need(Path(sys.executable).absolute() == Path(PYTHON), "Exact existing ARM venv interpreter required")
    need(importlib.metadata.version("treequest") == "0.3.2", "Actual pinned TreeQuest0.3.2 required")
    expected = {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE",
                "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}
    need(all(os.environ.get(key) == value for key, value in expected.items()), "Scientific environment differs")
    cache = SCIENTIFIC_ROOT + "-bootstrap-pycache-must-remain-absent"
    need(os.environ.get("PYTHONPYCACHEPREFIX") == cache and absent(cache), "Fresh owned absent pycache prefix required")


def parse_scontrol_deadline(stdout, offset, job_id, now):
    need(isinstance(stdout, str) and len(stdout) <= 65536 and isinstance(offset, str)
         and re.fullmatch(r"[+-](?:0[0-9]|1[0-4])[0-5][0-9]", offset), "Bounded Slurm output and actual timezone offset required")
    fields = {}
    for key, value in re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9]*)=([^\s]+)", stdout):
        need(key not in fields, "Ambiguous repeated Slurm field")
        fields[key] = value
    need(fields.get("JobId") == job_id and fields.get("TimeLimit") in {"01:00:00", "1:00:00"},
         "Actual exact job/one-hour TimeLimit required")
    minutes = (int(offset[1:3]) * 60 + int(offset[3:])) * (1 if offset[0] == "+" else -1)
    zone = timezone(timedelta(minutes=minutes))
    instants = []
    for key in ("StartTime", "EndTime"):
        raw = fields.get(key, "")
        need(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", raw), "Actual unambiguous scheduler timestamps required")
        instants.append(datetime.fromisoformat(raw).replace(tzinfo=zone).timestamp())
    start, end = instants
    need(start <= now < end <= now + 3600 and end - start == 3600,
         "Scheduler times conflict with current offset or one-hour allocation")
    return end


def allocation_outer_deadline(allocation, admission_root, *, env=None, now=None):
    """Require real Slurm end epoch, or retain exact read-only scontrol/date evidence."""
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    value = env.get("SLURM_JOB_END_TIME", "")
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        observation = {"schema": "hpc-forest-matrix15-scheduler-deadline-observation-v1",
                       "origin": "SLURM_JOB_END_TIME", "job_id": allocation["job_id"],
                       "value": value, "observed_at": now}
        save(Path(admission_root) / "scheduler-deadline-observation.json", observation)
        end = int(value)
    else:
        command = ["scontrol", "show", "job", "-o", allocation["job_id"]]
        environment = dict(env, LC_ALL="C", SLURM_TIME_FORMAT="standard")
        process = subprocess.run(command, env=environment, capture_output=True, text=True, check=False, timeout=10)
        offset_process = subprocess.run(["date", "+%z"], env=environment, capture_output=True, text=True, check=False, timeout=5)
        observation = {"schema": "hpc-forest-matrix15-scheduler-deadline-observation-v1",
                       "origin": "scontrol-show-job", "job_id": allocation["job_id"], "argv": command,
                       "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
                       "timezone_argv": ["date", "+%z"], "timezone_returncode": offset_process.returncode,
                       "timezone_stdout": offset_process.stdout, "timezone_stderr": offset_process.stderr,
                       "observed_at": now}
        # Preserve raw observations before any parsing; do not retry a malformed/ambiguous reply.
        save(Path(admission_root) / "scheduler-deadline-observation.json", observation)
        need(process.returncode == 0 and offset_process.returncode == 0
             and len(process.stdout) + len(process.stderr) <= 65536, "Actual scheduler deadline read failed")
        end = parse_scontrol_deadline(process.stdout, offset_process.stdout.strip(), allocation["job_id"], now)
    need(env.get("SLURM_JOB_ID") == allocation["job_id"] and now < end <= now + 3600,
         "Actual scheduler deadline is absent/past/outside1h allocation")
    return end


def verify_sources(shared, config):
    shared = Path(shared)
    source = shared / config["source_zip_relative"]
    runtime = shared / config["runtime_manifest_relative"]
    plan = shared / config["plan_relative"]
    need(sha(regular_bytes(source)) == SOURCE_SHA256
         and sha(regular_bytes(runtime)) == RUNTIME_MANIFEST_SHA256
         and sha(regular_bytes(plan)) == config["binding_without_job_id"]["plan_sha256"],
         "Native source/runtime/plan pins differ")
    runtime_value = read_json(regular_bytes(runtime))
    need(len(runtime_value) == 127, "Exactly sealed127-file native runtime required")
    for name in runtime_value:
        canonical_member(name)
    actual = {name: {"sha256": expected, "bytes": len(regular_bytes(shared / "project" / name))}
              for name, expected in runtime_value.items()}
    need(inventory(shared / "project") == actual, "Native127-file project inventory differs")
    return source, runtime


def scientific_paths(binding):
    root = binding["remote_root"]
    output = root + "/results-" + binding["job_id"]
    return {"root": root, "mailbox": output + "/mailbox",
            "registry": output + "/" + binding["subject_id"] + "/registry.sqlite3"}


def marker(binding, allocation, admission_root, admission_started_at, outer_deadline, *, now=None):
    paths = scientific_paths(binding)
    observations = {"scientific_" + key + "_observed_absent": absent(path) for key, path in paths.items()}
    need(all(observations.values()), "Scientific root/mailbox/registry already exists; no replay")
    return {"schema": "hpc-forest-matrix15-zero-model-allocation-marker-v1", "binding": binding,
            "allocation": allocation, "native_model_calls": 0, "source_runtime_verified": True,
            "observed_at": time.time() if now is None else now, "admission_root": str(admission_root),
            "admission_started_at": admission_started_at, "admission_deadline": admission_started_at + ADMISSION_SECONDS,
            "execution_deadline": admission_started_at + ADMISSION_SECONDS + RUNNER_SECONDS,
            "allocation_outer_deadline": outer_deadline,
            "scientific_paths": paths, **observations}


def read_authorization_commit(admission_root):
    admission_root = Path(admission_root)
    commit_path = admission_root / "authorization.sha256.json"
    auth_path = admission_root / "authorization.json"
    commit_raw = regular_bytes(commit_path)
    commit = read_json(commit_raw)
    need(set(commit) == {"sha256", "bytes", "authorization"} and commit["authorization"] == str(auth_path)
         and SHA.fullmatch(str(commit["sha256"])) and type(commit["bytes"]) is int
         and 0 < commit["bytes"] <= MAX_FILE, "Exact authorization commit required")
    auth_raw = regular_bytes(auth_path)
    need(sha(auth_raw) == commit["sha256"] and len(auth_raw) == commit["bytes"], "Authorization/commit bytes differ")
    return auth_path, auth_raw, commit_path, commit_raw


def wait_for_authorization(admission_root, started_monotonic, *, monotonic=time.monotonic, sleep=time.sleep):
    """The clock starts before preparation; no upload, parse or verification resets it."""
    while True:
        remaining = ADMISSION_SECONDS - (monotonic() - started_monotonic)
        need(remaining > 0, "Original600s admission clock expired; preserve without execution")
        if not absent(Path(admission_root) / "authorization.sha256.json"):
            return read_authorization_commit(admission_root)
        sleep(min(2.0, remaining))


def runner_argv(config, authorization):
    return [config["python"], "-B", str(Path(config["shared_root"]) / "project/examples/marathon22/forest_matrix15.py"),
            "--root", config["scientific_root"], "--shared", config["shared_root"],
            "--authorization", str(authorization), "--cell-key", CELL_KEY]


def run_native(argv, environment, stdout, stderr, maximum_seconds):
    """Only this newly created process group can be signalled on the outer bound."""
    need(type(maximum_seconds) in {int, float} and math.isfinite(maximum_seconds)
         and 0 < maximum_seconds <= RUNNER_SECONDS, "Bounded original runner window required")
    with subprocess.Popen(argv, env=environment, stdout=stdout, stderr=stderr, start_new_session=True) as process:
        try:
            return process.wait(timeout=maximum_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise


def main(argv=None):
    started_monotonic, started_at = time.monotonic(), time.time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args(argv)
    raw = regular_bytes(args.input)
    need(SHA.fullmatch(args.input_sha256) and sha(raw) == args.input_sha256, "Bootstrap input SHA differs")
    config = validate_input(read_json(raw))
    allocation = allocation_guard()
    interpreter_guard()
    binding = {**config["binding_without_job_id"], "job_id": allocation["job_id"]}
    shared, admission = Path(config["shared_root"]), Path(config["admission_root"])
    physical(admission.parent)
    need(absent(shared) and absent(admission) and all(absent(path) for path in scientific_paths(binding).values()),
         "Owned shared/admission/scientific target exists; no repair/replay")
    admission.mkdir(exist_ok=False)
    receipt = {"schema": "hpc-forest-matrix15-bootstrap-result-v1", "binding": binding,
               "bootstrap_started_at": started_at, "bootstrap_started_monotonic": started_monotonic,
               "maximum_admission_seconds": ADMISSION_SECONDS, "maximum_runner_seconds": RUNNER_SECONDS,
               "admission_deadline": started_at + ADMISSION_SECONDS,
               "execution_deadline": started_at + ADMISSION_SECONDS + RUNNER_SECONDS,
               "allocation_outer_deadline": None,
               "native_child_launch_attempted": False, "admission_accepted": False, "passed": False,
               "retry": False, "attempt": 1, "native_model_calls_before_authorization": 0}
    save(admission / "bootstrap-intent.json", {**receipt, "input": {"path": str(args.input), "sha256": args.input_sha256},
         "scientific_wall_seconds": 1800, "worker_wait_seconds": 600,
         "confirmation_seconds": 120, "collection_reserve_seconds": 180, "allocation": allocation,
         "source_zip_sha256": SOURCE_SHA256, "runtime_manifest_sha256": RUNTIME_MANIFEST_SHA256})
    try:
        outer_deadline = allocation_outer_deadline(allocation, admission)
        receipt["allocation_outer_deadline"] = outer_deadline
        need(started_at + ADMISSION_SECONDS + RUNNER_SECONDS + 10 < outer_deadline,
             "Actual allocation cannot contain original3300s envelope plus10s preservation")
        archive_raw = read_ref(config["shared_archive"], limit=MAX_ARCHIVE)
        manifest = read_json(read_ref(config["shared_files_manifest"]))
        # Read/hash the archive before creating sharedroot; extraction uses the same still-pinned file.
        material = read_archive(config["shared_archive"]["path"], manifest)
        need(sha(regular_bytes(config["shared_archive"]["path"], MAX_ARCHIVE)) == sha(archive_raw),
             "Archive changed during validation")
        extract_shared(shared, material, manifest["files"])
        source_path, runtime_path = verify_sources(shared, config)
        api = native_api(shared)
        api.verify_runtime(source_path, runtime_path)
        actual_allocation = api.allocation_guard()
        need(actual_allocation == allocation, "Native and bootstrap actual allocations differ")
        save(admission / "ZERO-MODEL-MARKER.json", marker(binding, allocation, admission, started_at, outer_deadline))
        auth_path, auth_raw, commit_path, commit_raw = wait_for_authorization(admission, started_monotonic)
        need(time.monotonic() - started_monotonic < ADMISSION_SECONDS, "Original admission clock expired before validation")
        authorization = api.validate_receipt(auth_path, {SCOPE}, runtime=True)
        need(api.cell_binding(authorization) == binding, "Accepted authorization binds another cell/job/source/plan")
        need(type(authorization.get("expires_at")) in {int, float}
             and time.time() < authorization["expires_at"] <= min(started_at + ADMISSION_SECONDS + RUNNER_SECONDS,
                                                                  outer_deadline, DEADLINE),
             "Authorization execution expiry exceeds original bound or actual allocation")
        need(regular_bytes(auth_path) == auth_raw and regular_bytes(commit_path) == commit_raw,
             "Authorization or commit changed during validation")
        need(time.monotonic() - started_monotonic < ADMISSION_SECONDS, "Original admission clock expired during validation")
        need(all(absent(path) for path in scientific_paths(binding).values()), "Scientific paths changed before runner launch")
        receipt.update(admission_accepted=True, authorization_sha256=sha(auth_raw),
                       admission_elapsed_seconds=time.monotonic() - started_monotonic)
        argv_child = runner_argv(config, auth_path)
        save(admission / "authorization-accepted.json", {**receipt, "argv": argv_child, "runtime_validated": True,
             "authorization_commit_sha256": sha(commit_raw), "observed_at": time.time()})
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="1")
        with (admission / "runner.stdout").open("xb") as stdout, (admission / "runner.stderr").open("xb") as stderr:
            maximum_seconds = min(RUNNER_SECONDS, started_monotonic + ADMISSION_SECONDS + RUNNER_SECONDS - time.monotonic())
            need(time.monotonic() - started_monotonic < ADMISSION_SECONDS and maximum_seconds > 0,
                 "Original admission/execution clock expired immediately before launch")
            receipt["native_child_launch_attempted"] = True
            returncode = run_native(argv_child, environment, stdout, stderr, maximum_seconds)
        receipt["native_child_returncode"] = returncode
        receipt["passed"] = returncode == 0
    except Exception as exc:  # noqa: BLE001 - preserve once-only negative, never repair or retry.
        receipt.update(error_type=type(exc).__name__, error=str(exc), passed=False)
    finally:
        receipt["bootstrap_elapsed_seconds"] = time.monotonic() - started_monotonic
        receipt["finished_at"] = time.time()
        save(admission / "bootstrap-result.json", receipt)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
