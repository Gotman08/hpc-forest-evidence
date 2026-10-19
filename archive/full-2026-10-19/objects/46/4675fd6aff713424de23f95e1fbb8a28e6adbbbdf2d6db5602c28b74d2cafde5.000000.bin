"""NEUTRAL mock MCP contexts only. No network, model, config body, or server process."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("parallel_receive_under_test", Path(__file__).with_name("receive.py"))
receiver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receiver)


@pytest.fixture
def case(tmp_path):
    reader = receiver.runtime()
    data = {"/gpfs/scratch/received-" + str(i): ("NEUTRAL bytes " + str(i)).encode() for i in range(14)}
    plan = {"schema": receiver.SCHEMA, "refs": [{"path": path, "sha256": reader.sha(raw)} for path, raw in data.items()],
            "lanes": 6, "config_path": "C:/Users/nicol/.codex/config.toml", "output_root": str(tmp_path / "received")}
    state = {"live": 0, "maximum": 0, "contexts": 0, "calls": [], "dumps": [], "missing": None, "catalog_missing": False,
             "raise_rpc": False, "cancel_rpc": False}
    class Result:
        def __init__(self, value):
            self.value = value
        def model_dump(self, **kwargs):
            state["dumps"].append(kwargs)
            assert kwargs == {"mode": "json", "by_alias": True, "exclude_none": False}
            return self.value
    class Tools(Result):
        def __init__(self):
            names = [] if state["catalog_missing"] else ["download_from_romeo"]
            self.tools = [SimpleNamespace(name=name) for name in names]
            super().__init__({"tools": [{"name": name} for name in names], "nextCursor": None})
    class Client:
        async def list_tools(self):
            return Tools()
        async def call_tool(self, name, arguments):
            assert name == "download_from_romeo" and arguments["verify"] is True
            state["calls"].append((name, arguments))
            await asyncio.sleep(0.001)
            if state["raise_rpc"]:
                raise RuntimeError("NEUTRAL RPC exception with no CallToolResult")
            if state["cancel_rpc"]:
                raise asyncio.CancelledError()
            raw = data[arguments["remote_path"]]
            Path(arguments["local_path"]).write_bytes(raw)
            payload = {"ok": True, "downloaded": arguments["remote_path"], "to": arguments["local_path"], "bytes": len(raw),
                "transport": "scp", "verifie": True, "remote_sha256": reader.sha(raw),
                "empreinte_locale": reader.sha(raw), "empreinte_distante": reader.sha(raw)}
            if state["missing"]:
                payload.pop(state["missing"])
            return Result({"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload,
                           "isError": False, "_meta": None})
    class Relay:
        def __init__(self, config):
            assert str(config).replace("\\", "/") == plan["config_path"]
            self.session = Client()
        async def __aenter__(self):
            state["live"] += 1
            state["contexts"] += 1
            state["maximum"] = max(state["maximum"], state["live"])
            return self
        async def __aexit__(self, *args):
            state["live"] -= 1
    return reader, plan, state, Relay


def run(case):
    reader, plan, _state, Relay = case
    ref = asyncio.run(receiver.receive(plan, reader, relay_class=Relay))
    return reader.parse(Path(ref["path"]).read_bytes())


def test_six_independent_contexts_and_full_model_dump_are_preserved(case):
    reader, plan, state, _Relay = case
    report = run(case)
    assert state["contexts"] == state["maximum"] == 6
    assert len(state["calls"]) == 14
    assert len({arguments["remote_path"] for _, arguments in state["calls"]}) == 14
    assert report["received"] == 14 and report["neutral"] is True and report["verified"] is False
    raw = reader.parse((Path(plan["output_root"]) / "raw/00001.json").read_bytes())
    assert raw["response"]["_meta"] is None
    assert raw["tool"] == "mcp__romeo__download_from_romeo"
    assert raw["neutral"] is True
    catalog = reader.parse(Path(report["catalog"]["path"]).read_bytes())
    with pytest.raises(ValueError, match="neutral"):
        reader.Evidence(catalog, [])  # Mock results cannot become production evidence.


@pytest.mark.parametrize("field", ["remote_sha256", "empreinte_locale", "empreinte_distante", "bytes", "transport", "verifie"])
def test_missing_required_metadata_retains_raw_result_and_refuses(case, field):
    reader, plan, state, _Relay = case
    state["missing"] = field
    report = run(case)
    assert report["received"] == 0 and report["failures"]
    assert len(list((Path(plan["output_root"]) / "raw").glob("0*.json"))) == 14
    assert reader.parse((Path(plan["output_root"]) / "raw/00001.json").read_bytes())["response"]["isError"] is False
    assert len(state["calls"]) == 14


def test_rpc_exception_is_dated_without_fabricated_tool_result_or_retry(case):
    reader, plan, state, _Relay = case
    state["raise_rpc"] = True
    report = run(case)
    assert report["received"] == 0 and len(state["calls"]) == 14
    assert not list((Path(plan["output_root"]) / "raw").glob("0*.json"))
    refusal = reader.parse((Path(plan["output_root"]) / "failures/00001.json").read_bytes())
    assert refusal["rpc_completion_unknown"] is True and refusal["observed_at"] > 0
    assert refusal["no_tool_result_fabricated"] is True and "response" not in refusal


def test_missing_catalog_download_tool_makes_no_download_call(case):
    _reader, _plan, state, _Relay = case
    state["catalog_missing"] = True
    report = run(case)
    assert not state["calls"] and report["received"] == 0
    assert len(report["failures"]) == 6


@pytest.mark.parametrize("change", ["duplicate", "conflict", "parent", "outside", "too_many_contexts"])
def test_invalid_input_has_no_context_or_overwrite(case, change, tmp_path):
    _reader, plan, state, _Relay = case
    if change == "duplicate":
        plan["refs"].append(dict(plan["refs"][0]))
    elif change == "conflict":
        plan["refs"].append({"path": plan["refs"][0]["path"], "sha256": "f" * 64})
    elif change == "parent":
        plan["output_root"] = str(tmp_path / ".." / "escaped")
    elif change == "outside":
        plan["output_root"] = "C:/outside-workspace-reception"
    else:
        plan["lanes"] = 7
    with pytest.raises(ValueError):
        run(case)
    assert state["contexts"] == 0 and not state["calls"]


def test_existing_output_cannot_be_reused(case):
    _reader, _plan, state, _Relay = case
    run(case)
    with pytest.raises(ValueError, match="Fresh"):
        run(case)
    assert state["contexts"] == 6


def test_rpc_cancellation_retains_partial_catalog_without_retry(case):
    reader, plan, state, _Relay = case
    state["cancel_rpc"] = True
    with pytest.raises(asyncio.CancelledError):
        run(case)
    assert (Path(plan["output_root"]) / "CATALOG.json").is_file()
    refusal = reader.parse((Path(plan["output_root"]) / "failures/00001.json").read_bytes())
    assert refusal["rpc_completion_unknown"] is True and refusal["cancelled"] is True


def test_cli_requires_explicit_receive_switch_to_connect():
    with pytest.raises(SystemExit):
        receiver.main(["--input", "x", "--input-sha256", "a" * 64, "--retry"])
