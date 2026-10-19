"""Small local regressions; no test builds a positive operational authorization."""
from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
import json
import socket
import struct
import subprocess
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("neutral_extension_operation_builder", HERE / "build_inputs.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
CELL = "forest-r2/gpt-6.1-sol/max/2023-count/seed-23"


@pytest.fixture(autouse=True)
def no_operational_activity(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Input-builder test attempted process, network, census, admission or probe")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    previous = sys.getprofile()

    def guard(frame, event, _arg):
        if event == "call" and frame.f_code.co_name in {"assemble", "probe_cli", "collect_windows", "exclusive_capacity"}:
            forbidden()

    sys.setprofile(guard)
    try:
        yield
    finally:
        sys.setprofile(previous)


@pytest.fixture(scope="module")
def runtime_data():
    return builder.runtime()


@pytest.fixture(scope="module")
def owned_directory():
    with tempfile.TemporaryDirectory(prefix="NEUTRAL-builder-tests-", dir=builder.WORK) as name:
        yield Path(name)


@pytest.fixture(scope="module")
def prepared(owned_directory):
    return builder.prepare(owned_directory / "prepare", CELL)


def put(reader, directory, name, value):
    path = directory / name
    path.write_bytes((json.dumps(value, sort_keys=True) + "\n").encode())
    return builder.ref(reader, path)


def negative_build(reader, prepared_ref, directory, name):
    """Complete syntax only; the nonexistent gate is bypassed solely for refusal tests."""
    data = copy.deepcopy(builder.read_ref(reader, prepared_ref))
    prior = put(reader, directory, name + "-missing-gate.json", {key: None for key in builder.PREREQUISITE_FIELDS})
    data["prerequisite_ref"] = prior
    prepared_copy = put(reader, directory, name + "-prepared.json", data)
    binding = {**data["binding_without_job_id"], "job_id": "1"}
    # No verified flag and no real allocation/call assertion; never reaches check_arm.
    marker = put(reader, directory, name + "-unadmitted-marker.json", {"binding": binding})
    inputs = {"schema": builder.INPUT_SCHEMA, "mode": "BUILD", "prepared": prepared_copy,
              "marker": marker, "marker_readback": marker, "job_status": marker, "transfers": {},
              "cli_observation": marker, "owned_worker_receipts": [],
              "output_directory": str(directory / (name + "-output"))}
    return data, inputs


def bypass_only_absent_prerequisite(monkeypatch, runtime_data):
    dynamic = runtime_data[2]
    cell = copy.deepcopy(dynamic.contract.REGISTERED_CELLS[CELL])

    def only_cell(_dynamic, _reader, _value, cell_key, _registry):
        assert cell_key == CELL
        return None, copy.deepcopy(cell)

    monkeypatch.setattr(builder, "prerequisites", only_cell)


def test_actual_runtime_bootstrap_reviews_and_historical_closure_are_pinned(runtime_data):
    upstream, reader, dynamic, _capacity, bootstrap = runtime_data
    assert builder.FIRST_BUILDER_SHA == "e7295bb03e956dc343c70eaabcfca98f240c3b3643963c3381f2013edb6a4124"
    assert builder.BOOT_PINS["job_prefix.py"] == "ed7c7ad59aa06d905f259e97a0bd83f2af3ed9be006d977bef3c46e92512db16"
    assert dynamic.SOURCE_SHA256 == "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
    assert bootstrap.PLAN_SHA == dynamic.PLAN_SHA256
    for name, checksum in builder.PINS.items():
        assert builder.ref(reader, builder.DELIVERY / name)["sha256"] == checksum
    closure = upstream.closure_primary(reader)
    assert closure["coordinator"]["sha256"] == "dbb0695d71789ab8f1ffc6bd6bc7271796cf363f3b97b13ae35d0f253ade539c"
    assert closure["global_closure"]["sha256"] == "cd7823488980ccf5dc0065c4484829ecd757970490e1b0011650061651bd0857"
    assert len(upstream.verify_closure(reader, closure)) > 0
    review_refs, reviewer = builder.reviewed_evidence(reader)
    assert {Path(item["path"]).name for item in review_refs} == {
        "REVUE-LECTURE-FRAICHE.json", "TESTS-NEUTRES-r1.xml", "FILES.sha256.json"} and reviewer


def test_prepare_emits_false_defaults_null_gate_and_no_commands(runtime_data, prepared):
    _upstream, reader, dynamic, _capacity, _bootstrap = runtime_data
    data = builder.read_ref(reader, prepared)
    directory = Path(prepared["path"]).parent
    bootstrap_input = reader.parse((directory / "INPUT-BOOTSTRAP.json").read_bytes())
    dynamic_input = reader.parse((directory / "INPUT-DYNAMIC-TEMPLATE.json").read_bytes())
    request = reader.parse((directory / "INPUT-BUILDER-TEMPLATE.json").read_bytes())
    receipt = reader.parse((directory / "PREPARATION.json").read_bytes())
    assert data["verified"] is False and data["prerequisite_ref"] is None
    assert data["commands_to_execute"] == [] and data["native_execution_authorized"] is False
    assert bootstrap_input["first_batch_gate"] is None
    assert bootstrap_input["native_execution_authorized_by_this_input"] is False
    assert dynamic_input == dynamic.template(CELL) and dynamic_input["mode"] == "PREPARE"
    assert all(dynamic_input[key] is None for key in ("first_batch_extension_gate", "first_batch_received_evidence", "selection_state"))
    assert request["mode"] == "PREPARE" and request["marker"] is request["cli_observation"] is None
    assert receipt["verified"] is False and receipt["prerequisite_verified"] is False
    assert receipt["commands_to_execute"] == [] and receipt["native_model_calls"] == receipt["jobs_submitted"] == 0


def test_bootstrap_pure_selection_closes_all_sixty_max_sessions(runtime_data):
    _upstream, reader, dynamic, _capacity, bootstrap = runtime_data
    refs, plan, _aliases = dynamic.static_inputs(builder.ref(reader, builder.STATICS / "STATICS.json"))
    helper = bootstrap.load_helper((builder.BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    raw = Path(refs["plan"]["path"]).read_bytes()
    sessions = set()
    for key, cell in dynamic.contract.REGISTERED_CELLS.items():
        _plan, binding = bootstrap.registered_selection(helper, raw, key)
        assert all(binding[field] == item for field, item in cell.items()) and binding["effort"] == "max"
        sessions.add(binding["session_id"])
    assert len(plan["cells"]) == len(sessions) == 60


@pytest.mark.parametrize("cell", ["unknown", "forest-r2/gpt-6-luna/high/2020-quicksort/seed-23"])
def test_unknown_or_nonmax_cell_is_refused_before_any_output(owned_directory, cell):
    output = owned_directory / "bad-cell"
    with pytest.raises(ValueError, match="Closed sixty-cell"):
        builder.prepare(output, cell)
    assert not output.exists()


def test_output_boundaries_reject_roots_escape_and_parent_traversal(runtime_data, owned_directory):
    reader = runtime_data[1]
    for path in (builder.WORK, builder.OUTPUT, owned_directory.parent.parent / "outside-builder",
                 owned_directory / ".." / "traversal"):
        with pytest.raises(ValueError, match="owned roots|escapes ownership"):
            builder.owned_output(reader, path)


def test_prepare_cannot_overwrite_prior_bytes(prepared):
    directory = Path(prepared["path"]).parent
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(ValueError, match="Output exists"):
        builder.prepare(directory, CELL)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


def test_output_junction_is_refused_without_a_helper_process(runtime_data, owned_directory):
    link, target = owned_directory / "junction", owned_directory / "physical"
    link.mkdir()
    target.mkdir()
    substitute, printed = ("\\??\\" + str(target)).encode("utf-16-le"), str(target).encode("utf-16-le")
    paths = substitute + b"\0\0" + printed + b"\0\0"
    data = struct.pack("<IHHHHHH", 0xA0000003, 8 + len(paths), 0, 0, len(substitute), len(substitute) + 2, len(printed)) + paths
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(link), 0x40000000, 7, None, 3, 0x02200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer, returned = ctypes.create_string_buffer(data), wintypes.DWORD()
        if not kernel.DeviceIoControl(handle, 0x000900A4, buffer, len(data), None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)
    assert link.is_junction()
    with pytest.raises(ValueError, match="Linked output ancestor"):
        builder.owned_output(runtime_data[1], link / "new-output")


def test_incomplete_build_never_writes_positive_roles_or_dynamic_input(runtime_data, prepared, owned_directory):
    reader = runtime_data[1]
    template = reader.parse((Path(prepared["path"]).parent / "INPUT-BUILDER-TEMPLATE.json").read_bytes())
    for mode in ("PREPARE", "BUILD"):
        inputs = {**template, "mode": mode, "output_directory": str(owned_directory / (mode + "-incomplete"))}
        ref = put(reader, owned_directory, mode + "-input.json", inputs)
        result = builder.build(ref)
        receipt = builder.read_ref(reader, result)
        assert receipt["verified"] is False and receipt["mode"] == "PREPARE"
        assert receipt["dynamic_input"] is None and receipt["commands_to_execute"] == []
        assert receipt["native_authorization"] is False and receipt["native_model_calls"] == 0
        assert len(list(Path(result["path"]).parent.iterdir())) == 1


def test_optional_prerequisites_need_real_gate_inventory_and_ledger(runtime_data, owned_directory):
    reader = runtime_data[1]
    prior = put(reader, owned_directory, "absent-prerequisites.json", {key: None for key in builder.PREREQUISITE_FIELDS})
    output = owned_directory / "must-not-prepare-with-gate"
    with pytest.raises(ValueError):
        builder.prepare(output, CELL, prior)
    assert not output.exists()


def test_prepared_source_hashes_cannot_be_reselected(runtime_data, prepared, owned_directory):
    reader = runtime_data[1]
    data, inputs = negative_build(reader, prepared, owned_directory, "source-drift")
    data["locked_sources"]["dynamic_admission.py"]["sha256"] = "0" * 64
    inputs["prepared"] = put(reader, owned_directory, "source-drift-sealed.json", data)
    with pytest.raises(ValueError, match="source selection cannot be overridden"):
        builder.build(put(reader, owned_directory, "source-drift-input.json", inputs))
    assert not Path(inputs["output_directory"]).exists()


def test_prepared_fixed_roots_config_and_closure_cannot_be_overridden(runtime_data, prepared, owned_directory, monkeypatch):
    reader = runtime_data[1]
    bypass_only_absent_prerequisite(monkeypatch, runtime_data)
    for field in ("capacity_registry", "windows_cache", "codex_config", "closure_primary"):
        data, inputs = negative_build(reader, prepared, owned_directory, field)
        data[field] = "override" if field != "closure_primary" else {}
        inputs["prepared"] = put(reader, owned_directory, field + "-changed.json", data)
        with pytest.raises(ValueError, match="cannot be overridden"):
            builder.build(put(reader, owned_directory, field + "-input.json", inputs))
        assert not Path(inputs["output_directory"]).exists()


def test_marker_of_another_cell_is_refused_before_cli_or_arm(runtime_data, prepared, owned_directory, monkeypatch):
    reader = runtime_data[1]
    bypass_only_absent_prerequisite(monkeypatch, runtime_data)
    _data, inputs = negative_build(reader, prepared, owned_directory, "wrong-marker")
    marker = builder.read_ref(reader, inputs["marker"])
    marker["binding"]["session_id"] = "0" * 32
    inputs["marker"] = put(reader, owned_directory, "wrong-marker-binding.json", marker)
    with pytest.raises(ValueError, match="another registered cell"):
        builder.build(put(reader, owned_directory, "wrong-marker-input.json", inputs))


def test_stale_real_cli_observation_blocks_build_without_replaying_probe(runtime_data, prepared, owned_directory, monkeypatch):
    reader = runtime_data[1]
    bypass_only_absent_prerequisite(monkeypatch, runtime_data)
    _data, inputs = negative_build(reader, prepared, owned_directory, "stale-cli")
    path = builder.BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/cli-observation-before-submit-r3/CLI-OBSERVATION.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "e59437601e33d0032c00153b4001f4f03235d3e841189a20ef6c26b1639be000"
    inputs["cli_observation"] = builder.ref(reader, path)
    with pytest.raises(runtime_data[2].InfrastructureError, match="stale, future or untyped"):
        builder.build(put(reader, owned_directory, "stale-cli-input.json", inputs))
    assert not Path(inputs["output_directory"]).exists()


def test_stale_real_arm_observation_is_rejected_before_marker_checks(runtime_data):
    _upstream, reader, dynamic, _capacity, _bootstrap = runtime_data
    path = builder.BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/preparation/actual-binding-r1/ARM-OBSERVATION.json"
    value = reader.parse(path.read_bytes())
    with pytest.raises(dynamic.InfrastructureError, match="stale, future or untyped"):
        dynamic.check_arm(builder.ref(reader, path), value["binding"], {}, None, now=value["observed_at"] + 601)


def test_historical_review_cannot_substitute_for_all_eight_current_refs(runtime_data):
    _upstream, reader, dynamic, _capacity, _bootstrap = runtime_data
    statics, _plan, _aliases = dynamic.static_inputs(builder.ref(reader, builder.STATICS / "STATICS.json"))
    required = [statics["source_zip"], statics["plan"],
                *[builder.ref(reader, builder.DELIVERY / name) for name in builder.PINS],
                builder.ref(reader, dynamic.COLD_READER)]
    assert len(required) == len({item["path"] for item in required}) == 8
    path = builder.BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/preparation/actual-binding-r1/INTEGRATION-REVIEW.json"
    with pytest.raises(dynamic.InfrastructureError, match="exact closed producer dependency set"):
        dynamic.review_input(builder.ref(reader, path), {"source_zip_sha256": dynamic.SOURCE_SHA256,
            "plan_sha256": dynamic.PLAN_SHA256}, required)


def test_owned_receipt_requires_two_real_identities_in_child_parent_order(runtime_data, owned_directory):
    _upstream, reader, _dynamic, capacity, _bootstrap = runtime_data
    path = builder.BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/worker-launch-r1/CIM-IDENTITES-REELLES-r1.json"
    sample = reader.parse(path.read_bytes())
    processes = [row for row in sample["processes"] if row["ExecutablePath"].lower().endswith("python.exe")]
    assert len(processes) == 2
    # Both malformed receipts are refusals; neither becomes usable owned evidence.
    for rows in (processes[:1], processes):
        value = {"schema": "hpc-forest-native-owned-worker-identity-v1", "verified": True,
                 "ownership_established": True, "session_id": sample["session_id"],
                 "channel": capacity.argument(processes[0]["CommandLine"], "--channel"), "processes": rows}
        ref = put(reader, owned_directory, f"wrong-owned-order-{len(rows)}.json", value)
        with pytest.raises(ValueError, match="two-process|exact \\[base child,venv parent\\]"):
            builder.owned_receipts(reader, capacity, [ref], sample["observed_at"])


def test_builder_input_hash_is_rechecked_before_any_output(runtime_data, prepared, owned_directory):
    reader = runtime_data[1]
    template = reader.parse((Path(prepared["path"]).parent / "INPUT-BUILDER-TEMPLATE.json").read_bytes())
    ref = put(reader, owned_directory, "changed-input.json", template)
    Path(ref["path"]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="Referenced bytes changed"):
        builder.build(ref)


def test_supplied_empty_prerequisite_is_rejected_without_a_positive_flag(runtime_data, owned_directory):
    reader = runtime_data[1]
    prior = put(reader, owned_directory, "empty-prerequisites.json", {})
    output = owned_directory / "empty-prerequisite-preparation"
    with pytest.raises(ValueError, match="Exact continuation prerequisite refs"):
        builder.prepare(output, CELL, prior)
    assert not output.exists()


def test_role_primary_evidence_does_not_promote_the_false_preparation_report(runtime_data):
    reader = runtime_data[1]
    primary_refs, _reviewer = builder.reviewed_evidence(reader)
    validation = builder.ref(reader, builder.DELIVERY / "VALIDATION-LOCALE.json")
    assert builder.read_ref(reader, validation)["verified"] is False
    assert validation not in primary_refs
    for item in primary_refs:
        raw = reader.ordinary(item["path"]).read_bytes()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue  # XML report remains actual nonempty textual evidence.
        assert isinstance(value, dict) and value.get("verified") is not False
        assert not any(value.get(key) is True for key in ("fixture", "test_only", "neutral"))
