"""Pure versioned host-policy regressions; no CLI, host, model or transport starts."""
import json

import pytest

from hpc_forest import codex_process, native_r2max
from hpc_forest.codex_mailbox import EFFORT, MODEL
from hpc_forest.core import InfrastructureError, atomic_json, file_digest

FEATURE_NAMES = [
    "skip_host_skill_discovery", "shell_tool", "unified_exec", "apps", "plugins", "memories",
    "multi_agent", "multi_agent_v2", "hooks", "skill_search", "browser_use", "computer_use",
    "image_generation", "view_image", "workspace_dependencies", "code_mode_host", "code_mode",
    "code_mode_only", "sleep_tool", "unbounded_connection_retries", "shell_snapshot", "goals",
]


def policy_fixture(tmp_path):
    binding = {"scope_id": native_r2max.SCOPE, "model": MODEL, "effort": EFFORT,
               "session_id": native_r2max.CELLS[MODEL], "job_id": "900000",
               "remote_root": "/scratch_p/NEUTRAL", "source_zip_sha256": "1" * 64,
               "plan_sha256": "2" * 64}
    policy = {"schema": codex_process.TASK_CLI_POLICY_SCHEMA, **binding,
              "cli_executable_sha256": "3" * 64,
              "skill_candidate_directories": ["C:/NEUTRAL/skill-one"],
              "filesystem_metadata_sha256": "4" * 64,
              "is_actual_CLI_discovery_receipt": False, "instruction_or_SKILL_body_read": False,
              "cli_feature_overrides": dict(codex_process.TASK_CLI_FEATURES),
              "code_mode_host_executable_sha256": codex_process.CODE_MODE_HOST_SHA256}
    path = tmp_path / ("cli-policy-" + binding["session_id"] + ".json")
    atomic_json(path, policy)
    return path, policy, binding


def request_fixture():
    return {"model": MODEL, "reasoning_effort": EFFORT, "schema": {"type": "object"},
            "messages": [{"role": "system", "content": "NEUTRAL"},
                         {"role": "user", "content": "NEUTRAL"}]}


@pytest.mark.parametrize("feature", FEATURE_NAMES)
def test_any_feature_boolean_change_is_refused_before_generation(tmp_path, feature):
    path, policy, binding = policy_fixture(tmp_path)
    policy["cli_feature_overrides"][feature] = not policy["cli_feature_overrides"][feature]
    atomic_json(path, policy)
    with pytest.raises(InfrastructureError):
        codex_process.load_task_cli_policy(path, file_digest(path), binding, "3" * 64)


@pytest.mark.parametrize("mutation", ["old_schema", "missing_host_pin", "wrong_host_pin",
                                     "missing_feature", "extra_feature", "numeric_host", "numeric_tool"])
def test_host_contract_schema_pin_and_closed_typed_map_are_required(tmp_path, mutation):
    path, policy, binding = policy_fixture(tmp_path)
    if mutation == "old_schema":
        policy["schema"] = "hpc-forest-r2e-local-cli-policy-v1"
    elif mutation == "missing_host_pin":
        del policy["code_mode_host_executable_sha256"]
    elif mutation == "wrong_host_pin":
        policy["code_mode_host_executable_sha256"] = "f" * 64
    elif mutation == "missing_feature":
        del policy["cli_feature_overrides"]["shell_tool"]
    elif mutation == "extra_feature":
        policy["cli_feature_overrides"]["NEUTRAL_unknown"] = False
    else:
        policy["cli_feature_overrides"]["code_mode_host" if mutation == "numeric_host" else "shell_tool"] = (
            1 if mutation == "numeric_host" else 0)
    atomic_json(path, policy)
    with pytest.raises(InfrastructureError):
        codex_process.load_task_cli_policy(path, file_digest(path), binding, "3" * 64)


@pytest.mark.parametrize("policy", [None, {}, {"schema": "hpc-forest-r2e-local-cli-policy-v1"}])
def test_unversioned_command_is_refused_before_cli_lookup_or_output(tmp_path, monkeypatch, policy):
    monkeypatch.setattr(codex_process, "CLI_POLICY", policy)

    def forbidden_lookup(_):
        raise AssertionError("No CLI lookup is allowed before the versioned policy")

    monkeypatch.setattr(codex_process.shutil, "which", forbidden_lookup)
    output = tmp_path / "NEUTRAL-not-created"
    with pytest.raises(InfrastructureError, match="versioned R2g"):
        codex_process.command_for(request_fixture(), output)
    assert not output.exists()


