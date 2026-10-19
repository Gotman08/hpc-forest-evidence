"""Pure CLI-event/hold regressions; never start a CLI, model, compiler or transport."""
import json
import time
import tomllib
from subprocess import list2cmdline
from types import SimpleNamespace

import pytest

from hpc_forest import codex_process, native_r2max, r2max_worker
from hpc_forest.codex_mailbox import EFFORT, MODEL, sha256
from hpc_forest.core import InfrastructureError, atomic_json, file_digest


def command_policy(candidates):
    return {"schema": codex_process.TASK_CLI_POLICY_SCHEMA,
            "cli_feature_overrides": dict(codex_process.TASK_CLI_FEATURES),
            "code_mode_host_executable_sha256": codex_process.CODE_MODE_HOST_SHA256,
            "skill_candidate_directories": candidates}


def test_candidate_argv_is_real_TOML_MAX_OAuth_no_tools_and_under_Windows_limit(tmp_path, monkeypatch):
    executable = "C:/NEUTRAL/pinned/codex.exe"
    monkeypatch.setattr(codex_process.shutil, "which", lambda _: executable)
    candidates = ["C:/NEUTRAL/skill-one", "C:/NEUTRAL/skill-two"]
    monkeypatch.setattr(codex_process, "CLI_POLICY", command_policy(candidates))
    request = {"model": MODEL, "reasoning_effort": EFFORT,
               "schema": {"type": "object", "properties": {"NEUTRAL": {"type": "boolean"}}},
               "messages": [{"role": "system", "content": "NEUTRAL frozen instructions"},
                            {"role": "user", "content": "NEUTRAL"}]}
    output = tmp_path / "NEUTRAL-argv"
    argv = codex_process.command_for(request, output, executable)
    overrides = [argv[index + 1] for index, token in enumerate(argv) if token == "--config"]
    values = tomllib.loads("\n".join(overrides))
    assert values["model_reasoning_effort"] == "max"
    assert values["forced_login_method"] == "chatgpt"
    assert values["model_context_window"] == 65536
    assert values["project_doc_max_bytes"] == 0 and values["web_search"] == "disabled"
    assert values["features"] == codex_process.TASK_CLI_FEATURES
    assert values["features"]["code_mode_host"] is True
    for field in ("skip_host_skill_discovery", "code_mode", "code_mode_only"):
        assert values["features"][field] is False
    assert values["skills"]["include_instructions"] is False
    assert values["skills"]["bundled"]["enabled"] is False
    assert values["skills"]["max_context_tokens"] == 1
    assert values["skills"]["config"] == [
        {"path": path, "enabled": False} for path in candidates]
    assert len(values["skills"]["config"]) == 2
    assert "--ignore-user-config" in argv and "--strict-config" in argv
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert argv[argv.index("--model") + 1] == MODEL
    assert len(list2cmdline(argv).encode("utf-16-le")) // 2 + 1 < 32767
    assert (output / "instructions.txt").read_text("utf8") == request["messages"][0]["content"]


def test_oversized_quoted_command_refused_before_any_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_process.shutil, "which", lambda _: "C:/NEUTRAL/codex.exe")
    monkeypatch.setattr(codex_process, "CLI_POLICY", command_policy(["C:/NEUTRAL/" + "x" * 33000]))
    request = {"model": MODEL, "reasoning_effort": EFFORT, "schema": {"type": "object"},
               "messages": [{"role": "system", "content": "NEUTRAL"},
                            {"role": "user", "content": "NEUTRAL"}]}
    with pytest.raises(InfrastructureError, match="argument limit"):
        codex_process.command_for(request, tmp_path / "NEUTRAL-oversized")


@pytest.mark.parametrize("value", [{"path": "C:/NEUTRAL", "enabled": True}, {"name": "*", "enabled": False}, None])
def test_TOML_serializer_rejects_enabled_or_guessed_selector(value):
    with pytest.raises(InfrastructureError):
        codex_process.toml_override_value(value)


