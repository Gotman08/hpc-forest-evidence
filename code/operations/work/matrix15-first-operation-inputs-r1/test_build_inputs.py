"""NEUTRAL local builder fixtures. No CLI, census, auth, transport, or job calls.

Real fixed source127/static/Q-bridge/review/closure refs are read. Only a fresh
CLI-observation validator is replaced in the fixture; real production has no
such switch. Raw ARM observations below are synthetic and never submitted.
"""
from __future__ import annotations

import copy
import importlib.util
import os
import time
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("first_inputs_under_test", Path(__file__).with_name("build_inputs.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
BASE = builder.BASE


@pytest.fixture(params=["r1", "r2"])
def case(tmp_path, monkeypatch, request):
    reader = builder.reader_runtime()
    base_name = "base-r2" if request.param == "r1" else "base-r3"
    original = reader.parse((BASE / f"outputs/HPC-Forest-Matrice15-Execution-root-01/preparation/{base_name}/PREPARED.json").read_bytes())
    reader, dynamic, capacity = builder.runtime(original)
    monkeypatch.setattr(builder, "runtime", lambda bundle=None: (reader, dynamic, capacity))
    monkeypatch.setattr(builder, "DEST", tmp_path)
    monkeypatch.setattr(dynamic, "assemble", lambda *a, **k: pytest.fail("Assembler must never be invoked"))
    monkeypatch.setattr(capacity, "collect_windows", lambda: pytest.fail("Census must never be collected"))
    monkeypatch.setattr(dynamic, "validate_cli_observation", lambda ref, now: ({}, {}))
    prepared = copy.deepcopy(original)
    prepared.update(windows_cache=str(tmp_path / "absent-cache"), output_windows=str(tmp_path / "absent-admission"),
                    capacity_registry=str(tmp_path / "capacity-registry"))
    Path(prepared["capacity_registry"]).mkdir()
    def write(name, value=None, raw=None):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else reader.encoded(value))
        return builder.ref(reader, path)
    prepared_ref = write("PREPARED.json", prepared)
    refs = builder.object_ref(reader, prepared["statics"])["artifacts"]
    plan = builder.object_ref(reader, refs["plan"])
    subject = dynamic.contract.resolve_subject(plan, dynamic.FIRST_CELL)
    authorization = {**{k: subject[k] for k in ("cell_key", "subject_id", "model", "effort", "session_id")},
        "scope_id": dynamic.contract.SCOPE, "job_id": "12345", "remote_root": builder.FIRST_ROOT, "artifacts": refs}
    binding = dynamic.native.cell_binding(authorization)
    now = time.time()
    marker = {"schema": dynamic.MARKER_SCHEMA, "binding": binding, "native_model_calls": 0,
        "admission_root": builder.FIRST_ROOT + "-admission", "admission_started_at": now - 10,
        "observed_at": now - 1, "allocation_outer_deadline": now + 3600,
        "scientific_paths": {"root": builder.FIRST_ROOT, "mailbox": builder.FIRST_ROOT + "/results-12345/mailbox",
            "registry": builder.FIRST_ROOT + "/results-12345/2020-quicksort/registry.sqlite3"},
        "allocation": {"job_id": "12345", "architecture": "aarch64", "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0, "affinity_cpu_count": 4},
        "source_runtime_verified": True, "scientific_root_observed_absent": True,
        "scientific_mailbox_observed_absent": True, "scientific_registry_observed_absent": True}
    marker_ref = write("marker.json", marker)
    def observation(name, tool, arguments, payload):
        return write(name, {"schema": dynamic.OBS_SCHEMA, "tool": tool, "arguments": arguments,
            "observed_at": now, "response": {"structuredContent": payload, "isError": False}})
    marker_path = builder.FIRST_ROOT + "-admission/ZERO-MODEL-MARKER.json"
    marker_readback = observation("marker-readback.json", "mcp__romeo__read_remote_file", {"path": marker_path, "offset": 1},
        {"ok": True, "path": marker_path, "offset": 1, "limit": 2000, "total_lines": len(reader.encoded(marker).splitlines()),
         "truncated": False, "content": Path(marker_ref["path"]).read_text(encoding="utf8")})
    status = observation("status.json", "mcp__romeo__job_status", {"job_id": "12345"},
        {"ok": True, "job_id": "12345", "state": "RUNNING", "finished": False})
    arm_refs = builder.object_ref(reader, prepared["statics_arm"])
    transfers = {}
    for key, local in {**refs, "subject_qualification": prepared["subject_qualification"]}.items():
        readback = write("readback/" + key, raw=Path(local["path"]).read_bytes())
        remote = arm_refs[key]["path"] if key in arm_refs else "/gpfs/scratch/received-quicksort-qualification.json"
        size = Path(local["path"]).stat().st_size
        raw = observation("transfers/" + key + ".json", "mcp__romeo__download_from_romeo",
            {"remote_path": remote, "local_path": readback["path"], "verify": True},
            {"ok": True, "transport": "scp", "downloaded": remote, "to": readback["path"], "bytes": size,
             "verifie": True, "empreinte_locale": local["sha256"], "empreinte_distante": local["sha256"],
             "remote_sha256": local["sha256"]})
        transfers[key] = {"local": local, "remote_path": remote, "sha256": local["sha256"], "bytes": size,
                          "raw": raw, "readback": readback}
    value = {"schema": builder.INPUT_SCHEMA, "mode": "BUILD", "prepared": prepared_ref, "marker": marker_ref,
        "marker_readback": marker_readback, "job_status": status, "transfers": transfers,
        "cli_observation": write("cli-observation-placeholder.json", {"not_production": True}),
        "owned_worker_receipts": [], "output_directory": str(tmp_path / "built")}
    return reader, dynamic, capacity, write, value, marker, prepared


def call(case):
    _reader, _dynamic, _capacity, write, value, _marker, _prepared = case
    return builder.build(write("input.json", value))


def test_full_builder_graph_has_no_census_or_assembler(case):
    reader, dynamic, _capacity, _write, value, marker, _prepared = case
    result_ref = call(case)
    result = builder.object_ref(reader, result_ref)
    assert set(result) == set(dynamic.template())
    assert result["expires_at"] == marker["admission_started_at"] + 3300
    assert result["output_arm"] == builder.FIRST_ROOT + "-admission"
    assert set(result["capacity_evidence"]) == {"reservation_producer_review", "local_projection_producer_review",
                                                "source_only_received_closure", "owned_worker_receipts"}
    out = Path(value["output_directory"])
    assert not (out / "source_only_absence.json").exists()
    assert not (out / "other_owned_worker_reconciliation.json").exists()
    receipt = reader.parse((out / "BUILDER-RECEIPT.json").read_bytes())
    assert receipt["capacity_observed"] is False
    assert receipt["assemble_invoked"] is False
    assert not Path(result["windows_cache"]).exists()
    assert not Path(result["output_windows"]).exists()


def test_prepared_default_cannot_build_actual_binding(case):
    case[4]["mode"] = "PREPARE"
    with pytest.raises((ValueError, RuntimeError), match="PREPARE"):
        call(case)


@pytest.mark.parametrize("field", ["marker", "marker_readback", "job_status", "transfers", "cli_observation"])
def test_missing_real_binding_inputs_refused(case, field):
    case[4][field] = None
    with pytest.raises((ValueError, RuntimeError), match="PREPARE"):
        call(case)


@pytest.mark.parametrize("change", ["foreign_session", "foreign_job", "stale", "model_started", "negative", "existing_paths"])
def test_resealed_marker_semantic_changes_refuse(case, change):
    _reader, _dynamic, _capacity, write, value, marker, _prepared = case
    if change == "foreign_session":
        marker["binding"]["session_id"] = "f" * 32
    elif change == "foreign_job":
        marker["binding"]["job_id"] = "99999"
    elif change == "stale":
        marker["admission_started_at"] -= 600
        marker["observed_at"] -= 600
    elif change == "model_started":
        marker["native_model_calls"] = 1
    elif change == "negative":
        marker["verified"] = False
    else:
        marker["scientific_root_observed_absent"] = False
    value["marker"] = write("marker-changed.json", marker)
    with pytest.raises((ValueError, RuntimeError)):
        call(case)


def test_resealed_raw_status_failure_refused(case):
    reader, _dynamic, _capacity, write, value, _marker, _prepared = case
    raw = builder.object_ref(reader, value["job_status"])
    raw["response"]["structuredContent"]["state"] = "FAILED"
    raw["response"]["structuredContent"]["finished"] = True
    value["job_status"] = write("status-failed.json", raw)
    with pytest.raises((ValueError, RuntimeError), match="RUNNING"):
        call(case)


def test_fresh_cli_is_validated_and_stale_refusal_propagates(case, monkeypatch):
    _reader, dynamic, _capacity, _write, _value, _marker, _prepared = case
    def stale(_ref, *, now):
        dynamic.need(False, "Observation stale")
    monkeypatch.setattr(dynamic, "validate_cli_observation", stale)
    with pytest.raises((ValueError, RuntimeError), match="stale"):
        call(case)


def test_unverified_scp_transfer_even_resealed_refuses(case):
    reader, _dynamic, _capacity, write, value, _marker, _prepared = case
    transfer = value["transfers"]["plan"]
    raw = builder.object_ref(reader, transfer["raw"])
    raw["response"]["structuredContent"]["verifie"] = False
    transfer["raw"] = write("plan-scp-failed.json", raw)
    with pytest.raises((ValueError, RuntimeError), match="SCP"):
        call(case)


def test_wrong_final_shared_path_is_not_rewritten(case):
    case[4]["transfers"]["plan"]["remote_path"] = "/gpfs/scratch/wrong-plan.json"
    with pytest.raises((ValueError, RuntimeError), match="final shared"):
        call(case)


def test_exact_nine_transfers_required(case):
    del case[4]["transfers"]["harness"]
    with pytest.raises((ValueError, RuntimeError), match="nine"):
        call(case)


def test_output_is_exclusive(case):
    call(case)
    with pytest.raises((ValueError, RuntimeError), match="New owned"):
        call(case)


def test_parent_traversal_output_refused(case, tmp_path):
    case[4]["output_directory"] = str(tmp_path / ".." / "outside-builder-ownership")
    with pytest.raises((ValueError, RuntimeError), match="parent traversal"):
        call(case)
    assert not (tmp_path.parent / "outside-builder-ownership").exists()


def test_output_outside_boundary_refused_before_filesystem_walk(case, tmp_path):
    case[4]["output_directory"] = str(tmp_path.parent / "different-owned-boundary")
    with pytest.raises((ValueError, RuntimeError), match="owned output"):
        call(case)
    assert not (tmp_path.parent / "different-owned-boundary").exists()


def test_output_link_or_junction_ancestor_refused(case, tmp_path, monkeypatch):
    target, redirect = tmp_path / "target", tmp_path / "redirect"
    target.mkdir()
    try:
        os.symlink(target, redirect, target_is_directory=True)
    except OSError:
        # Some Windows hosts do not permit creating symlinks. Exercise the real
        # Path.is_junction branch with a positive metadata observation there.
        redirect.mkdir()
        original = Path.is_junction
        monkeypatch.setattr(Path, "is_junction", lambda path: path == redirect or original(path))
    case[4]["output_directory"] = str(redirect / "must-not-create")
    with pytest.raises((ValueError, RuntimeError), match="junction output ancestor"):
        call(case)
    assert not (target / "must-not-create").exists()


def test_no_clock_or_census_cli_options():
    with pytest.raises(SystemExit):
        builder.main(["build", "--input", "x", "--input-sha256", "a" * 64, "--now", "1"])


def test_resealed_missing_closed_cohort_refuses(case):
    _reader, _dynamic, _capacity, write, value, _marker, prepared = case
    del prepared["closure_primary"]["receipts"]["gpt-6-astra"]
    value["prepared"] = write("prepared-missing-cohort.json", prepared)
    with pytest.raises((ValueError, RuntimeError), match="four closed"):
        call(case)


def test_resealed_not_closed_global_primary_refuses(case):
    reader, _dynamic, _capacity, write, value, _marker, prepared = case
    global_closure = builder.object_ref(reader, prepared["closure_primary"]["global_closure"])
    global_closure["new_generation_or_OBS4_transition_authorized"] = True
    prepared["closure_primary"]["global_closure"] = write("changed-global-closure.json", global_closure)
    value["prepared"] = write("prepared-changed-global.json", prepared)
    with pytest.raises((ValueError, RuntimeError), match="global closure"):
        call(case)


def test_unapproved_explicit_source_selection_cannot_import(case):
    reader = case[0]
    bundle = {"producer": {"path": str(BASE / "outputs/HPC-Forest-Matrice15-Admission-Dynamique-Preparation-r1/dynamic_admission.py"),
                            "sha256": "f" * 64},
              "helper": builder.ref(reader, BASE / "outputs/HPC-Forest-Matrice15-Admission-Dynamique-Preparation-r1/capacity.py")}
    # Call the original function, outside the fixture's stable runtime selector.
    fresh = builder.load_file("original_builder_for_selection", Path(builder.__file__), reader.sha(Path(builder.__file__).read_bytes()))
    with pytest.raises((ValueError, RuntimeError), match="Primary evidence changed"):
        fresh.runtime(bundle)


def test_r2_canonical_line_count_matches_unchanged_raw(case):
    reader, _old_dynamic, _capacity, write, value, _marker, prepared = case
    path = BASE / "work/matrix15-dynamic-admission-r2/dynamic_admission.py"
    dynamic = builder.load_file("r2_line_count_under_test", path,
        "806bb6bea6e0bb6141b66fd6170f230c91b18dd54e71d99ed78aa1e35759f132")
    raw = builder.object_ref(reader, value["marker_readback"])
    raw["response"]["structuredContent"]["total_lines"] = str(raw["response"]["structuredContent"]["total_lines"])
    readback_ref = write("marker-readback-canonical-string.json", raw)
    refs = builder.object_ref(reader, prepared["statics"])["artifacts"]
    binding = builder.object_ref(reader, value["marker"])["binding"]
    arm = {"schema": dynamic.ARM_SCHEMA, "binding": binding, "observed_at": time.time(), "marker": value["marker"],
           "marker_readback": readback_ref, "job_id_observation": value["job_status"], "transfers": value["transfers"]}
    arm_ref = write("arm-canonical-string.json", arm)
    value, _marker, _evidence = dynamic.check_arm(arm_ref, binding, refs, prepared["subject_qualification"], now=time.time())
    assert value["marker_readback"] == readback_ref
    assert builder.object_ref(reader, readback_ref) == raw


def test_r2_full_builder_accepts_real_mcp_count_shape(case):
    reader, dynamic, _capacity, write, value, _marker, prepared = case
    raw = builder.object_ref(reader, value["marker_readback"])
    raw["response"]["structuredContent"]["total_lines"] = str(raw["response"]["structuredContent"]["total_lines"])
    value["marker_readback"] = write("actual-shape-line-count.json", raw)
    if prepared["producer"]["sha256"] == builder.PRODUCER_SHA:
        with pytest.raises(RuntimeError, match="Whole exact"):
            call(case)  # R1's unchanged refusal is the discovered defect.
    else:
        result = builder.object_ref(reader, call(case))
        assert set(result) == set(dynamic.template())
