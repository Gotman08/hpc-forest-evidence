"""Materialize a prepared-only launch from the actual final static artifacts; no job/API calls."""
from __future__ import annotations

import argparse
import re
from pathlib import Path, PurePosixPath

import bootstrap_native as boot

STAGING_ROOT = boot.SCIENTIFIC_ROOT + "-inputs"


def local_ref(path):
    path = Path(path).resolve(strict=True)
    raw = boot.regular_bytes(path, boot.MAX_ARCHIVE)
    return {"path": str(path), "sha256": boot.sha(raw), "bytes": len(raw)}


def make_input(statics, archive_ref, manifest_ref):
    boot.need(statics.get("schema") == "hpc-forest-matrix15-native-static-package-v1", "Actual static package descriptor required")
    refs = statics["artifacts"]
    for ref in refs.values():
        raw = boot.regular_bytes(Path(ref["path"]).resolve(strict=True), boot.MAX_ARCHIVE)
        boot.need(boot.sha(raw) == ref["sha256"], "A final local static reference changed")
    boot.need(refs["source_zip"]["sha256"] == boot.SOURCE_SHA256
              and refs["runtime_manifest"]["sha256"] == boot.RUNTIME_MANIFEST_SHA256, "Sealed source/runtime differ")
    plan = boot.read_json(boot.regular_bytes(Path(refs["plan"]["path"]).resolve(strict=True)))
    subject = plan["subject_bindings"]["2020-quicksort"]
    cells = [cell for cell in plan["cells"] if cell["cell_key"] == boot.CELL_KEY]
    boot.need(len(cells) == 1 and cells[0] == {"cell_key": boot.CELL_KEY, "subject_id": "2020-quicksort",
              "model": "gpt-6-luna", "effort": "max", "session_id": boot.SESSION}, "Final plan first-cell identity differs")
    binding = {"scope_id": boot.SCOPE, "cell_key": boot.CELL_KEY, "subject_id": "2020-quicksort", "model": "gpt-6-luna",
               "effort": "max", "session_id": boot.SESSION, "remote_root": boot.SCIENTIFIC_ROOT,
               "source_zip_sha256": boot.SOURCE_SHA256, "plan_sha256": refs["plan"]["sha256"],
               "preparation_manifest_sha256": refs["preparation_manifest"]["sha256"],
               "r1_contract_sha256": subject["r1_contract_ref"]["sha256"]}
    return boot.validate_input({"schema": "hpc-forest-matrix15-bootstrap-input-v1", "evidence_origin": "operator-prepared",
        "native_execution_authorized_by_this_input": False, "shared_root": boot.SHARED_ROOT,
        "scientific_root": boot.SCIENTIFIC_ROOT, "admission_root": boot.SCIENTIFIC_ROOT + "-admission", "python": boot.PYTHON,
        "shared_archive": archive_ref, "shared_files_manifest": manifest_ref, "binding_without_job_id": binding,
        "source_zip_relative": "native-source.zip", "runtime_manifest_relative": "runtime-manifest.json",
        "plan_relative": "plan-60-v2.json", "maximum_admission_seconds": 600, "maximum_runner_seconds": 2700,
        "scientific_wall_seconds": 1800, "confirmation_seconds": 120, "collection_reserve_seconds": 180})