@pytest.mark.parametrize("raw,category", [
    (b"WARN NEUTRAL loader diagnostic\n", "non_json_or_malformed_json"),
    (b'{"type":"error","message":"NEUTRAL"}\n', "diagnostic_event"),
    (b'{"type":"item.completed","item":{"type":"error","message":"NEUTRAL"}}\n', "diagnostic_item"),
    (b'{"type":"warning"}\n', "diagnostic_event"),
    (b'{"level":"WARN","message":"NEUTRAL"}\n', "diagnostic_severity"),
    (b'{"error":{"message":"NEUTRAL"}}\n', "event_error_field"),
    (b"\xff\n", "invalid_utf8"),
    (b"[]\n", "non_object_event"),
    (b'{"type":"item.completed","item":{}}\n', "unknown_or_tool_item"),
    (b'{"type":"item.completed","item":null}\n', "unknown_or_tool_item"),
    (b'{"type":"NEUTRAL-unknown-event"}\n', "unknown_event_type"),
    (b'{"type":"turn.completed","type":"error"}\n', "non_json_or_malformed_json"),
    (b'{"type":"turn.completed","duration":NaN}\n', "non_json_or_malformed_json"),
    (b"\n \n", "empty_cli_log"),
])
def test_all_raw_diagnostics_refused_without_allowlist(tmp_path, raw, category):
    path = tmp_path / "NEUTRAL.jsonl"
    path.write_bytes(raw)
    result = codex_process.diagnostics_from_events(path)
    assert result["clean"] is False and result["counts"].get(category) == 1
    assert result["codex_jsonl_sha256"] == sha256(raw)
    assert path.read_bytes() == raw
    assert result["diagnostic_allowlist_or_suppression"] is False
    assert "message" not in result["findings"][0]


def test_model_text_is_not_reclassified_as_system_diagnostic(tmp_path):
    raw = (b'{"type":"item.completed","item":{"id":"NEUTRAL","type":"agent_message","text":"NEUTRAL WARN word"}}\n'
           b'{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n')
    path = tmp_path / "NEUTRAL.jsonl"
    path.write_bytes(raw)
    assert codex_process.diagnostics_from_events(path)["clean"] is True


