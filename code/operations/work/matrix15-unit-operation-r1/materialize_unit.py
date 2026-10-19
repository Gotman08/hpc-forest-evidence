"""Pure staged input/body builder for one registered Matrix15 continuation cell."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Unit-Operation-Preparation-r1"
BUILDER = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1/build_inputs.py"
BUILDER_SHA = "4d26cdab42a7b47cc8d326fbd638e9f44fbe404dbcac40ad64cf7dba42dd99d1"
PREFIX_SHA = "ed7c7ad59aa06d905f259e97a0bd83f2af3ed9be006d977bef3c46e92512db16"
NEXT = "forest-r2/gpt-6.1-sol/max/2023-count/seed-23"
NEXT_SESSION = "4bb93e081ad042a185b7029f3ade2605"
SPACK = "/zrtbeqke25s2vbqo4yrhsowjz7mg3pjf"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def raw(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf8")


def physical(path):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts and not any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)),
        "Ordinary absolute path required")
    return path


def sized(path):
    path = physical(path)
    need(path.is_file(), "Existing regular input required")
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def ref(path):
    item = sized(path)
    return {key: item[key] for key in ("path", "sha256")}


def write(path, value):
    path = physical(path)
    need(path.is_relative_to(OUTPUT) and path != OUTPUT, "Output outside unit ownership")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(value if isinstance(value, bytes) else raw(value))
    return ref(path)


def source_module(name, path, checksum):
    path = physical(path)
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == checksum, "Pinned pure builder source changed")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(data, str(path), "exec", dont_inherit=True), module.__dict__)  # noqa: S102 - exact pinned source, no pyc.
    return module


def runtime():
    builder = source_module("matrix15_unit_pinned_builder", BUILDER, BUILDER_SHA)
    upstream, reader, dynamic, capacity, bootstrap = builder.runtime()
    prefix = source_module("matrix15_unit_pinned_prefix", builder.BOOTSTRAP / "job_prefix.py", PREFIX_SHA)
    return builder, upstream, reader, dynamic, capacity, bootstrap, prefix


def body(bootstrap_input, input_sha, remote_stage, bootstrap_sha, gate_source_sha, prefix):
    root = bootstrap_input["scientific_root"]
    cache = root + "-bootstrap-pycache-must-remain-absent"
    shared = bootstrap_input["shared_root"]
    q = shlex.quote
    checks = " ".join(q(value) for pair in ((bootstrap_sha, "bootstrap_extension.py"),
        (gate_source_sha, "extension_gate.py"), (input_sha, "INPUT-BOOTSTRAP.json")) for value in pair)
    lines = ["#!/usr/bin/env bash", "# Prepared single cell; ROOT reviews and consumes one MCP plan only.",
        "set -euo pipefail", "romeo_load_armgpu_env", "spack load " + SPACK,
        "[[ -x " + q(bootstrap_input["python"]) + " ]] || { echo 'Exact ARM Python missing' >&2; exit 70; }",
        "[[ -d " + q(shared) + " && ! -L " + q(shared) + " ]] || { echo 'Existing shared375 required' >&2; exit 71; }"]
    for path, code, message in ((root, 72, "Scientific root exists; no replay"),
        (bootstrap_input["admission_root"], 73, "Admission root exists; no replay"),
        (cache, 74, "Fresh absent pycache prefix required")):
        lines.append("[[ ! -e " + q(path) + " && ! -L " + q(path) + " ]] || { echo " + q(message) + " >&2; exit " + str(code) + "; }")
    lines.extend(["command -v timeout >/dev/null", "command -v sha256sum >/dev/null", "cd -- " + q(remote_stage),
        "printf '%s  %s\\n' " + checks + " | sha256sum --check --strict",
        "export PYTHONPYCACHEPREFIX=" + q(cache), "export PYTHONDONTWRITEBYTECODE=1",
        "export OPENBLAS_NUM_THREADS=1", "export OMP_NUM_THREADS=4", "export OMP_DYNAMIC=FALSE",
        "export OMP_PROC_BIND=TRUE", "export CUDA_VISIBLE_DEVICES=''"])
    tail = [bootstrap_input["python"], "-I", "-B", remote_stage + "/bootstrap_extension.py",
            "--input", remote_stage + "/INPUT-BOOTSTRAP.json", "--input-sha256", input_sha]
    lines.append(shlex.join([*prefix.argument_prefix(), *tail]))
    return ("\n".join(lines) + "\n").encode("utf8")


def materialize(output, cell_key=NEXT, prerequisite=None):
    output = physical(output)
    need(output.is_relative_to(OUTPUT) and output != OUTPUT and not output.exists(), "New owned unit output required")
    builder, _upstream, reader, dynamic, _capacity, bootstrap, prefix = runtime()
    need(cell_key in dynamic.contract.REGISTERED_CELLS, "Registered sixty-cell identity required")
    refs, _plan, _aliases = dynamic.static_inputs(ref(builder.STATICS / "STATICS.json"))
    plan_raw = Path(refs["plan"]["path"]).read_bytes()
    helper = bootstrap.load_helper((builder.BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    _plan, binding = bootstrap.registered_selection(helper, plan_raw, cell_key)
    need(cell_key != NEXT or binding["session_id"] == NEXT_SESSION, "Fixed next Sol/count identity drift")
    gate = None
    gate_check = None
    if prerequisite is not None:
        prior = builder.read_ref(reader, prerequisite)
        gate_check, selected = builder.prerequisites(dynamic, reader, prior, cell_key,
            str(BASE / "work/matrix15-global-capacity-production-r1"))
        need(all(binding[key] == value for key, value in selected.items()), "Selection differs from registered binding")
        gate = prior["gate_arm"]
    bootstrap_input = bootstrap.build_cell_input(helper, plan_raw, cell_key, gate)
    if prerequisite is None:
        template_ref = write(output / "INPUT-BOOTSTRAP-TEMPLATE.json", bootstrap_input)
        return write(output / "PREPARATION.json", {"schema": "hpc-forest-matrix15-unit-operation-prepared-v1",
            "mode": "PREPARE", "verified": False, "cell_key": cell_key, "binding_without_job_id": binding,
            "bootstrap_template": template_ref, "missing": ["actual received extension prerequisites"],
            "operational_files_emitted": False, "job_prepare_arguments": None, "upload_manifest": None,
            "native_authorization": False, "native_model_calls": 0, "jobs_submitted": 0,
            "capacity_registry_modified": False, "automatic_extension": False})
    bootstrap.validate_input(helper, bootstrap_input, plan_raw)
    remote_stage = binding["remote_root"] + "-bootstrap-inputs"
    input_ref = write(output / "stage/INPUT-BOOTSTRAP.json", bootstrap_input)
    staged = {"INPUT-BOOTSTRAP.json": input_ref}
    for filename in ("bootstrap_extension.py", "extension_gate.py"):
        source = builder.BOOTSTRAP / filename
        checksum = builder.BOOT_PINS[filename] if filename in builder.BOOT_PINS else builder.PINS[filename]
        need(ref(source)["sha256"] == checksum, "Pinned staged source changed")
        staged[filename] = write(output / "stage" / filename, source.read_bytes())
    shell = body(bootstrap_input, input_ref["sha256"], remote_stage, staged["bootstrap_extension.py"]["sha256"],
                 staged["extension_gate.py"]["sha256"], prefix)
    body_ref = write(output / "job-body.sh", shell)
    args = {"arch": "armgpu", "command": shell.decode("utf8"), "cpus_per_task": 4, "gpus_per_node": 0,
        "job_tmpdir": False, "mem_gb": 16, "name": "forest-m15-" + binding["session_id"][:12], "nodes": 1,
        "ntasks_per_node": 1, "redirect_caches": False, "spack_packages": [SPACK], "time_limit": "01:00:00",
        "workdir": "/gpfs/scratch/nimarano"}
    arguments_ref = write(output / "JOB-PREPARE-ARGS.json", args)
    manifest_ref = write(output / "UPLOAD-MANIFEST.json", {"schema": "hpc-forest-matrix15-unit-bootstrap-upload-v1",
        "uploaded": False, "remote_stage": remote_stage, "members": [{"local": sized(Path(item["path"])),
            "remote": {"path": remote_stage + "/" + name, "sha256": item["sha256"]}} for name, item in staged.items()],
        "shared_root": bootstrap_input["shared_root"], "shared_reuse_only": True, "expected_shared_files": 375})
    return write(output / "PREPARATION.json", {"schema": "hpc-forest-matrix15-unit-operation-prepared-v1",
        "mode": "PREPARE", "verified": False, "cell_key": cell_key, "binding_without_job_id": binding,
        "prerequisites": prerequisite, "historical_gate_check": gate_check, "operational_files_emitted": True,
        "bootstrap_input": input_ref, "job_body": body_ref, "job_prepare_arguments": arguments_ref,
        "upload_manifest": manifest_ref, "native_authorization": False, "native_model_calls": 0, "jobs_submitted": 0,
        "capacity_registry_modified": False, "automatic_extension": False})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cell-key", default=NEXT)
    parser.add_argument("--prerequisites", type=Path)
    parser.add_argument("--prerequisites-sha256")
    args = parser.parse_args(argv)
    need(bool(args.prerequisites) == bool(args.prerequisites_sha256), "Prerequisite path and SHA must be paired")
    prior = {"path": str(args.prerequisites), "sha256": args.prerequisites_sha256} if args.prerequisites else None
    result = materialize(args.output, args.cell_key, prior)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
