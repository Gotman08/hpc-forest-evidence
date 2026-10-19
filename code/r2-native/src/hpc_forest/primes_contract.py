"""Immutable certified finite R2 contract; no generator, calibration or model call."""
from __future__ import annotations

import json
from pathlib import Path

from . import contracts
from .core import InfrastructureError, atomic_json, file_digest

PREPARATION_MANIFEST_SHA256 = "d260af0a7b91cbe5fc7e3ab1ad9313723e385c21fdd75bd5c9623095683022fd"
REFERENCE_SHA256 = "70e15be0d677eb40d700c3c09c20dc4d2db50132fbf9a2a4d30fb37bd3014f6d"
COMPILER_FLAGS = ["-O2", "-std=c11", "-Werror=uninitialized", "-Werror=maybe-uninitialized", "-lm"]
SIZES = (1, 2, 4, 8, 16, 30)
BENCHMARK_ORIGIN = "p30-v0"  # Chosen before any executable timing; no calibration.


def verify_preparation(package: Path):
    package = package.resolve(strict=True)
    manifest_path = package / "prototype-manifest.json"
    if file_digest(manifest_path) != PREPARATION_MANIFEST_SHA256:
        raise InfrastructureError("The independently reviewed preparation manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if actual != set(manifest) | {"prototype-manifest.json"}:
        raise InfrastructureError("Certified preparation has unmanifested or missing members")
    for name, item in manifest.items():
        path = package / contracts.relative(name)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(package):
            raise InfrastructureError("Unsafe certified preparation member")
        if file_digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise InfrastructureError("Certified preparation bytes changed")
    data = package / "data"
    if file_digest(data / "model-view/primetest.c") != REFERENCE_SHA256:
        raise InfrastructureError("The unchanged official source is required")
    return data


def specification(data: Path):
    def case(phase, number, origin):
        return {"name": f"{phase}-case-{number}", "argv": [],
                "stdin": {"file": f"private-audit-fixtures/{origin}/input.txt"},
                "files": [], "capture_files": []}
    search = [case("search", n, f"p{p:02d}-v0") for n, p in enumerate(SIZES, 1)]
    confirmation = [case("confirmation", n, f"p{p:02d}-v1") for n, p in enumerate(SIZES, 1)]
    contract = {"language": "c", "source_files": ["model-view/primetest.c"],
                "compiler_flags": list(COMPILER_FLAGS), "comparison": {"mode": "bytes"},
                "search_cases": search, "confirmation_cases": confirmation,
                "benchmark_case": case("benchmark", 1, BENCHMARK_ORIGIN)}
    contracts.validate_contract(contract, data)
    return contract


def expected_mapping():
    return {**{f"search-case-{n}": f"p{p:02d}-v0" for n, p in enumerate(SIZES, 1)},
            **{f"confirmation-case-{n}": f"p{p:02d}-v1" for n, p in enumerate(SIZES, 1)},
            "benchmark-case-1": BENCHMARK_ORIGIN}


def verify_resolved_values(resolved, data: Path, read_input):
    if (resolved.get("comparison") != {"mode": "bytes"} or resolved.get("compiler_flags") != COMPILER_FLAGS
            or resolved.get("language") != "c" or resolved.get("source_files") != ["model-view/primetest.c"]):
        raise InfrastructureError("Final compiled contract flags, source or byte comparator changed")
    for phase in ("search", "confirmation"):
        cases = resolved.get(phase, [])
        names = [case.get("name") for case in cases]
        required = {f"{phase}-case-{n}" for n in range(1, 7)}
        if len(cases) != 6 or len(set(names)) != 6 or set(names) != required:
            raise InfrastructureError("Each phase requires its exact six unique certified cases")
    if resolved.get("benchmark", {}).get("name") != "benchmark-case-1":
        raise InfrastructureError("The sole fixed certified benchmark is required")
    mapping, rows = expected_mapping(), []
    for case in [*resolved["search"], *resolved["confirmation"], resolved["benchmark"]]:
        if (set(case.get("expected", {})) != {"stdout"} or case.get("argv") != []
                or case.get("files") != [] or case.get("capture_files") != []):
            raise InfrastructureError("Unexpected contracted argument, asset or output channel")
        origin = mapping[case["name"]]
        expected = data / "private-audit-fixtures" / origin / "expected.txt"
        stdin = data / "private-audit-fixtures" / origin / "input.txt"
        if contracts.unblob(case["expected"]["stdout"]) != expected.read_bytes():
            raise InfrastructureError("Allocated official reference disagrees with certified bytes")
        if read_input(contracts.relative(case["stdin"])) != stdin.read_bytes():
            raise InfrastructureError("Materialized input is not the immutable certified input")
        rows.append({"case": case["name"], "origin": origin,
                     "expected_sha256": file_digest(expected), "input_sha256": file_digest(stdin),
                     "allocated_reference_exact_bytes": True})
    if len({row["origin"] for row in rows[:12]}) != 12 or rows[-1]["origin"] != BENCHMARK_ORIGIN:
        raise InfrastructureError("The exact twelve certified origins and fixed benchmark are required")
    return rows


def verify_resolved_expected(validation: Path, data: Path):
    resolved = json.loads((validation / "contract.json").read_text(encoding="utf8"))
    return verify_resolved_values(resolved, data, lambda name: (validation / name).read_bytes())


def prepare_certified(package: Path, output: Path):
    """Allocated caller only. contracts.prepare is reused, then certified bytes gate readiness."""
    data = verify_preparation(package)
    receipt = contracts.prepare(specification(data), data, output, probe_timeout=30)
    rows = verify_resolved_expected(Path(receipt["validation"]), data)
    # The official file has its original relative name inside source/src/model-view.
    if file_digest(Path(receipt["source"]) / "src/model-view/primetest.c") != REFERENCE_SHA256:
        raise InfrastructureError("The prepared official C changed")
    receipt.update(certified_expected_rows=rows, compiler_flags=COMPILER_FLAGS,
                   certified_expected_compared_byte_for_byte=True, calibration=False,
                   benchmark_origin=BENCHMARK_ORIGIN, native_model_calls=0)
    atomic_json(output / "certified-preparation-receipt.json", receipt)
    return receipt


def prepare_runtime_reference(package: Path, output: Path, allocation: dict,
                              source_zip_sha256: str, plan_sha256: str, qualification_ref: dict):
    """Fresh same-job official preparation; qualification timings are never imported."""
    preparation = prepare_certified(package, output / "prepared")
    origin = {"schema": "hpc-forest-primes-r2max-runtime-reference-v1", "verified": True,
              "job_id": allocation["job_id"], "allocation": allocation,
              "source_zip_sha256": source_zip_sha256, "plan_sha256": plan_sha256,
              "preparation_manifest_sha256": PREPARATION_MANIFEST_SHA256,
              "reference_origin_is_current_allocation": True,
              "qualification_timings_imported": False, "native_model_calls": 0,
              "new_inputs_or_candidates": 0, "compiler_flags": COMPILER_FLAGS,
              "prior_qualification_evidence_only": qualification_ref,
              "preparation": preparation}
    atomic_json(output / "runtime-reference-origin.json", origin)
    return preparation
