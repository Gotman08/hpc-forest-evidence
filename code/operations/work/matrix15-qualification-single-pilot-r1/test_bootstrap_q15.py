"""Pure bootstrap guard/archive tests; no process, compiler, model or network."""
from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

import bootstrap_q15 as boot


def archive(tmp_path, rows):
    path = tmp_path / "NEUTRAL.tar.gz"
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as target:
        for item, raw in rows:
            target.addfile(item, io.BytesIO(raw) if raw else None)
    return path


def entry(name, raw=b"NEUTRAL"):
    item = tarfile.TarInfo(name)
    item.size = len(raw)
    return item, raw


def test_actual_sealed_source_package_as_data_only():
    current = Path(__file__).resolve().parents[2]
    path = current / "outputs/HPC-Forest-Q15-Pilote-Unique-r1" / boot.ARCHIVE_NAME
    before = set(sys.modules)
    assert boot.sha(path.read_bytes()) == boot.ARCHIVE_SHA256
    material = boot.read_tar(path)
    plan = boot.verify_package(material)
    assert len(material) == 353 and len(plan["subject_order"]) == 15
    assert not any(name == "hpc_forest" or name.startswith("hpc_forest.") for name in set(sys.modules) - before)


@pytest.mark.parametrize("name", [".", "../escape", "/absolute", "C:/windows", "a//b", "a/./b",
                                   "a\\b", "a/", ".git/config", "a/\nlog", "__pycache__/x.pyc"])
def test_unsafe_member_names_refused(name):
    with pytest.raises(ValueError):
        boot.canonical_member(name)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE])
def test_links_and_nonregular_members_refused(tmp_path, kind):
    item = tarfile.TarInfo("NEUTRAL")
    item.type = kind
    item.linkname = "NEUTRAL-target" if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE} else ""
    with pytest.raises(ValueError):
        boot.read_tar(archive(tmp_path, [(item, b"")]), expected_count=1)


def test_duplicate_case_collision_wrong_count_or_pax_refused(tmp_path):
    for rows in ([entry("a"), entry("a")], [entry("a"), entry("A")], [entry("a")]):
        with pytest.raises(ValueError):
            boot.read_tar(archive(tmp_path, rows), expected_count=2)
    item, raw = entry("a")
    item.pax_headers = {"comment": "NEUTRAL no extended metadata accepted"}
    with pytest.raises(ValueError):
        boot.read_tar(archive(tmp_path, [(item, raw)]), expected_count=1)


def test_file_and_total_bounds_checked_before_reading_payload(tmp_path, monkeypatch):
    path = archive(tmp_path, [entry("a", b"NEUTRAL")])
    monkeypatch.setattr(boot, "MAX_FILE_BYTES", 3)
    with pytest.raises(ValueError, match="oversized"):
        boot.read_tar(path, expected_count=1)
    monkeypatch.setattr(boot, "MAX_FILE_BYTES", 100)
    monkeypatch.setattr(boot, "MAX_TOTAL_BYTES", 3)
    with pytest.raises(ValueError, match="total"):
        boot.read_tar(path, expected_count=1)


def test_changed_package_pin_refused_before_any_runtime_import():
    with pytest.raises(ValueError, match="pins differ"):
        boot.verify_package({"PLAN-Q15.json": b"NEUTRAL not a plan"})


def guard(**changes):
    env = {"SLURM_JOB_ID": "999", "SLURM_JOB_NUM_NODES": "1", "SLURM_NTASKS": "1",
           "SLURM_CPUS_PER_TASK": "4", "SLURM_MEM_PER_NODE": "16384"}
    env.update(changes.pop("env", {}))
    return boot.allocation_guard(env=env, system=changes.pop("system", "Linux"),
        machine=changes.pop("machine", "aarch64"), affinity=changes.pop("affinity", [0, 1, 2, 3]),
        now=changes.pop("now", boot.DEADLINE - 20000), **changes)


def test_exact_allocation_guard_and_fixed_child_argv():
    assert guard()["gpus"] == 0
    argv = boot.child_argv(Path("/NEUTRAL/package"), Path("/NEUTRAL/result-Q15"))
    assert argv[0] == boot.PYTHON and argv[1] == "-B" and "-I" not in argv
    assert argv[-2:] == ["--maximum-seconds", "1800"]
    assert argv[argv.index("--plan-sha256") + 1] == boot.PLAN_SHA256


@pytest.mark.parametrize("changes", [{"machine": "x86_64"}, {"system": "Windows"},
    {"env": {"SLURM_RESTART_COUNT": "1"}}, {"env": {"SLURM_GPUS": "1"}},
    {"env": {"SLURM_MEM_PER_NODE": "8192"}}, {"env": {"SLURM_CPUS_PER_TASK": "8"}},
    {"affinity": [0, 1, 2]}, {"now": boot.DEADLINE - 2100 - 10800}, {"now": float("nan")}])
def test_wrong_allocation_or_exclusive_deadline_refused(changes):
    with pytest.raises(ValueError):
        guard(**changes)