@pytest.mark.parametrize("raw", [b'{"type":"turn.started"}\n',
                                 b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n' * 2])
def test_missing_or_multiple_completed_events_never_promote_NORMAL(tmp_path, raw):
    path = tmp_path / "NEUTRAL-incomplete.jsonl"
    path.write_bytes(raw)
    result = codex_process.diagnostics_from_events(path)
    assert result["clean"] is False and result["counts"]["missing_or_ambiguous_completed_event"] == 1


@pytest.mark.parametrize("with_diagnostic", [False, True])
def test_result_is_checked_after_natural_process_completion(tmp_path, monkeypatch, with_diagnostic):
    output = tmp_path / "NEUTRAL-generation"
    output.mkdir()
    request = {"model": MODEL, "reasoning_effort": EFFORT, "session_id": "2" * 32,
               "nonce": "1" * 32, "expires_at": time.time() + 10,
               "messages": [{"role": "system", "content": "NEUTRAL"},
                            {"role": "user", "content": "NEUTRAL"}]}
    order = []
    monkeypatch.setattr(codex_process, "check_dependencies", lambda *args: {})
    monkeypatch.setattr(codex_process, "command_for", lambda *args: ["NEUTRAL-DO-NOT-EXECUTE"])

    def fake_process(argv, cwd, log, timeout, **kwargs):
        assert argv == ["NEUTRAL-DO-NOT-EXECUTE"]
        raw = b'{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n'
        if with_diagnostic:
            raw += b'{"type":"item.completed","item":{"type":"error","message":"NEUTRAL"}}\n'
        log.write_bytes(raw)
        atomic_json(output / "agent-result.json", {"NEUTRAL": True})
        order.append("process_returned_naturally")
        return SimpleNamespace(log=str(log), returncode=0, timed_out=False)

    inspect = codex_process.diagnostics_from_events

    def checked_after_completion(path):
        assert order == ["process_returned_naturally"]
        order.append("diagnostics_checked")
        return inspect(path)

    monkeypatch.setattr(codex_process, "run_process", fake_process)
    monkeypatch.setattr(codex_process, "diagnostics_from_events", checked_after_completion)
    response = codex_process.run_codex(request, "3" * 64, output, tmp_path / "NEUTRAL-gate.json", set())
    assert order == ["process_returned_naturally", "diagnostics_checked"]
    assert response["infrastructure_error"] is with_diagnostic
    assert response["data"] == (None if with_diagnostic else {"NEUTRAL": True})
    assert response["usage"]["tokens"] == 10
    assert response["usage"]["cli_diagnostic_count"] == int(with_diagnostic)
    assert (output / "agent-result.json").is_file()
    assert (output / "cli-diagnostics.json").is_file()


def delivered_fixture(tmp_path, *, technical=True):
    output = tmp_path / "NEUTRAL-cache"
    local = output / ("1" * 32)
    local.mkdir(parents=True)
    atomic_json(local / "response.json", {"infrastructure_error": technical})
    atomic_json(local / "delivered.json", {"response_sha256": file_digest(local / "response.json")})
    return output, local


def test_delivered_technical_hold_blocks_new_claim_but_preserves_cached_response(tmp_path):
    output, local = delivered_fixture(tmp_path)
    response_raw = (local / "response.json").read_bytes()
    r2max_worker.preserve_delivered_technical_hold(output, local)
    hold_raw = (output / "cli-technical-hold.json").read_bytes()
    assert json.loads(hold_raw)["new_generations_allowed"] is False
    r2max_worker.check_technical_hold(output, "1" * 32 + ".request.json")
    with pytest.raises(InfrastructureError, match="holds all new"):
        r2max_worker.check_technical_hold(output, "2" * 32 + ".request.json")
    assert not (output / ("2" * 32)).exists()
    r2max_worker.preserve_delivered_technical_hold(output, local)
    assert (local / "response.json").read_bytes() == response_raw
    assert (output / "cli-technical-hold.json").read_bytes() == hold_raw


def test_no_hold_for_algorithmic_negative(tmp_path):
    output, local = delivered_fixture(tmp_path, technical=False)
    (local / "delivered.json").unlink()
    r2max_worker.preserve_delivered_technical_hold(output, local)
    assert not (output / "cli-technical-hold.json").exists()


def test_hold_requires_exact_completed_delivery(tmp_path):
    output, local = delivered_fixture(tmp_path)
    atomic_json(local / "delivered.json", {"response_sha256": "f" * 64})
    with pytest.raises(InfrastructureError, match="fully delivered exact"):
        r2max_worker.preserve_delivered_technical_hold(output, local)
    assert not (output / "cli-technical-hold.json").exists()


def test_opaque_existing_hold_refuses_new_generation_without_parsing_it(tmp_path):
    output = tmp_path / "NEUTRAL-cache"
    output.mkdir()
    (output / "cli-technical-hold.json").write_bytes(b"NEUTRAL partial durable hold")
    with pytest.raises(InfrastructureError, match="holds all new"):
        r2max_worker.check_technical_hold(output, "3" * 32 + ".request.json")
    with pytest.raises(InfrastructureError, match="Unsafe"):
        r2max_worker.check_technical_hold(output, "../foreign.request.json")


def test_R2h_scope_and_sessions_are_new_and_MAX_only():
    assert native_r2max.SCOPE == 'hpc-forest-primes-native-max-r2h'
    assert native_r2max.EFFORT == "max"
    assert native_r2max.CELLS == {'gpt-6-luna': 'd231e8f9f0ee433b8f05aa8aa3fae22f', 'gpt-6-astra': '798b99a175d4454d9371e8ba898503e4', 'gpt-5.6-terra': '7a46678417dc450c93fd23f76132e90f', 'gpt-6.1-sol': '0f1de21e9eda4fb89a8dbd66c6fa8d6c'}


def policy_fixture(tmp_path):
    binding = {"scope_id": native_r2max.SCOPE, "model": MODEL, "effort": "max",
               "session_id": native_r2max.CELLS[MODEL], "job_id": "900000",
               "remote_root": "/scratch_p/NEUTRAL", "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64}
    value = {**command_policy(["C:/NEUTRAL/skill-one", "C:/NEUTRAL/skill-two"]),
             **binding, "cli_executable_sha256": "3" * 64,
             "skill_candidate_directories": ["C:/NEUTRAL/skill-one", "C:/NEUTRAL/skill-two"],
             "filesystem_metadata_sha256": "4" * 64, "is_actual_CLI_discovery_receipt": False,
             "instruction_or_SKILL_body_read": False}
    path = tmp_path / ("cli-policy-" + binding["session_id"] + ".json")
    atomic_json(path, value)
    return path, value, binding


def test_exact_local_policy_binds_cell_before_any_cli(tmp_path):
    path, value, binding = policy_fixture(tmp_path)
    assert codex_process.load_task_cli_policy(path, file_digest(path), binding, "3" * 64) == value
    with pytest.raises(InfrastructureError):
        codex_process.load_task_cli_policy(path, "f" * 64, binding, "3" * 64)
    with pytest.raises(InfrastructureError):
        codex_process.load_task_cli_policy(path, file_digest(path), {**binding, "model": "gpt-6-astra"}, "3" * 64)


@pytest.mark.parametrize("field,value", [
    ("instruction_or_SKILL_body_read", True), ("is_actual_CLI_discovery_receipt", True),
    ("cli_executable_sha256", "f" * 64), ("skill_candidate_directories", ["C:/NEUTRAL/../foreign"]),
    ("unknown_field", True),
])
def test_local_policy_mutation_refused(tmp_path, field, value):
    path, policy, binding = policy_fixture(tmp_path)
    policy[field] = value
    atomic_json(path, policy)
    with pytest.raises(InfrastructureError):
        codex_process.load_task_cli_policy(path, file_digest(path), binding, "3" * 64)


def projection_fixture(tmp_path, monkeypatch):
    policy_path, policy, _ = policy_fixture(tmp_path)
    monkeypatch.setattr(codex_process, "CLI_POLICY", policy)
    monkeypatch.setattr(codex_process.shutil, "which", lambda _: "C:/NEUTRAL/codex.exe")
    output = tmp_path / ("7" * 32)
    request = {"model": MODEL, "reasoning_effort": EFFORT, "schema": {"type": "object"},
               "messages": [{"role": "system", "content": "NEUTRAL"}, {"role": "user", "content": "NEUTRAL"}]}
    argv = codex_process.command_for(request, output)
    raw = output / "invocation.json"
    atomic_json(raw, {"argv": argv, "model": MODEL, "reasoning_effort": EFFORT,
                      "request_sha256": "8" * 64, "source_execution_allowed": False, "hosted_inference": True})
    cli = {"executable_path": argv[0], "task_cli_policy_sha256": file_digest(policy_path)}
    projection = codex_process.cli_metadata_projection(raw, cli["task_cli_policy_sha256"], "invocation")
    return raw, projection, cli


def test_projection_retains_actual_record_privately_and_never_exports_skill_paths(tmp_path, monkeypatch):
    raw, projection, cli = projection_fixture(tmp_path, monkeypatch)
    before = raw.read_bytes()
    record, argv = codex_process.check_cli_metadata_projection(projection, "invocation", cli, MODEL)
    assert record["model"] == MODEL and argv[0] == cli["executable_path"]
    assert "C:/NEUTRAL/skill-one" not in json.dumps(projection)
    assert projection["private_record_sha256"] == file_digest(raw)
    assert projection["private_argv_verified"] is False and projection["private_review_required"] is True
    assert raw.read_bytes() == before


@pytest.mark.parametrize("change", ["policy", "hash", "model", "flag", "array", "claim"])
def test_projection_mutations_refused(tmp_path, monkeypatch, change):
    _, projection, cli = projection_fixture(tmp_path, monkeypatch)
    if change == "policy":
        projection["task_cli_policy_sha256"] = "f" * 64
    elif change == "hash":
        projection["private_record_sha256"] = "malformed"
    elif change == "model":
        projection["argv_public"][12] = "NEUTRAL-other-model"
    elif change == "flag":
        projection["argv_public"][7] = "danger-full-access"
    elif change == "array":
        projection["argv_public"].insert(-1, "skills.config=[]")
    else:
        projection["private_argv_verified"] = True
    with pytest.raises((InfrastructureError, IndexError)):
        codex_process.check_cli_metadata_projection(projection, "invocation", cli, MODEL)


def test_two_metadata_uploads_are_projected_but_raw_stderr_is_not_filtered(tmp_path, monkeypatch):
    raw, _, cli = projection_fixture(tmp_path, monkeypatch)
    argv = json.loads(raw.read_bytes())["argv"]
    sidecar = raw.with_name("codex.jsonl.json")
    atomic_json(sidecar, {"argv": argv, "returncode": 0, "timed_out": False, "seconds": 1.0, "log": "NEUTRAL"})
    stderr = raw.with_name("codex.jsonl")
    stderr.write_bytes(b"WARN NEUTRAL remains raw\n")
    transferred = []

    class InertTransfer:
        async def upload(self, local, remote):
            transferred.append((local, remote, local.read_bytes()))
            return {"NEUTRAL": True}

    proxy = r2max_worker.LocalCliProjectionTransfers(InertTransfer(), "NEUTRAL-channel", cli["task_cli_policy_sha256"])
    for local in (raw, sidecar, stderr):
        before = local.read_bytes()
        coroutine = proxy.upload(local, "NEUTRAL-channel/logs/" + local.parent.name + "." + local.name)
        with pytest.raises(StopIteration):
            coroutine.send(None)
        assert local.read_bytes() == before
    assert all(b"C:/NEUTRAL/skill-one" not in payload for _, _, payload in transferred[:2])
    assert all(json.loads(payload)["projection_is_executable"] is False for _, _, payload in transferred[:2])
    assert transferred[2][2] == b"WARN NEUTRAL remains raw\n"


@pytest.mark.parametrize("prefix,exact", [
    (b"WARN NEUTRAL retained\n", True),
    (b"\xff\n", False),
    (b'{"type":"turn.completed","usage":{"input_tokens":2,"input_tokens":9,"output_tokens":1}}\n', False),
    (b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n', False),
    (b'{"type":"turn.completed"}\n', False),
])
def test_diagnostic_refusal_keeps_exact_usage_only_when_unambiguous(tmp_path, prefix, exact):
    path = tmp_path / "NEUTRAL-usage.jsonl"
    path.write_bytes(prefix + b'{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n')
    usage, _ = codex_process.usage_from_events(path)
    assert usage["token_accounting"] == ("exact" if exact else "upper_bound")
    assert usage["events"][-1] == {"input_tokens": 7, "output_tokens": 3}
    assert usage["tokens"] == (10 if exact else codex_process.TOKEN_CEILING)
