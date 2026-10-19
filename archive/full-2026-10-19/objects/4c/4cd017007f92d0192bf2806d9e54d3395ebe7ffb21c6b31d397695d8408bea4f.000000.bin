"""Allocated final-contract qualification only; no model, worker, submission or installation."""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from hpc_forest.core import atomic_json, file_digest  # noqa: E402
from hpc_forest.native_r2max import SCOPE, allocation_guard, verify_qualification, verify_runtime  # noqa: E402
from hpc_forest.primes_contract import (  # noqa: E402
    COMPILER_FLAGS,
    PREPARATION_MANIFEST_SHA256,
    REFERENCE_SHA256,
    prepare_certified,
    verify_preparation,
)
from hpc_forest.r2max_trace_qualification import qualify_trace  # noqa: E402


def qualify(package, output, source_zip, plan_path):
    # Refuse before directory creation, subprocesses, compiler probes or any channel.
    allocation = allocation_guard()
    source_sha = file_digest(source_zip)
    plan = json.loads(plan_path.read_text(encoding="utf8"))
    if (plan.get("scope_id") != SCOPE or plan.get("source_zip_sha256") != source_sha
            or plan.get("preparation_manifest_sha256") != PREPARATION_MANIFEST_SHA256):
        raise RuntimeError("Qualification requires the exact new source and frozen plan")
    verify_runtime(source_zip)
    verify_preparation(package)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "hpc-forest-primes-r2max-allocated-contract-qualification-v1",
               "scope_id": SCOPE, "verified": False, "allocation": allocation,
               "source_zip_sha256": source_sha, "plan_sha256": file_digest(plan_path),
               "preparation_manifest_sha256": PREPARATION_MANIFEST_SHA256,
               "reference_source_sha256": REFERENCE_SHA256,
               "compiler_flags": COMPILER_FLAGS, "native_model_calls": 0,
               "hardware_or_process_isolation_proved": False,
               "started_at": time.time(), "negative_preserved_no_retry": True}
    try:
        prepared = output / "prepared"
        preparation = prepare_certified(package, prepared)
        trace = qualify_trace(preparation, output / "official-evaluator-trace", allocation)
        command = json.loads((prepared / "reference-build/compiler-command.json").read_text())
        if command.get("compiler_flags") != COMPILER_FLAGS or any(flag not in command["argv"] for flag in COMPILER_FLAGS):
            raise RuntimeError("Actual compilation flags do not match the final contract")
        receipt.update(verified=True, prepared_root=str(prepared.resolve()),
                       prepared_files={p.relative_to(prepared).as_posix(): file_digest(p)
                                       for p in sorted(prepared.rglob("*"))
                                       if p.is_file() and "__pycache__" not in p.parts},
                       compiler_command=command, reference_binary_sha256=preparation["reference_binary_sha256"],
                       reference_outputs_all_certified_bytes=True, unique_certified_cases=12,
                       certified_expected_rows=preparation["certified_expected_rows"],
                       benchmark_origin=preparation["benchmark_origin"], calibration=False,
                       native_research_admitted=False)
        receipt["official_evaluator_trace_qualification"] = {
            "path": str(output / "official-evaluator-trace/trace-qualification.json"),
            "sha256": file_digest(output / "official-evaluator-trace/trace-qualification.json"),
            "execution_purpose": trace["execution_purpose"], "verified": trace["verified"]}
        receipt["official_evaluator_trace_files"] = {
            p.relative_to(output / "official-evaluator-trace").as_posix(): file_digest(p)
            for p in sorted((output / "official-evaluator-trace").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}
        verify_qualification(receipt, source_sha, prepared=True, package=package)
    except Exception as exc:
        receipt.update(verified=False, error_type=type(exc).__name__, error=str(exc),
                       reference_outputs_all_certified_bytes=False,
                       native_research_admitted=False)
    finally:
        receipt["finished_at"] = time.time()
        atomic_json(output / "qualification.json", receipt)
        archive_path = output.with_name(output.name + ".tar.gz")
        if archive_path.exists():
            raise RuntimeError("Refusing to overwrite an earlier qualification archive")
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.add(path, arcname="qualification/" + path.relative_to(output).as_posix())
        atomic_json(output.with_name(output.name + "-archive.json"),
                    {"path": str(archive_path), "sha256": file_digest(archive_path),
                     "private_audit_only": True, "native_model_calls": 0})
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.package.resolve(strict=True), args.output.resolve(),
                     args.source_zip.resolve(strict=True), args.plan.resolve(strict=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
