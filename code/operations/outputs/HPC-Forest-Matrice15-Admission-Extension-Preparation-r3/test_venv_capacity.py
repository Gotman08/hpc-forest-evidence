"""Pure/temporary-file tests of pinned Windows venv pairs, never a live census.

The one saved ROOT observation replay is explicitly a partial three-line sample.
It proves classifier behavior only and cannot establish admission or free capacity.
"""
from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
import json
import os
import struct
import sys
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
NOW = 1800000000.0
RUNTIME_PIN = "049c5c1602814ec3541fcaa414f9c70dec4ecebbee9017414fbca9510be72f88"
ROOT_SAMPLE = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/worker-launch-r1/CIM-IDENTITES-REELLES-r1.json"
ROOT_SAMPLE_SHA = "840f1c77fe6f438575fffe795e88346a5358de0d52bba3887a2b944713a492aa"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = load_file("neutral_venv_capacity", HERE / "capacity.py")
with patch.dict(sys.modules, {"capacity": cap}):
    legacy = load_file("neutral_venv_capacity_legacy_fixtures", HERE / "test_capacity.py")


@pytest.fixture(autouse=True)
def no_live_activity(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Venv regression attempted real collection or process execution")

    monkeypatch.setattr(cap, "collect_windows", forbidden)
    monkeypatch.setattr(cap.subprocess, "run", forbidden)
    monkeypatch.setattr(cap.subprocess, "Popen", forbidden)


@pytest.fixture
def identity():
    root = r"C:\NEUTRAL runtime\venv"
    home = r"C:\NEUTRAL runtime\base"
    return {"schema": cap.VENV_IDENTITY_SCHEMA, "venv_root": root,
            "launcher": {"path": root + r"\Scripts\python.exe", "sha256": "1" * 64},
            "base_python": {"path": home + r"\python.exe", "sha256": "2" * 64},
            "pyvenv_cfg": {"path": root + r"\pyvenv.cfg", "sha256": "3" * 64},
            "home": home, "executable": home + r"\python.exe", "version": "3.13.4"}


def instant(offset):
    return datetime.fromtimestamp(NOW + offset, UTC).isoformat()


def pair(identity, *, pid=10, session="b" * 32, channel="/NEUTRAL/mailbox"):
    command = (f'"{identity["launcher"]["path"]}" -B -m hpc_forest.matrix15_worker '
               f'--session-id {session} --channel {channel}')
    parent = {"ProcessId": pid, "ParentProcessId": 99999, "ExecutablePath": identity["launcher"]["path"],
              "CommandLine": command, "CreationDate": instant(-60)}
    child = {"ProcessId": pid + 1, "ParentProcessId": pid, "ExecutablePath": identity["base_python"]["path"],
             "CommandLine": command, "CreationDate": instant(-59)}
    return [parent, child]


def classify(processes, identity):
    return cap.classify_processes(processes, NOW, venv_identity=identity)


def assert_refused_or_not_fused(processes, identity):
    try:
        result = classify(processes, identity)
    except cap.CapacityError:
        return
    assert result["private_windows_venv_pairs_count"] == 0
    assert all(len(group) == 1 for group in result["private_native_groups"])


def write_json(path, value):
    path.write_bytes((json.dumps(value, sort_keys=True, indent=2) + "\n").encode())
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def local_runtime(tmp_path, monkeypatch):
    root, home = tmp_path / "NEUTRAL venv", tmp_path / "NEUTRAL base"
    (root / "Scripts").mkdir(parents=True)
    home.mkdir()
    launcher, base, cfg = root / "Scripts/python.exe", home / "python.exe", root / "pyvenv.cfg"
    launcher.write_bytes(b"MZ\x00NEUTRAL redirector bytes")
    base.write_bytes(b"MZ\x00NEUTRAL base interpreter bytes")
    config = {"home": str(home), "include-system-site-packages": "false", "version": "3.13.4",
              "executable": str(base), "command": str(base) + " -m venv " + str(root)}
    cfg.write_text("\n".join(f"{key} = {value}" for key, value in config.items()) + "\n", encoding="utf8")

    def ref(path):
        return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    value = {"schema": cap.VENV_IDENTITY_SCHEMA, "venv_root": str(root), "launcher": ref(launcher),
             "base_python": ref(base), "pyvenv_cfg": ref(cfg), "home": str(home),
             "executable": str(base), "version": "3.13.4"}
    sidecar = tmp_path / "NEUTRAL-VENV-RUNTIME-IDENTITY.json"

    def repin():
        proof = write_json(sidecar, value)
        monkeypatch.setattr(cap, "VENV_IDENTITY_PATH", sidecar)
        monkeypatch.setattr(cap, "VENV_IDENTITY_SHA256", proof["sha256"])

    repin()
    return {"value": value, "sidecar": sidecar, "repin": repin, "config": config,
            "files": {"launcher": launcher, "base_python": base, "pyvenv_cfg": cfg}}


@pytest.fixture
def capacity_fixture():
    fixture = legacy.CapacityFixtures(methodName="runTest")
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.tearDown()


def test_live_sidecar_has_the_hard_pin_and_explicit_opt_in_schema():
    raw = (HERE / "VENV-RUNTIME-IDENTITY.json").read_bytes()
    assert cap.VENV_IDENTITY_SHA256 == RUNTIME_PIN
    assert hashlib.sha256(raw).hexdigest() == RUNTIME_PIN
    value = cap.validate_venv_identity(json.loads(raw))
    assert value["schema"] == "hpc-forest-windows-venv-interpreter-pair-v1"
    assert set(value["launcher"]) == set(value["base_python"]) == set(value["pyvenv_cfg"]) == {"path", "sha256"}


def test_old_behavior_still_refuses_duplicate_session_without_opt_in(identity):
    with pytest.raises(cap.CapacityError, match="Duplicate active native session"):
        cap.classify_processes(pair(identity), NOW)
    with pytest.raises(cap.CapacityError, match="Duplicate active native session"):
        cap.classify_processes(pair(identity), NOW, venv_identity=None)


@pytest.mark.parametrize("reverse_input", [False, True])
def test_exact_parent_redirector_and_base_child_form_one_ordered_group(identity, reverse_input):
    processes = pair(identity)
    original = copy.deepcopy(processes)
    result = classify(processes[::-1] if reverse_input else processes, identity)
    assert result["native_workers_count"] == 1 and result["private_windows_venv_pairs_count"] == 1
    assert [item["ProcessId"] for item in result["private_native_groups"][0]] == [11, 10]
    assert result["session_ids"] == ["b" * 32]
    assert result["all_native_workers_known"] is True and processes == original
    assert [item["ExecutablePath"] for item in result["private_native_groups"][0]] == [
        identity["base_python"]["path"], identity["launcher"]["path"]]


@pytest.mark.parametrize("mutation", ["siblings", "independent", "triple-sibling", "chain", "old-launcher",
    "equal-date", "reversed-date", "pid-reuse", "wrong-parent", "argv", "head", "path", "channel", "session"])
def test_ambiguous_or_contradictory_python_relationship_never_reduces_count(identity, mutation):
    processes = pair(identity)
    parent, child = processes
    if mutation == "siblings":
        child["ParentProcessId"] = parent["ParentProcessId"]
    elif mutation == "independent":
        child["ParentProcessId"] = 88888
    elif mutation == "triple-sibling":
        processes.append({**child, "ProcessId": 12, "CreationDate": instant(-58)})
    elif mutation == "chain":
        processes.append({**child, "ProcessId": 12, "ParentProcessId": child["ProcessId"], "CreationDate": instant(-58)})
    elif mutation == "old-launcher":
        launcher = legacy.process(9, session="b" * 32, role="launcher")
        parent["ParentProcessId"] = 9
        processes.append(launcher)
    elif mutation == "equal-date":
        child["CreationDate"] = parent["CreationDate"]
    elif mutation == "reversed-date":
        child["CreationDate"] = instant(-61)
    elif mutation == "pid-reuse":
        child["ProcessId"] = parent["ProcessId"]
    elif mutation == "wrong-parent":
        parent["ParentProcessId"] = child["ProcessId"]
    elif mutation == "argv":
        child["CommandLine"] += " --different-argument yes"
    elif mutation == "head":
        command = child["CommandLine"].replace(identity["launcher"]["path"], identity["base_python"]["path"])
        parent["CommandLine"] = child["CommandLine"] = command
    elif mutation == "path":
        child["ExecutablePath"] = r"C:\unrelated\python.exe"
    elif mutation == "channel":
        child["CommandLine"] = child["CommandLine"].replace("/NEUTRAL/mailbox", "/other/mailbox")
    else:
        child["CommandLine"] = child["CommandLine"].replace("b" * 32, "c" * 32)
    assert_refused_or_not_fused(processes, identity)


def test_two_independent_sessions_remain_two_workers(identity):
    first = pair(identity)[0]
    second = pair(identity, pid=20, session="c" * 32)[1]
    second["ParentProcessId"] = 88888
    result = classify([first, second], identity)
    assert result["native_workers_count"] == 2 and result["private_windows_venv_pairs_count"] == 0


@pytest.mark.parametrize("mutation", ["schema", "missing", "extra", "launcher-path", "base-path", "cfg-path",
    "home", "executable", "version", "hash", "relative-root"])
def test_opt_in_provenance_must_be_exact(identity, mutation):
    value = copy.deepcopy(identity)
    if mutation == "schema":
        value["schema"] = "unproven-venv"
    elif mutation == "missing":
        value.pop("pyvenv_cfg")
    elif mutation == "extra":
        value["trust_me"] = True
    elif mutation.endswith("-path"):
        value[{"launcher-path": "launcher", "base-path": "base_python", "cfg-path": "pyvenv_cfg"}[mutation]]["path"] = r"C:\unrelated\python.exe"
    elif mutation == "hash":
        value["launcher"]["sha256"] = "not-a-sha"
    elif mutation == "relative-root":
        value["venv_root"] = "relative"
    else:
        value[mutation] = "unrelated"
    with pytest.raises(cap.CapacityError):
        classify(pair(identity), value)


def test_loader_accepts_only_actual_pinned_mz_files_and_exact_cfg(local_runtime):
    before = {key: path.read_bytes() for key, path in local_runtime["files"].items()}
    assert cap.load_venv_identity() == local_runtime["value"]
    assert {key: path.read_bytes() for key, path in local_runtime["files"].items()} == before


@pytest.mark.parametrize("key", ["launcher", "base_python", "pyvenv_cfg", "sidecar"])
def test_loader_rehashes_every_runtime_artifact(local_runtime, key):
    path = local_runtime["sidecar"] if key == "sidecar" else local_runtime["files"][key]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(cap.CapacityError, match="digest changed"):
        cap.load_venv_identity()


@pytest.mark.parametrize("key", ["launcher", "base_python"])
def test_repinning_a_non_mz_file_does_not_create_an_interpreter(local_runtime, key):
    path = local_runtime["files"][key]
    path.write_bytes(b"not an executable")
    local_runtime["value"][key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    local_runtime["repin"]()
    with pytest.raises(cap.CapacityError, match="not an executable"):
        cap.load_venv_identity()


@pytest.mark.parametrize("mutation", ["home", "executable", "version", "include-system", "command", "missing", "extra", "duplicate", "malformed"])
def test_cfg_semantics_remain_required_even_with_new_file_pins(local_runtime, mutation):
    config = copy.deepcopy(local_runtime["config"])
    if mutation == "missing":
        config.pop("home")
    elif mutation == "extra":
        config["extra"] = "value"
    elif mutation in {"duplicate", "malformed"}:
        pass
    else:
        config["include-system-site-packages" if mutation == "include-system" else mutation] = "wrong"
    raw = "\n".join(f"{key} = {value}" for key, value in config.items()) + "\n"
    if mutation == "duplicate":
        raw += "home = other\n"
    elif mutation == "malformed":
        raw += "malformed line\n"
    path = local_runtime["files"]["pyvenv_cfg"]
    path.write_text(raw, encoding="utf8")
    local_runtime["value"]["pyvenv_cfg"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    local_runtime["repin"]()
    with pytest.raises(cap.CapacityError):
        cap.load_venv_identity()


@pytest.mark.skipif(os.name != "nt", reason="Windows physical-runtime path regression")
def test_loader_refuses_a_real_junction_even_when_its_content_hash_is_pinned(local_runtime):
    # Directory junctions need no symlink privilege and require no helper process.
    home = local_runtime["files"]["base_python"].parent
    target = home.with_name("NEUTRAL-actual-base")
    home.rename(target)
    home.mkdir()
    substitute = ("\\??\\" + str(target.resolve())).encode("utf-16-le")
    printed = str(target.resolve()).encode("utf-16-le")
    paths = substitute + b"\x00\x00" + printed + b"\x00\x00"
    data = struct.pack("<IHHHHHH", 0xA0000003, 8 + len(paths), 0,
                       0, len(substitute), len(substitute) + 2, len(printed)) + paths
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(home), 0x40000000, 7, None, 3, 0x02200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(data)
        returned = wintypes.DWORD()
        if not kernel.DeviceIoControl(handle, 0x000900A4, buffer, len(data), None, 0,
                                      ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)
    assert home.is_junction()
    with pytest.raises(cap.CapacityError, match="Symlink|junction|Reparse"):
        cap.load_venv_identity()


def test_three_venv_pairs_leave_one_fixture_slot_and_all_verdicts_false(identity, capacity_fixture):
    processes = [item for index in range(3) for item in pair(identity, pid=10 + index * 10, session=str(index + 1) * 32)]
    with patch.object(cap, "load_venv_identity", return_value=identity), capacity_fixture.context(raw=legacy.census(processes)) as result:
        assert result["verified"] is False
        assert cap.read_json(result["lane"]["path"])["active_native_workers_before_start"] == 3
        for key in ("lane", "projection", "reservation", "registry_reservation"):
            receipt = cap.read_json(result[key]["path"])
            assert receipt["verified"] is False and receipt["maximum_native_workers_total"] == 4


def test_four_venv_pairs_are_still_cap4_and_cannot_reserve(identity, capacity_fixture):
    processes = [item for index in range(4) for item in pair(identity, pid=10 + index * 10, session=str(index + 1) * 32)]
    with patch.object(cap, "load_venv_identity", return_value=identity), pytest.raises(cap.CapacityError, match="cap4"):
        with capacity_fixture.context(raw=legacy.census(processes)):
            pytest.fail("Four venv pairs opened a fifth native slot")
    assert not list(capacity_fixture.registry.glob("*.reservation.json"))


def test_pending_reservation_adds_to_three_venv_groups(identity, capacity_fixture):
    with capacity_fixture.context() as result:
        reservation = cap.read_json(result["reservation"]["path"])
    other_output = capacity_fixture.root / "NEUTRAL-other-output"
    other_output.mkdir()
    capacity_fixture.output = other_output
    processes = [item for index in range(3) for item in pair(identity, pid=10 + index * 10, session=str(index + 1) * 32)]
    binding = {**legacy.BINDING, "session_id": "c" * 32}
    with patch.object(cap, "load_venv_identity", return_value=identity), pytest.raises(cap.CapacityError, match="cap4"):
        with capacity_fixture.context(raw=legacy.census(processes), binding=binding):
            pytest.fail("Pending reservation disappeared behind a venv pair")
    assert reservation["verified"] is False
    assert len(list(capacity_fixture.registry.glob("*.reservation.json"))) == 1


def test_saved_root_three_line_sample_replays_one_pair_without_claiming_full_census():
    raw = ROOT_SAMPLE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ROOT_SAMPLE_SHA
    sample = json.loads(raw)
    identity_value = cap.read_json(HERE / "VENV-RUNTIME-IDENTITY.json")
    assert len(sample["processes"]) == 3
    result = cap.classify_processes(sample["processes"], sample["observed_at"], venv_identity=identity_value)
    assert result["native_workers_count"] == result["private_windows_venv_pairs_count"] == 1
    assert [row["ProcessId"] for row in result["private_native_groups"][0]] == [36144, 57576]
    assert len(result["private_native_groups"][0]) == 2
    assert "verified" not in result and "capacity_admitted" not in result