def shell_body(input_sha, files):
    checks = " ".join("'" + ref["sha256"] + "' '" + name + "'" for name, ref in files.items())
    return f"""#!/usr/bin/env bash
# PREPARED ONLY. Root must validate this exact body and submit one MCP plan.
# Required allocation: ARM64,1node,1task,4CPU,16GiB,0GPU,01:00:00.
set -euo pipefail
romeo_load_armgpu_env
spack load /zrtbeqke25s2vbqo4yrhsowjz7mg3pjf
[[ -x '{boot.PYTHON}' ]] || {{ echo 'Exact ARM Python missing' >&2; exit 70; }}
[[ ! -e '{boot.SHARED_ROOT}' && ! -L '{boot.SHARED_ROOT}' ]] || {{ echo 'Shared root exists; no replay' >&2; exit 71; }}
[[ ! -e '{boot.SCIENTIFIC_ROOT}' && ! -L '{boot.SCIENTIFIC_ROOT}' ]] || {{ echo 'Scientific root exists; no replay' >&2; exit 72; }}
[[ ! -e '{boot.SCIENTIFIC_ROOT}-admission' && ! -L '{boot.SCIENTIFIC_ROOT}-admission' ]] || {{ echo 'Admission root exists; no replay' >&2; exit 73; }}
command -v timeout >/dev/null
command -v sha256sum >/dev/null
cd -- '{STAGING_ROOT}'
printf '%s  %s\\n' {checks} | sha256sum --check --strict
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX='{boot.SCIENTIFIC_ROOT}-bootstrap-pycache-must-remain-absent'
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
export OMP_DYNAMIC=FALSE
export OMP_PROC_BIND=TRUE
export CUDA_VISIBLE_DEVICES=''
[[ ! -e "$PYTHONPYCACHEPREFIX" && ! -L "$PYTHONPYCACHEPREFIX" ]] || {{ echo 'Fresh absent pycache prefix required' >&2; exit 74; }}
srun --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=16G --cpu-bind=cores timeout --signal=TERM --kill-after=10s 3310s '{boot.PYTHON}' -I -B '{STAGING_ROOT}/bootstrap_native.py' --input '{STAGING_ROOT}/BOOTSTRAP-INPUT.json' --input-sha256 '{input_sha}'
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statics", type=Path, required=True)
    parser.add_argument("--shared-archive", type=Path, required=True)
    parser.add_argument("--shared-files-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    archive = local_ref(args.shared_archive)
    manifest = local_ref(args.shared_files_manifest)
    for source in (args.shared_archive, args.shared_files_manifest):
        boot.need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}", source.name), "Safe transfer basename required")
    boot.need(args.shared_archive.name != args.shared_files_manifest.name, "Transfer basenames collide")
    manifest_value = boot.read_json(boot.regular_bytes(Path(manifest["path"])))
    boot.read_archive(Path(archive["path"]), manifest_value)
    projected_archive = {**archive, "path": str(PurePosixPath(STAGING_ROOT) / args.shared_archive.name)}
    projected_manifest = {**manifest, "path": str(PurePosixPath(STAGING_ROOT) / args.shared_files_manifest.name)}
    statics_raw = boot.regular_bytes(args.statics.resolve(strict=True))
    config = make_input(boot.read_json(statics_raw), projected_archive, projected_manifest)
    output = args.output_dir.absolute()
    boot.need(boot.absent(output), "Prepared output exists; use a fresh directory, preserve previous attempt")
    output.mkdir(parents=True, exist_ok=False)
    transfer = output / "transfer"
    transfer.mkdir()
    files = {}
    sources = {"bootstrap_native.py": Path(__file__).with_name("bootstrap_native.py"),
               args.shared_archive.name: Path(archive["path"]), args.shared_files_manifest.name: Path(manifest["path"])}
    for name, source in sources.items():
        with (transfer / name).open("xb") as stream:
            stream.write(boot.regular_bytes(source.resolve(strict=True), boot.MAX_ARCHIVE))
        files[name] = local_ref(transfer / name)
    input_ref = boot.save(transfer / "BOOTSTRAP-INPUT.json", config)
    files["BOOTSTRAP-INPUT.json"] = input_ref
    with (output / "job-body.sh").open("xb") as stream:
        stream.write(shell_body(input_ref["sha256"], files).encode())
    boot.save(output / "PREPARATION-BOOTSTRAP.json", {"schema": "hpc-forest-matrix15-bootstrap-preparation-v1",
        "verified": False, "evidence_origin": "operator-prepared", "jobs_submitted": 0, "native_model_calls": 0,
        "native_authorization": False, "statics": {"path": str(args.statics.resolve()), "sha256": boot.sha(statics_raw)},
        "transfer_root": STAGING_ROOT, "files": files, "input": input_ref, "job_body": local_ref(output / "job-body.sh")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
