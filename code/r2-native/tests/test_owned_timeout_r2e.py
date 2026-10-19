"""Owned watchdog tests; every process, timer and signal target is inert."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "r2e_owned_timeout_core", Path(__file__).parents[1] / "src/hpc_forest/core.py"
)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


class OwnedProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.kill_calls = 0
        self.communications = []

    @property
    def pid(self):
        raise AssertionError("Windows termination must not reopen or target a PID")

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9

    def communicate(self, *args, **kwargs):
        self.communications.append((args, kwargs))


def windows(monkeypatch):
    monkeypatch.setattr(core, "os", SimpleNamespace(name="nt", environ={}, replace=os.replace))


def test_windows_uses_only_owned_popen_object(monkeypatch):
    windows(monkeypatch)
    monkeypatch.setattr(core.subprocess, "run", lambda *_a, **_k: pytest.fail("No taskkill"))
    owned = OwnedProcess()
    core._kill_owned(owned)
    assert owned.kill_calls == 1
    assert owned.returncode == -9


def test_finished_process_is_untouched(monkeypatch):
    windows(monkeypatch)
    owned = OwnedProcess(returncode=0)
    core._kill_owned(owned)
    assert owned.kill_calls == 0


def test_exception_cleanup_reaps_only_owned_process(monkeypatch):
    windows(monkeypatch)
    owned = OwnedProcess()
    core._terminate_owned(owned)
    assert owned.kill_calls == 1
    assert owned.communications == [((), {"timeout": 5})]


def test_posix_group_branch_is_unchanged_and_inert(monkeypatch):
    signals = []
    owned = OwnedProcess()
    monkeypatch.setattr(
        core,
        "os",
        SimpleNamespace(name="posix", killpg=lambda pid, sig: signals.append((pid, sig))),
    )
    monkeypatch.setattr(OwnedProcess, "pid", property(lambda self: 24680))
    monkeypatch.setattr(core, "signal", SimpleNamespace(SIGKILL=9))
    core._kill_owned(owned)
    assert signals == [(24680, 9)]
    assert owned.kill_calls == 1


def test_windows_watchdog_keeps_deadline_and_timeout_metadata(monkeypatch, tmp_path):
    windows(monkeypatch)
    owned = OwnedProcess()
    timers = []
    launches = []

    class InertTimer:
        def __init__(self, seconds, callback):
            self.seconds = seconds
            self.callback = callback
            self.cancelled = False
            self.joined = False
            timers.append(self)

        def start(self):
            self.callback()

        def cancel(self):
            self.cancelled = True

        def join(self):
            self.joined = True

    def inert_popen(argv, **kwargs):
        launches.append((argv, kwargs))
        return owned

    monkeypatch.setattr(core.threading, "Timer", InertTimer)
    monkeypatch.setattr(core.subprocess, "Popen", inert_popen)
    monkeypatch.setattr(core.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    log = tmp_path / "owned.log"
    result = core.run_process(["inert-only"], tmp_path, log, 2.75, stdin="fixture")
    assert len(launches) == 1
    assert launches[0][1]["start_new_session"] is False
    assert launches[0][1]["creationflags"] == core.subprocess.CREATE_NEW_PROCESS_GROUP
    assert owned.kill_calls == 1
    assert owned.communications == [((b"fixture",), {})]
    assert timers[0].seconds == 2.75
    assert timers[0].cancelled and timers[0].joined
    assert result.timed_out is True
    assert result.returncode == -9
    metadata = json.loads(log.with_suffix(".log.json").read_text(encoding="utf-8"))
    assert metadata["timed_out"] is True
    assert metadata["returncode"] == -9


def test_nonpositive_deadline_does_not_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(core.subprocess, "Popen", lambda *_a, **_k: pytest.fail("No process"))
    with pytest.raises(core.BudgetExhausted, match="deadline"):
        core.run_process(["inert-only"], tmp_path, tmp_path / "never.log", 0)
