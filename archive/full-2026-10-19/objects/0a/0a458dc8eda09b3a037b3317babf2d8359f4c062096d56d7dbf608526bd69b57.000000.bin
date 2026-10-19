"""One allocated stdlib bootstrap for the sealed baseline-only Q15 package."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import stat
import subprocess
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path("/gpfs/scratch/nimarano/hpc-forest-q15-single-pilot-20261019-root-01")
ARCHIVE_NAME = "HPC-Forest-Q15-baseline-source-r1.tar.gz"
ARCHIVE_SHA256 = "6f30c842b161f23719c877f70684a58b796f8f724539282a2b99756e8ccdaf9d"
PLAN_SHA256 = "36c95aa92150239e126c95de05b596c445e20dc59d3bb68d3554ef09a7d46ad0"
PACKAGE_MANIFEST_SHA256 = "dc43083bb65d49fd477a7edcb56d675d77b7cdc9f4dfde04611e9715962baa45"
PARENT_RUNTIME_SHA256 = "6d93e23b0930ecfa4d66251f4542a08b140b80351873da8248c154937c8c971b"
Q_RUNTIME_SHA256 = "515ea767592a91fa8a5b19c6766f8f81eba1c5673a6572f3492401f9f29f7094"
PROTOCOL_SHA256 = "ae2ccbb8d10f54d022bb95248412d0fba8751b8f1c97196336e6e6b9f1fb08b2"
RUNNER_SHA256 = "978a17ee825a87500a5f6406023caabbd477bae5df6b80b276da1b72cc09ab29"
HELPER_SHA256 = "4549277cbf66e9140798e361b91f2b2572bf21de1a011bfe860ad6e28b2f65e6"
PYTHON = "/scratch_p/nimarano/hpc-forest-localmodels-20261015-r1/venv-r3/bin/python"
MAX_TOTAL_BYTES = 64 * 1024**2
MAX_FILE_BYTES = 8 * 1024**2
MEMBER_COUNT = 353
QUALIFICATION_SECONDS = 1800
DEADLINE = datetime(2026, 10, 31, 23, tzinfo=UTC).timestamp()
SHA = re.compile(r"[0-9a-f]{64}\Z")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(raw):
    need(isinstance(raw, bytes) and len(raw) <= MAX_FILE_BYTES, "Bounded JSON bytes required")

    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_value):
        raise ValueError("Nonfinite JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def canonical_member(name):
    need(isinstance(name, str) and name and len(name) <= 1024
         and all(ord(char) >= 32 for char in name) and "\\" not in name and ":" not in name,
         "Unsafe member name")
    path = PurePosixPath(name)
    need(bool(path.parts) and not path.is_absolute() and str(path) == name and ".." not in path.parts
         and not any(part in {".git", "__pycache__", ".pytest_cache", ".ruff_cache"} for part in path.parts),
         "Noncanonical or forbidden member")
    return path


def read_tar(path, *, expected_count=MEMBER_COUNT):
    need(type(expected_count) is int and 1 <= expected_count <= 1000, "Bounded expected member count required")
    material, folded, total = {}, set(), 0
    with tarfile.open(path, "r:gz") as archive:
        need(not archive.pax_headers, "Global PAX headers refused")
        for member in archive:
            name = canonical_member(member.name)
            need(member.type in {tarfile.REGTYPE, tarfile.AREGTYPE} and member.isfile()
                 and not member.issym() and not member.islnk() and not member.linkname
                 and not member.pax_headers and not member.sparse,
                 "Only regular members without PAX/link/sparse metadata allowed")
            need(member.name not in material and member.name.casefold() not in folded
                 and len(material) < expected_count and 0 <= member.size <= MAX_FILE_BYTES,
                 "Duplicate, excess or oversized member")
            total += member.size
            need(total <= MAX_TOTAL_BYTES, "Archive total exceeds64MiB")
            stream = archive.extractfile(member)
            need(stream is not None, "Missing member stream")
            raw = stream.read(MAX_FILE_BYTES + 1)
            need(len(raw) == member.size, "Member bytes differ from header")
            material[name.as_posix()] = raw
            folded.add(member.name.casefold())
        need(not archive.pax_headers, "Global PAX headers refused")
    need(len(material) == expected_count, "Exact archive member count required")
    return material


def verify_package(material):
    pins = {"PLAN-Q15.json": PLAN_SHA256, "PACKAGE-MANIFEST.json": PACKAGE_MANIFEST_SHA256,
            "ORIGINAL-RUNTIME-MANIFEST.json": PARENT_RUNTIME_SHA256,
            "RUNTIME-Q-MANIFEST.json": Q_RUNTIME_SHA256,
            "qualify15.py": RUNNER_SHA256, "qualification_contract.py": HELPER_SHA256}
    need(all(name in material and sha(material[name]) == digest for name, digest in pins.items()),
         "Actual package/plan/runtime/runner pins differ")
    manifest = read_json(material["PACKAGE-MANIFEST.json"])
    need(type(manifest) is dict and set(manifest) == {"schema", "files"}
         and manifest["schema"] == "hpc-forest-Q15-package-files-v1"
         and type(manifest["files"]) is dict, "Exact package manifest required")
    declared = manifest["files"]
    need(all(isinstance(key, str) and isinstance(value, str) and SHA.fullmatch(value)
             for key, value in declared.items()), "Exact file/SHA map required")
    actual = {name: sha(raw) for name, raw in material.items() if name != "PACKAGE-MANIFEST.json"}
    need(actual == declared, "Package inventory differs from immutable manifest")
    plan = read_json(material["PLAN-Q15.json"])
    need(plan.get("source_bindings") == {
        "schema": "hpc-forest-Q15-single-pilot-source-binding-v1",
        "parent_runtime_manifest_sha256": PARENT_RUNTIME_SHA256,
        "q_runtime_manifest_sha256": Q_RUNTIME_SHA256,
        "single_pilot_protocol_sha256": PROTOCOL_SHA256}, "Single-pilot source binding differs")
    need(plan.get("native_authorization") is False and type(plan.get("native_model_calls")) is int
         and plan["native_model_calls"] == 0 and len(plan.get("subject_order", [])) == 15,
         "Baseline-only fifteen-subject plan required")
    return plan


def allocation_guard(*, env=None, system=None, machine=None, affinity=None, now=None):
    env = os.environ if env is None else env
    system = platform.system() if system is None else system
    machine = platform.machine().lower() if machine is None else machine.lower()
    affinity = sorted(os.sched_getaffinity(0)) if affinity is None and hasattr(os, "sched_getaffinity") else affinity
    now = time.time() if now is None else now
    need(system == "Linux" and machine in {"aarch64", "arm64"}, "Owned LinuxARM64 allocation required")
    need(re.fullmatch(r"[1-9][0-9]*", env.get("SLURM_JOB_ID", "")), "Concrete Slurm job required")
    need(all(env.get(key) == value for key, value in {"SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
         "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}.items()), "Exact1node1task4CPU16GiB required")
    need(env.get("SLURM_RESTART_COUNT", "0") == "0" and env.get("CUDA_VISIBLE_DEVICES", "") == ""
         and all(env.get(key, "") in {"", "0"} for key in
                 ("SLURM_GPUS", "SLURM_GPUS_PER_NODE", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS")),
         "ZeroGPU and no restart required")
    need(isinstance(affinity, (list, tuple, set)) and len(set(affinity)) == 4,
         "Exactly four effective CPUs required")
    need(type(now) in {int, float} and math.isfinite(now) and now + 2100 + 10800 < DEADLINE,
         "Job35min plus reception3h exceeds exclusive deadline")
    return {"job_id": env["SLURM_JOB_ID"], "architecture": machine, "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0, "affinity_cpu_ids": sorted(affinity),
            "observed_utc": datetime.fromtimestamp(now, UTC).isoformat()}


def physical(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path
         and not any(item.is_symlink() for item in (path, *path.parents)), "Canonical nonlinked path required")
    return path


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
    return {"path": str(path), "sha256": sha(raw)}


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        need(not path.is_symlink(), "Linked output/source member refused")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return result


def child_argv(package, output):
    return [PYTHON, "-B", str(package / "qualify15.py"), "--package", str(package),
            "--plan", str(package / "PLAN-Q15.json"), "--plan-sha256", PLAN_SHA256,
            "--output", str(output), "--maximum-seconds", str(QUALIFICATION_SECONDS)]


def main():
    allocation = allocation_guard()
    physical(ROOT.parent)
    need(not ROOT.exists() and not ROOT.is_symlink(), "Execution root already exists; preserve without replay")
    archive_path = physical(physical(Path(__file__).absolute()).parent / ARCHIVE_NAME)
    need(stat.S_ISREG(archive_path.stat().st_mode) and archive_path.stat().st_size <= MAX_TOTAL_BYTES,
         "Bounded regular input archive required")
    need(sha(archive_path.read_bytes()) == ARCHIVE_SHA256, "Transferred archive SHA differs")
    material = read_tar(archive_path)
    plan = verify_package(material)
    allocation_guard()
    ROOT.mkdir(exist_ok=False)
    package, output = ROOT / "package", ROOT / "result-Q15"
    package.mkdir()
    cache = ROOT / "no-pycache-child-must-remain-absent"
    argv = child_argv(package, output)
    save(ROOT / "bootstrap-intent.json", {"schema": "hpc-forest-Q15-single-pilot-bootstrap-intent-v1",
         "allocation": allocation, "input_archive": {"path": str(archive_path), "sha256": ARCHIVE_SHA256},
         "plan_sha256": PLAN_SHA256, "package_manifest_sha256": PACKAGE_MANIFEST_SHA256,
         "source_bindings": plan["source_bindings"], "argv": argv, "native_model_calls": 0,
         "attempt": 1, "retry": False, "maximum_seconds": QUALIFICATION_SECONDS})
    receipt = {"schema": "hpc-forest-Q15-single-pilot-bootstrap-result-v1", "allocation": allocation,
               "plan_sha256": PLAN_SHA256, "input_archive_sha256": ARCHIVE_SHA256,
               "native_model_calls": 0, "qualification_child_launch_attempted": False, "passed": False}
    try:
        for name, raw in material.items():
            path = package.joinpath(*canonical_member(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
        before = {name: sha(raw) for name, raw in material.items()}
        need(inventory(package) == before, "Written package bytes differ")
        save(ROOT / "package-before.json", before)
        need(not cache.exists(), "Fresh absent child pycache prefix required")
        allocation_guard()
        receipt["qualification_child_launch_attempted"] = True
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache),
                           OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="4")
        with (ROOT / "qualification.stdout").open("xb") as stdout, (ROOT / "qualification.stderr").open("xb") as stderr:
            process = subprocess.run(argv, stdout=stdout, stderr=stderr, env=environment, check=False)
        receipt["qualification_returncode"] = process.returncode
        receipt["input_package_unchanged"] = inventory(package) == before
        result_path = output / "RESULT-Q15.json"
        result = read_json(result_path.read_bytes()) if result_path.is_file() else {}
        sidecar_path = ROOT / "result-Q15-archive.json"
        sidecar = read_json(sidecar_path.read_bytes()) if sidecar_path.is_file() else {}
        result_archive = ROOT / "result-Q15.tar.gz"
        receipt["result_archive_present"] = result_archive.is_file()
        archive_verified = (result_archive.is_file() and sidecar.get("path") == str(result_archive)
                            and sidecar.get("sha256") == sha(result_archive.read_bytes()))
        receipt["result_archive_sha_verified"] = archive_verified
        if archive_verified:
            receipt["result_archive"] = {"path": str(result_archive), "sha256": sidecar["sha256"]}
        receipt["qualification_complete_reported"] = result.get("qualification_complete") is True
        receipt["passed"] = (process.returncode == 0 and receipt["input_package_unchanged"]
                             and receipt["qualification_complete_reported"] and archive_verified)
    except Exception as exc:  # noqa: BLE001 - Preserve a negative once; never retry or repair.
        receipt.update(error_type=type(exc).__name__, error=str(exc), passed=False)
    finally:
        save(ROOT / "bootstrap-result.json", receipt)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
