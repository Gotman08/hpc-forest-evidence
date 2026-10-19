"""Chain the real wrapper/base argparse without a CLI, process or transport."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import codex_process, codex_worker, native_r2max, r2max_worker
from hpc_forest.core import file_digest


@pytest.fixture
def two_parsers(tmp_path, monkeypatch):
    executable = tmp_path / "NEUTRAL-not-executable.bin"
    executable.write_bytes(b"NEUTRAL parser identity only; never execute")
    cli_file = tmp_path / "NEUTRAL-cli-identity.json"
    cli_file.write_text(json.dumps({"executable_path": str(executable),
                                   "executable_sha256": file_digest(executable),
                                   "task_cli_policy_sha256": "b" * 64}), encoding="utf8")
    calls = {"bindings": [], "parsed": []}

    def forbidden(*args, **kwargs):
        raise AssertionError("The parser test must never run a CLI, transport or generation")

    # Restore the production adapter's module assignments after each inert case.
    for name in ("Worker", "run_codex", "validate_remote_channel"):
        monkeypatch.setattr(codex_worker, name, getattr(codex_worker, name))
    monkeypatch.setattr(codex_process, "CLI_POLICY", None)
    monkeypatch.setattr(codex_process, "load_task_cli_policy", lambda *args: {"skill_candidate_directories": []})
    monkeypatch.setattr(codex_worker.RomeoFiles, "__init__", forbidden)
    monkeypatch.setattr(codex_worker.subprocess, "run", forbidden)
    monkeypatch.setattr(r2max_worker, "artifact", lambda ref: Path(ref["path"]))
    monkeypatch.setattr(r2max_worker, "bind_worker_cache", lambda root, auth: calls["bindings"].append(root))
    def inert_async(args):
        calls["inherited_argv"] = list(sys.argv)
        return SimpleNamespace(parsed=args)

    monkeypatch.setattr(codex_worker, "main_async", inert_async)

    def inert_run(token):
        assert isinstance(token, SimpleNamespace)
        calls["parsed"].append(token.parsed)
        if "failure" in calls:
            raise calls["failure"]
        return 37

    monkeypatch.setattr(codex_worker.asyncio, "run", inert_run)

    def prepare(model="gpt-6-astra", *, equals=False):
        session = native_r2max.CELLS[model]
        root = "/scratch/NEUTRAL-fresh"
        auth = {"model": model, "effort": "max", "session_id": session, "job_id": "NEUTRAL",
                "remote_root": root, "artifacts": {"cli_identity": {"path": str(cli_file)},
                "source_zip": {"sha256": "1" * 64}, "plan": {"sha256": "2" * 64}}}
        monkeypatch.setattr(r2max_worker, "install_identity", lambda *args, **kwargs: auth)
        public = ["--session-id", session, "--required-jobs", native_r2max.SCOPE,
                  "--channel", root + "/results-NEUTRAL/mailbox", "--output", str(tmp_path / "NEUTRAL-output"),
                  "--dependency-receipt", str(tmp_path / "NEUTRAL-dependency.json"),
                  "--executable", str(executable), "--codex-config", str(tmp_path / "NEUTRAL-codex.toml"),
                  "--once", "--max-seconds", "1800", "--poll-seconds", "0.75"]
        policy = str(tmp_path / "NEUTRAL-policy.json")
        private = (["--cli-policy=" + policy, "--cli-policy-sha256=" + "b" * 64] if equals else
                   ["--cli-policy", policy, "--cli-policy-sha256", "b" * 64])
        original = ["NEUTRAL-r2max-worker", *public[:4], *private, *public[4:]]
        monkeypatch.setattr(sys, "argv", original)
        return original, public, auth

    return calls, prepare


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-5.6-terra", "gpt-6.1-sol"])
@pytest.mark.parametrize("equals", [False, True])
def test_real_wrapper_and_inherited_parser_preserve_all_shared_options(two_parsers, model, equals):
    calls, prepare = two_parsers
    original, public, auth = prepare(model, equals=equals)
    assert r2max_worker.main() == 37
    assert sys.argv is original
    assert len(calls["parsed"]) == 1 and len(calls["bindings"]) == 1
    assert calls["inherited_argv"] == [original[0], *public]
    parsed = calls["parsed"][0]
    assert parsed.session_id == auth["session_id"]
    assert parsed.required_jobs == [native_r2max.SCOPE]
    assert parsed.channel == auth["remote_root"] + "/results-NEUTRAL/mailbox"
    assert parsed.output == Path(public[public.index("--output") + 1]).resolve()
    assert parsed.dependency_receipt == Path(public[public.index("--dependency-receipt") + 1])
    assert parsed.executable == public[public.index("--executable") + 1]
    assert parsed.codex_config == Path(public[public.index("--codex-config") + 1])
    assert parsed.once is True and parsed.transport_smoke is False
    assert parsed.max_seconds == 1800 and parsed.poll_seconds == 0.75
    assert not hasattr(parsed, "cli_policy") and not hasattr(parsed, "cli_policy_sha256")


@pytest.mark.parametrize("failure", [RuntimeError("NEUTRAL inherited failure"), SystemExit(19)])
def test_original_argv_object_restored_when_inherited_main_raises(two_parsers, failure):
    calls, prepare = two_parsers
    original, _, _ = prepare()
    calls["failure"] = failure
    with pytest.raises(type(failure)) as caught:
        r2max_worker.main()
    assert caught.value is failure and sys.argv is original
    assert len(calls["parsed"]) == 1


@pytest.mark.parametrize("unknown", ["--unknown-option", "--codex-confg"])
def test_inherited_parser_still_refuses_unknown_or_misspelled_options(two_parsers, unknown):
    calls, prepare = two_parsers
    original, _, _ = prepare()
    original.append(unknown)
    with pytest.raises(SystemExit) as caught:
        r2max_worker.main()
    assert caught.value.code == 2 and sys.argv is original
    assert calls["parsed"] == []


@pytest.mark.parametrize("missing", ["--cli-policy", "--cli-policy-sha256"])
def test_wrapper_still_requires_each_private_option_before_binding(two_parsers, missing):
    calls, prepare = two_parsers
    original, _, _ = prepare()
    index = original.index(missing)
    del original[index:index + 2]
    with pytest.raises(SystemExit) as caught:
        r2max_worker.main()
    assert caught.value.code == 2 and sys.argv is original
    assert calls["bindings"] == [] and calls["parsed"] == []
