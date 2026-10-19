"""Pure temporary parser observations; never an operational admission or census."""
from __future__ import annotations

import copy
from pathlib import Path

import dynamic_admission as admission
import pytest


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No process or capacity collection in parser tests")
    monkeypatch.setattr(admission.subprocess, "run", forbidden)


def write(tmp_path, name, value):
    return admission.create(tmp_path / name, value)


@pytest.fixture
def observed(tmp_path):
    cell = copy.deepcopy(admission.contract.REGISTERED_CELLS[admission.FIRST_CELL])
    binding = {**cell, "scope_id": admission.contract.SCOPE, "job_id": "900001",
        "remote_root": "/scratch/" + admission.contract.SCOPE + "-" + cell["session_id"],
        "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
        "preparation_manifest_sha256": "3" * 64, "r1_contract_sha256": "4" * 64}
    refs = {key: write(tmp_path, key + ".bin", (key + " parser-only bytes").encode()) for key in admission.STATIC_KEYS}
    qref = write(tmp_path, "qualification.json", {"verified": False})
    root = binding["remote_root"]
    marker = {"schema": admission.MARKER_SCHEMA, "binding": binding,
        "admission_root": root + "-admission", "observed_at": 1100.0, "admission_started_at": 1000.0,
        "allocation_outer_deadline": 4600.0, "native_model_calls": 0,
        "scientific_paths": {"root": root, "mailbox": root + "/results-900001/mailbox",
                             "registry": root + "/results-900001/2020-quicksort/registry.sqlite3"},
        "source_runtime_verified": True, "scientific_root_observed_absent": True,
        "scientific_mailbox_observed_absent": True, "scientific_registry_observed_absent": True,
        "allocation": {"job_id": "900001", "architecture": "aarch64", "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0, "affinity_cpu_count": 4}}
    marker_ref = write(tmp_path, "marker.json", marker)
    def raw(name, tool, args, payload, *, is_error=False):
        return write(tmp_path, name, {"schema": admission.OBS_SCHEMA,
            "tool": tool, "arguments": args, "observed_at": 1100.0,
            "response": {"isError": is_error, "structuredContent": payload}})
    marker_path = root + "-admission/ZERO-MODEL-MARKER.json"
    readback_ref = raw("readback.json", "mcp__romeo__read_remote_file", {"path": marker_path, "offset": 1},
        {"ok": True, "path": marker_path, "offset": 1, "limit": 2000, "total_lines": 1,
         "truncated": False, "content": Path(marker_ref["path"]).read_text(encoding="utf8")})
    job_ref = raw("job.json", "mcp__romeo__job_status", {"job_id": "900001"},
                  {"ok": True, "job_id": "900001", "state": "RUNNING", "finished": False})
    transfers = {}
    for key, ref in {**refs, "subject_qualification": qref}.items():
        remote = "/scratch/shared/" + key
        size = Path(ref["path"]).stat().st_size
        raw_ref = raw(key + "-upload.json", "mcp__romeo__upload_to_romeo",
            {"local_path": ref["path"], "remote_path": remote, "verify": True},
            {"ok": True, "sent": ref["path"], "to": remote, "transport": "scp", "verifie": True,
             "bytes": size, "empreinte_locale": ref["sha256"], "empreinte_distante": ref["sha256"]})
        transfers[key] = {"local": ref, "remote_path": remote, "sha256": ref["sha256"], "bytes": size, "raw": raw_ref}
    outer = {"schema": admission.ARM_SCHEMA, "binding": binding, "observed_at": 1100.0,
             "marker": marker_ref, "marker_readback": readback_ref, "job_id_observation": job_ref, "transfers": transfers}
    return tmp_path, binding, refs, qref, outer, raw


def check(observed, outer=None):
    tmp_path, binding, refs, qref, original, _ = observed
    ref = write(tmp_path, "outer-" + str(len(list(tmp_path.iterdir()))) + ".json", outer or original)
    return admission.check_arm(ref, binding, refs, qref, now=1100.0)


def test_whole_upload_observations_parse_without_creating_authorization(observed):
    value, marker, evidence = check(observed)
    assert "verified" not in value and "verified" not in marker
    assert evidence and not list(observed[0].glob("authorization*"))


def test_whole_download_observation_rehashes_actual_readback_bytes(observed):
    tmp_path, _, _, _, original, raw = observed
    outer = copy.deepcopy(original)
    transfer = outer["transfers"]["source_zip"]
    readback = write(tmp_path, "downloaded-source.zip", Path(transfer["local"]["path"]).read_bytes())
    transfer["readback"] = readback
    transfer["raw"] = raw("download.json", "mcp__romeo__download_from_romeo",
        {"local_path": readback["path"], "remote_path": transfer["remote_path"], "verify": True, "recursive": False},
        {"ok": True, "downloaded": transfer["remote_path"], "to": readback["path"], "transport": "scp",
         "verifie": True, "bytes": transfer["bytes"], "empreinte_locale": transfer["sha256"],
         "empreinte_distante": transfer["sha256"], "remote_sha256": transfer["sha256"]})
    assert "verified" not in check(observed, outer)[0]
    Path(readback["path"]).write_bytes(b"changed readback")
    with pytest.raises(admission.InfrastructureError, match="bytes changed"):
        check(observed, outer)


@pytest.mark.parametrize("mutation", ["isError", "ok", "arguments", "path", "sha", "bytes", "unverified", "transport", "other-receipt"])
def test_inconsistent_or_failed_upload_never_proves_transport(observed, mutation):
    tmp_path, _, _, _, original, _ = observed
    outer = copy.deepcopy(original)
    transfer = outer["transfers"]["source_zip"]
    value = admission.read(admission.verified_ref(transfer["raw"]))
    payload = value["response"]["structuredContent"]
    if mutation == "isError":
        value["response"]["isError"] = True
    elif mutation == "ok":
        payload["ok"] = False
    elif mutation == "arguments":
        value["arguments"]["remote_path"] = "/scratch/another"
    elif mutation == "path":
        payload["to"] = "/scratch/another"
    elif mutation == "sha":
        payload["empreinte_distante"] = "f" * 64
    elif mutation == "bytes":
        payload["bytes"] += 1
    elif mutation == "unverified":
        payload["verifie"] = False
    elif mutation == "transport":
        payload["transport"] = "rsync"
    else:
        value = admission.read(admission.verified_ref(outer["transfers"]["harness"]["raw"]))
    transfer["raw"] = write(tmp_path, "bad-upload.json", value)
    with pytest.raises(admission.InfrastructureError):
        check(observed, outer)


@pytest.mark.parametrize("field,value", [("truncated", True), ("offset", 2), ("path", "/scratch/another"),
                                         ("content", "partial"), ("limit", 0)])
def test_partial_or_foreign_marker_readback_is_rejected(observed, field, value):
    tmp_path, _, _, _, original, _ = observed
    outer = copy.deepcopy(original)
    raw = admission.read(admission.verified_ref(outer["marker_readback"]))
    raw["response"]["structuredContent"][field] = value
    outer["marker_readback"] = write(tmp_path, "bad-readback.json", raw)
    with pytest.raises(admission.InfrastructureError):
        check(observed, outer)


def test_initial_600_seconds_and_immutable_3300_second_authorization_are_distinct():
    marker = {"observed_at": 1100.0, "admission_started_at": 1000.0, "allocation_outer_deadline": 4600.0}
    admission.admission_clock(marker, 1599.9)
    with pytest.raises(admission.InfrastructureError):
        admission.admission_clock(marker, 1600.0)
    admission.authorization_clock(marker, 4300.0, 1100.0)
    admission.authorization_clock(marker, 4300.0, 4200.0)
    with pytest.raises(admission.InfrastructureError):
        admission.authorization_clock(marker, 4300.01, 1100.0)
    with pytest.raises(admission.InfrastructureError):
        admission.authorization_clock({**marker, "allocation_outer_deadline": 3000.0}, 3001.0, 1100.0)


def test_cli_cannot_execute_an_unpinned_neighbor_binary(tmp_path, monkeypatch):
    files = {name: write(tmp_path, name, name.encode()) for name in admission.native.CLI_FILES}
    other = write(tmp_path, "other.exe", b"inert parser-only neighbor")
    monkeypatch.setattr(admission.native, "CLI_FILES", {name: ref["sha256"] for name, ref in files.items()})
    with pytest.raises(admission.InfrastructureError, match="exact pinned codex.exe"):
        admission.probe_cli(Path(other["path"]), [], tmp_path / "probe-output")
    assert not list((tmp_path / "probe-output").glob("*.stdout"))


@pytest.mark.parametrize("target", ["outer", "marker", "raw"])
def test_explicit_negative_observations_cannot_be_promoted(observed, target):
    tmp_path, _, _, _, original, _ = observed
    outer = copy.deepcopy(original)
    if target == "outer":
        outer["verified"] = False
    else:
        name = "marker" if target == "marker" else "job_id_observation"
        value = admission.read(admission.verified_ref(outer[name]))
        value["verified"] = False
        outer[name] = write(tmp_path, "explicit-negative.json", value)
    with pytest.raises(admission.InfrastructureError, match="negative receipt"):
        check(observed, outer)
