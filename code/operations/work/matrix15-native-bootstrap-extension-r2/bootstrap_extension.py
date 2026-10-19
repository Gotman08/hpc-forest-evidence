"""Prepared extension of the sixty registered Matrix15 cells; never an auto-launcher.

Reuses the byte-pinned stdlib bootstrap helper and immutable shared375 inventory.
No operational input is emitted unless an actual first-batch receipt/release gate
has been received and reviewed.  Every new cell still needs its own authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import time
from pathlib import Path

BASE_SHA = "d4bf5278c8fb698570e111b7e19c632e0bd8929e5aa8ebd833e262e303e56752"
PLAN_SHA = "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f"
SCOPE = "hpc-forest-matrix15-native-max-r2"
SHARED = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-20261019-root-01-shared"
FIRST_SESSION = "9a681c2826854a4b885e94c5e6243f0a"
FIRST_CELL = "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23"
FIRST_ROOT = "/gpfs/scratch/nimarano/" + SCOPE + "-" + FIRST_SESSION
COMMON_STAGE = FIRST_ROOT + "-inputs"
COMMON_HELPER = {"path": COMMON_STAGE + "/bootstrap_native.py", "sha256": BASE_SHA, "bytes": 27586}
COMMON_ARCHIVE = {"path": COMMON_STAGE + "/HPC-Forest-Matrix15-Static-Shared-r2.tar.gz",
                  "sha256": "7a174551f369b2a04a6e31990f2c30eed47827e26deaa58ff14165eb6140c674", "bytes": 14494766}
COMMON_MANIFEST = {"path": COMMON_STAGE + "/SHARED-FILES-MANIFEST.json",
                   "sha256": "b4a51798ecbbe995af50ea83a2eba36aa3f71c1965d06ef32d4b400050ebe721", "bytes": 62765}
MODELS = {"gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra"}
SUBJECTS = {"2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
            "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
            "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci"}


def load_helper(path=COMMON_HELPER["path"]):
    """Only the exact sealed file may supply helpers; its main is never called."""
    path = Path(path)
    if (not path.is_absolute() or path.resolve(strict=True) != path
            or any(item.is_symlink() for item in (path, *path.parents))):
        raise ValueError("Canonical nonlinked sealed helper required")
    raw = path.read_bytes()
    if len(raw) != COMMON_HELPER["bytes"] or hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError("Sealed bootstrap helper bytes differ")
    spec = importlib.util.spec_from_file_location("_forest_sealed_bootstrap_helpers_d4bf", path)
    if spec is None or spec.loader is None:
        raise ValueError("Missing sealed helper loader")
    module = importlib.util.module_from_spec(spec)
    # Compile the verified bytes directly; ignore existing .pyc without modifying it.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact byte-pinned helper, no pyc trust.
    return module


def registered_selection(b, plan_raw, cell_key):
    b.need(b.sha(plan_raw) == PLAN_SHA, "Exact registered sixty-cell plan required")
    plan = b.read_json(plan_raw)
    cells = plan.get("cells")
    b.need(type(cells) is list and len(cells) == 60 and plan.get("scope_id") == SCOPE,
           "Exact registered sixty cells and scope required")
    sessions, keys, pairs = set(), set(), set()
    selected = None
    for cell in cells:
        b.need(type(cell) is dict and set(cell) == {"cell_key", "subject_id", "model", "effort", "session_id"}
               and cell["subject_id"] in SUBJECTS and cell["model"] in MODELS and cell["effort"] == "max"
               and re.fullmatch(r"[0-9a-f]{32}", cell["session_id"])
               and cell["cell_key"] == f"forest-r2/{cell['model']}/max/{cell['subject_id']}/seed-23"
               and cell["session_id"] not in sessions and cell["cell_key"] not in keys,
               "Unregistered/duplicate/non-MAX cell or session")
        sessions.add(cell["session_id"])
        keys.add(cell["cell_key"])
        pairs.add((cell["model"], cell["subject_id"]))
        if cell["cell_key"] == cell_key:
            selected = cell
    b.need(pairs == {(model, subject) for model in MODELS for subject in SUBJECTS} and selected is not None,
           "Requested cell is outside the registered sixty-cell matrix")
    root = "/gpfs/scratch/nimarano/" + SCOPE + "-" + selected["session_id"]
    subject = plan["subject_bindings"][selected["subject_id"]]
    binding = {"scope_id": SCOPE, **selected, "remote_root": root,
               "source_zip_sha256": b.SOURCE_SHA256, "plan_sha256": PLAN_SHA,
               "preparation_manifest_sha256": plan["preparation_manifest"]["sha256"],
               "r1_contract_sha256": subject["r1_contract_ref"]["sha256"]}
    return plan, binding


def validate_input(b, value, plan_raw):
    fields = {"schema", "evidence_origin", "native_execution_authorized_by_this_input", "automatic_extension",
              "shared_root", "scientific_root", "admission_root", "python", "common_helper", "common_archive",
              "common_manifest", "binding_without_job_id", "first_batch_gate", "maximum_admission_seconds",
              "maximum_runner_seconds", "scientific_wall_seconds", "confirmation_seconds", "collection_reserve_seconds"}
    b.need(type(value) is dict and set(value) == fields
           and value.get("schema") == "hpc-forest-matrix15-extension-bootstrap-input-v1"
           and value.get("evidence_origin") == "operator-prepared"
           and value.get("native_execution_authorized_by_this_input") is False
           and value.get("automatic_extension") is False, "Prepared individual-cell extension input required")
    binding = value["binding_without_job_id"]
    b.need(type(binding) is dict and set(binding) == b.BINDING_FIELDS - {"job_id"}, "Exact eleven-field cell binding required")
    plan, expected = registered_selection(b, plan_raw, binding["cell_key"])
    b.need(binding == expected and value["shared_root"] == SHARED and value["scientific_root"] == expected["remote_root"]
           and value["admission_root"] == expected["remote_root"] + "-admission" and value["python"] == b.PYTHON,
           "Registered identity/root/shared/interpreter changed")
    b.need(value["common_helper"] == COMMON_HELPER and value["common_archive"] == COMMON_ARCHIVE
           and value["common_manifest"] == COMMON_MANIFEST, "Immutable common transfer references changed")
    limits = {"maximum_admission_seconds": 600, "maximum_runner_seconds": 2700, "scientific_wall_seconds": 1800,
              "confirmation_seconds": 120, "collection_reserve_seconds": 180}
    b.need(all(type(value[key]) is int and value[key] == item for key, item in limits.items()),
           "Original admission/execution/scientific limits changed")
    b.need(type(value["first_batch_gate"]) is dict, "Actual received first-batch gate absent; preparation remains closed")
    return plan, binding


def build_cell_input(b, plan_raw, cell_key, gate_ref):
    """Pure object builder; caller must validate the actual gate before any emission.

    A null gate produces only an inadmissible preparation template. Runtime always
    revalidates the real proof with the native validator before its marker.
    """
    _plan, binding = registered_selection(b, plan_raw, cell_key)
    return {"schema": "hpc-forest-matrix15-extension-bootstrap-input-v1", "evidence_origin": "operator-prepared",
            "native_execution_authorized_by_this_input": False, "automatic_extension": False,
            "shared_root": SHARED, "scientific_root": binding["remote_root"],
            "admission_root": binding["remote_root"] + "-admission", "python": b.PYTHON,
            "common_helper": COMMON_HELPER, "common_archive": COMMON_ARCHIVE, "common_manifest": COMMON_MANIFEST,
            "binding_without_job_id": binding, "first_batch_gate": gate_ref,
            "maximum_admission_seconds": 600, "maximum_runner_seconds": 2700, "scientific_wall_seconds": 1800,
            "confirmation_seconds": 120, "collection_reserve_seconds": 180}


def verify_immutable_shared(b, shared, manifest):
    b.need(str(shared) == SHARED and len(manifest.get("files", {})) == 375
           and manifest.get("schema") == "hpc-forest-matrix15-shared-files-v1"
           and set(manifest) == {"schema", "files"}, "Exact existing375-file shared inventory required")
    b.physical(shared)
    b.need(b.inventory(shared) == manifest["files"], "Existing shared375 inventory changed; never repair or reextract")
    plan_raw = b.regular_bytes(Path(shared) / "plan-60-v2.json")
    b.need(b.sha(plan_raw) == PLAN_SHA, "Existing shared plan differs")
    config = {"source_zip_relative": "native-source.zip", "runtime_manifest_relative": "runtime-manifest.json",
              "plan_relative": "plan-60-v2.json", "binding_without_job_id": {"plan_sha256": PLAN_SHA}}
    source, runtime = b.verify_sources(shared, config)
    return plan_raw, source, runtime


def validate_first_batch_gate(b, gate, native, batch, plan_raw):
    b.need(b.sha(plan_raw) == PLAN_SHA, "Exact shared plan required before extension gate")
    path = Path(__file__).with_name("extension_gate.py")
    raw = b.regular_bytes(path.absolute())
    b.need(b.sha(raw) == "e8e8ee7e69ccced5d15054f1a61f3970e0019a282e7c20f8cdbc4db77aa9eb30", "Portable extension gate source changed")
    module = {"__name__": "_forest_verified_extension_gate", "__file__": str(path)}
    exec(compile(raw, str(path), "exec"), module)  # noqa: S102 - source SHA checked immediately above.
    # Capture the original resolver before the temporary exact resolver context is installed.
    return module["validate_gate"](gate, read_ref=native.artifact, native=native, batch=batch)


def extension_interpreter_guard(b, root):
    b.need(Path(sys.executable).absolute() == Path(b.PYTHON), "Exact existing ARM venv required")
    b.need(b.importlib.metadata.version("treequest") == "0.3.2", "Actual TreeQuest0.3.2 required")
    expected = {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE", "CUDA_VISIBLE_DEVICES": "",
                "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}
    b.need(all(b.os.environ.get(key) == value for key, value in expected.items()), "Actual scientific environment differs")
    cache = root + "-bootstrap-pycache-must-remain-absent"
    b.need(b.os.environ.get("PYTHONPYCACHEPREFIX") == cache and b.absent(cache), "Own fresh absent pycache prefix required")


def main(argv=None):
    started_monotonic, started_at = time.monotonic(), time.time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args(argv)
    b = load_helper()
    raw = b.regular_bytes(args.input)
    b.need(b.SHA.fullmatch(args.input_sha256) and b.sha(raw) == args.input_sha256, "Extension input SHA differs")
    config = b.read_json(raw)
    # Common helper/manifest/archive are only re-read; no shared file is created, extracted or modified.
    b.read_ref(COMMON_HELPER)
    b.read_ref(COMMON_ARCHIVE, limit=b.MAX_ARCHIVE)
    manifest = b.read_json(b.read_ref(COMMON_MANIFEST))
    plan_raw, source, runtime = verify_immutable_shared(b, Path(SHARED), manifest)
    _plan, upstream_binding = validate_input(b, config, plan_raw)
    allocation = b.allocation_guard()
    extension_interpreter_guard(b, upstream_binding["remote_root"])
    binding = {**upstream_binding, "job_id": allocation["job_id"]}
    admission = Path(config["admission_root"])
    b.physical(admission.parent)
    b.need(b.absent(admission) and all(b.absent(path) for path in b.scientific_paths(binding).values()),
           "Own scientific/admission paths exist; no replay")
    admission.mkdir(exist_ok=False)
    receipt = {"schema": "hpc-forest-matrix15-extension-bootstrap-result-v1", "binding": binding,
               "bootstrap_started_at": started_at, "bootstrap_started_monotonic": started_monotonic,
               "admission_deadline": started_at + 600, "execution_deadline": started_at + 3300,
               "maximum_admission_seconds": 600, "maximum_runner_seconds": 2700,
               "native_child_launch_attempted": False, "admission_accepted": False, "passed": False,
               "retry": False, "attempt": 1, "automatic_extension": False, "native_model_calls_before_authorization": 0}
    b.save(admission / "bootstrap-intent.json", {**receipt, "input": {"path": str(args.input), "sha256": args.input_sha256},
           "shared_reused_immutable": True, "scientific_wall_seconds": 1800, "confirmation_seconds": 120})
    try:
        outer_deadline = b.allocation_outer_deadline(allocation, admission)
        receipt["allocation_outer_deadline"] = outer_deadline
        b.need(started_at + 3310 < outer_deadline, "Actual allocation cannot contain original3300s envelope plus10s preservation")
        native = b.native_api(SHARED)
        native.verify_runtime(source, runtime)
        b.need(native.allocation_guard() == allocation, "Actual native allocation differs")
        batch = b.importlib.import_module("hpc_forest.matrix15_first_batch")
        gate = b.read_json(b.read_ref(config["first_batch_gate"]))
        gate_check = validate_first_batch_gate(b, gate, native, batch, plan_raw)
        receipt["first_batch_gate_verified"] = gate_check
        b.save(admission / "ZERO-MODEL-MARKER.json", b.marker(binding, allocation, admission, started_at, outer_deadline))
        auth_path, auth_raw, commit_path, commit_raw = b.wait_for_authorization(admission, started_monotonic)
        b.need(time.monotonic() - started_monotonic < 600, "Original admission clock expired before validation")
        auth = native.validate_receipt(auth_path, {SCOPE}, runtime=True)
        b.need(native.cell_binding(auth) == binding and time.time() < auth["expires_at"] <= min(started_at + 3300, outer_deadline, b.DEADLINE),
               "Exact cell authorization or original execution expiry differs")
        b.need(b.regular_bytes(auth_path) == auth_raw and b.regular_bytes(commit_path) == commit_raw,
               "Authorization/commit changed during admission")
        # The gate and375 shared files are unchanged immediately before launch.
        b.read_ref(config["first_batch_gate"])
        verify_immutable_shared(b, Path(SHARED), manifest)
        b.need(all(b.absent(path) for path in b.scientific_paths(binding).values()), "Own scientific paths changed")
        child = [b.PYTHON, "-B", SHARED + "/project/examples/marathon22/forest_matrix15.py", "--root", binding["remote_root"],
                 "--shared", SHARED, "--authorization", str(auth_path), "--cell-key", binding["cell_key"]]
        receipt.update(admission_accepted=True, authorization_sha256=b.sha(auth_raw), admission_elapsed_seconds=time.monotonic() - started_monotonic)
        b.save(admission / "authorization-accepted.json", {**receipt, "argv": child, "runtime_validated": True,
               "authorization_commit_sha256": b.sha(commit_raw), "observed_at": time.time()})
        maximum_seconds = min(2700, started_monotonic + 3300 - time.monotonic())
        b.need(time.monotonic() - started_monotonic < 600 and maximum_seconds > 0, "Original clock expired immediately before launch")
        environment = dict(b.os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="1")
        with (admission / "runner.stdout").open("xb") as stdout, (admission / "runner.stderr").open("xb") as stderr:
            receipt["native_child_launch_attempted"] = True
            code = b.run_native(child, environment, stdout, stderr, maximum_seconds)
        receipt.update(native_child_returncode=code, shared_unchanged_after_runner=b.inventory(SHARED) == manifest["files"])
        receipt["passed"] = code == 0 and receipt["shared_unchanged_after_runner"]
    except Exception as exc:  # noqa: BLE001 - once-only negative, never repair/replay.
        receipt.update(error_type=type(exc).__name__, error=str(exc), passed=False)
    finally:
        receipt.update(bootstrap_elapsed_seconds=time.monotonic() - started_monotonic, finished_at=time.time())
        b.save(admission / "bootstrap-result.json", receipt)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