def projection_fixture(tmp_path, monkeypatch):
    path, policy, binding = policy_fixture(tmp_path)
    assert codex_process.load_task_cli_policy(path, file_digest(path), binding, "3" * 64) == policy
    monkeypatch.setattr(codex_process, "CLI_POLICY", policy)
    monkeypatch.setattr(codex_process.shutil, "which", lambda _: "C:/NEUTRAL/codex.exe")
    output = tmp_path / ("7" * 32)
    argv = codex_process.command_for(request_fixture(), output)
    raw = output / "invocation.json"
    atomic_json(raw, {"argv": argv, "model": MODEL, "reasoning_effort": EFFORT,
                      "source_execution_allowed": False, "hosted_inference": True})
    cli = {"executable_path": argv[0], "task_cli_policy_sha256": file_digest(path)}
    return policy, codex_process.cli_metadata_projection(raw, file_digest(path), "invocation"), cli


def test_canonical_feature_order_is_independent_of_private_JSON_order(tmp_path, monkeypatch):
    policy, projection, cli = projection_fixture(tmp_path, monkeypatch)
    canonical = list(projection["argv_public"])
    policy["cli_feature_overrides"] = dict(reversed(list(policy["cli_feature_overrides"].items())))
    monkeypatch.setattr(codex_process, "CLI_POLICY", policy)
    argv = codex_process.command_for(request_fixture(), tmp_path / ("7" * 32))
    assert [arg.split("=", 1)[0][9:] for arg in argv if arg.startswith("features.")] == FEATURE_NAMES
    assert sum(arg == "features.code_mode_host=true" for arg in argv) == 1
    assert all(arg.endswith("=false") for arg in argv
               if arg.startswith("features.") and not arg.startswith("features.code_mode_host="))
    raw = tmp_path / ("7" * 32) / "invocation.json"
    atomic_json(raw, {"argv": argv, "model": MODEL, "reasoning_effort": EFFORT})
    shuffled = codex_process.cli_metadata_projection(raw, cli["task_cli_policy_sha256"], "invocation")
    assert shuffled["argv_public"] == canonical
    codex_process.check_cli_metadata_projection(shuffled, "invocation", cli, MODEL)


@pytest.mark.parametrize("mutation", ["host_false", "tool_true", "numeric_host", "extra_feature", "missing_feature"])
def test_public_projection_does_not_reintroduce_tool_or_old_host_policy(tmp_path, monkeypatch, mutation):
    _, projection, cli = projection_fixture(tmp_path, monkeypatch)
    argv = projection["argv_public"]
    index = argv.index("features.code_mode_host=true")
    if mutation == "host_false":
        argv[index] = "features.code_mode_host=false"
    elif mutation == "tool_true":
        argv[argv.index("features.shell_tool=false")] = "features.shell_tool=true"
    elif mutation == "numeric_host":
        argv[index] = "features.code_mode_host=1"
    elif mutation == "extra_feature":
        argv[-1:-1] = ["--config", "features.NEUTRAL_unknown=false"]
    else:
        del argv[index - 1:index + 1]
    with pytest.raises(InfrastructureError):
        codex_process.check_cli_metadata_projection(projection, "invocation", cli, MODEL)


@pytest.mark.parametrize("item_type", ["command_execution", "mcp_tool_call", "web_search"])
def test_host_candidate_never_admits_tool_events(tmp_path, item_type):
    raw = (json.dumps({"type": "item.completed", "item": {"type": item_type}}) + "\n" +
           json.dumps({"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3}}) + "\n").encode()
    path = tmp_path / "NEUTRAL-tool-event.jsonl"
    path.write_bytes(raw)
    assert codex_process.diagnostics_from_events(path)["clean"] is False
    usage, tools = codex_process.usage_from_events(path)
    assert tools is True and usage["tool_events"] == [item_type]
    assert path.read_bytes() == raw
