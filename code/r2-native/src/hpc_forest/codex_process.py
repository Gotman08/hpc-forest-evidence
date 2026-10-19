"""Native Codex generation with an explicit model/effort and no candidate execution."""
from __future__ import annotations

import copy
import json
import re
import shutil
import time
import tomllib
from pathlib import Path
from subprocess import list2cmdline

from .codex_mailbox import (
    EFFORT,
    MODEL,
    TOKEN_CEILING,
    bounded_json,
    response_envelope,
    sha256,
)
from .core import InfrastructureError, atomic_json, run_process

CLI_POLICY = None  # Populated only by the exact per-task local policy in the admitted worker.
TASK_CLI_POLICY_SCHEMA = "hpc-forest-r2g-local-cli-policy-v1"
CODE_MODE_HOST_SHA256 = "3b6a9179a4da17fa5fc6948219cd61486dc3b534c683838076d8c61bd311c68e"
# Versioned infrastructure candidate, never a claim of effective runtime isolation.
# Every tool-facing feature remains false; the event/diagnostic refusal is unchanged.
TASK_CLI_FEATURES = {"skip_host_skill_discovery": False, **{
    name: name == "code_mode_host" for name in [
        "shell_tool", "unified_exec", "apps", "plugins", "memories", "multi_agent",
        "multi_agent_v2", "hooks", "skill_search", "browser_use", "computer_use",
        "image_generation", "view_image", "workspace_dependencies", "code_mode_host",
        "code_mode", "code_mode_only", "sleep_tool", "unbounded_connection_retries",
        "shell_snapshot", "goals",
    ]}}


def load_task_cli_policy(path: Path, checksum: str, binding: dict, executable_sha256: str) -> dict:
    """Read only a hash-bound local task policy, never discover or read skill bodies."""
    if (not path.is_absolute() or path.name != "cli-policy-" + binding["session_id"] + ".json"
            or ".." in path.parts or not path.is_file()
            or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents))
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or sha256(path.read_bytes()) != checksum):
        raise InfrastructureError("Exact ordinary hash-bound local CLI policy required")
    value = bounded_json(path, 262144)
    expected_fields = {"schema", *binding, "cli_executable_sha256", "skill_candidate_directories",
                       "filesystem_metadata_sha256", "is_actual_CLI_discovery_receipt",
                       "instruction_or_SKILL_body_read", "cli_feature_overrides",
                       "code_mode_host_executable_sha256"}
    paths = value.get("skill_candidate_directories")
    features = value.get("cli_feature_overrides")
    if (set(value) != expected_fields or value.get("schema") != TASK_CLI_POLICY_SCHEMA
            or value.get("code_mode_host_executable_sha256") != CODE_MODE_HOST_SHA256
            or not isinstance(features, dict) or set(features) != set(TASK_CLI_FEATURES)
            or any(features.get(name) is not enabled for name, enabled in TASK_CLI_FEATURES.items())
            or any(value.get(key) != expected for key, expected in binding.items())
            or value.get("cli_executable_sha256") != executable_sha256
            or value.get("is_actual_CLI_discovery_receipt") is not False
            or value.get("instruction_or_SKILL_body_read") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("filesystem_metadata_sha256", ""))
            or not isinstance(paths, list) or not 0 < len(paths) <= 512
            or any(not isinstance(p, str) or not re.match(r"^[A-Za-z]:[/\\]", p)
                   or ".." in p.replace("\\", "/").split("/")
                   or any(char in p for char in ("\0", "\n", "\r")) for p in paths)
            or len(set(paths)) != len(paths)):
        raise InfrastructureError("Local CLI policy differs from the exact versioned R2g cell")
    return value


def task_feature_overrides() -> dict:
    """No host-enabled command may be built with an old or missing task policy."""
    policy = CLI_POLICY or {}
    features = policy.get("cli_feature_overrides")
    if (policy.get("schema") != TASK_CLI_POLICY_SCHEMA
            or policy.get("code_mode_host_executable_sha256") != CODE_MODE_HOST_SHA256
            or not isinstance(features, dict) or set(features) != set(TASK_CLI_FEATURES)
            or any(features.get(name) is not enabled for name, enabled in TASK_CLI_FEATURES.items())):
        raise InfrastructureError("The exact versioned R2g host candidate policy is required")
    return dict(TASK_CLI_FEATURES)


def toml_override_value(value):
    """Serialize the closed per-task primitive/skill-selector types as TOML, not JSON maps."""
    if type(value) in (bool, int, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(toml_override_value(item) for item in value) + "]"
    if isinstance(value, dict) and set(value) == {"path", "enabled"}:
        if not isinstance(value["path"], str) or value["enabled"] is not False:
            raise InfrastructureError("Only explicit disabled skill path selectors are supported")
        return "{path=" + toml_override_value(value["path"]) + ",enabled=false}"
    raise InfrastructureError("Unsupported task CLI override type")


def cli_metadata_projection(path: Path, policy_sha256: str, kind: str) -> dict:
    """Keep actual argv locally; export an explicitly non-executable digest projection."""
    record = bounded_json(path, 262144)
    argv = record.get("argv")
    if kind not in {"invocation", "process"} or not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        raise InfrastructureError("Exact private CLI record required for projection")
    indices = [i for i, arg in enumerate(argv) if arg.startswith("skills.config=")]
    expected = "skills.config=" + toml_override_value([
        {"path": directory, "enabled": False} for directory in (CLI_POLICY or {}).get("skill_candidate_directories", [])])
    if (not CLI_POLICY or len(indices) != 1 or indices[0] < 1 or argv[indices[0] - 1] != "--config"
            or argv[indices[0]] != expected):
        raise InfrastructureError("Only the exact hash-bound local skill selector may be omitted")
    index = indices[0]
    return {"schema": "hpc-forest-r2e-private-cli-metadata-projection-v1", "kind": kind,
            "record_without_private_argv": {key: value for key, value in record.items() if key != "argv"},
            "argv_public": argv[:index - 1] + argv[index + 1:],
            "private_record_sha256": sha256(path.read_bytes()),
            "private_argv_sha256": sha256(json.dumps(argv, ensure_ascii=False, sort_keys=True).encode("utf8")),
            "private_skill_override_sha256": sha256(expected.encode("utf8")),
            "task_cli_policy_sha256": policy_sha256,
            "private_skill_path_count": len(CLI_POLICY["skill_candidate_directories"]),
            "private_review_required": True, "private_argv_verified": False,
            "projection_is_executable": False, "raw_record_exported": False}


def check_cli_metadata_projection(value: dict, kind: str, cli: dict, model: str) -> tuple[dict, list[str]]:
    fields = {"schema", "kind", "record_without_private_argv", "argv_public", "private_record_sha256",
              "private_argv_sha256", "private_skill_override_sha256", "task_cli_policy_sha256",
              "private_skill_path_count", "private_review_required", "private_argv_verified",
              "projection_is_executable", "raw_record_exported"}
    if (set(value) != fields or value.get("schema") != "hpc-forest-r2e-private-cli-metadata-projection-v1"
            or value.get("kind") != kind or value.get("private_review_required") is not True
            or any(value.get(key) is not False for key in ("private_argv_verified", "projection_is_executable", "raw_record_exported"))
            or value.get("task_cli_policy_sha256") != cli.get("task_cli_policy_sha256")
            or any(not isinstance(value.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", value[key])
                   for key in ("private_record_sha256", "private_argv_sha256", "private_skill_override_sha256", "task_cli_policy_sha256"))
            or type(value.get("private_skill_path_count")) is not int or not 0 < value["private_skill_path_count"] <= 512):
        raise InfrastructureError("Exact non-executable private CLI projection required")
    argv = value.get("argv_public")
    record = value.get("record_without_private_argv")
    if (not isinstance(argv, list) or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in argv)
            or not argv or argv[0] != cli["executable_path"] or argv[1:2] != ["exec"]
            or argv.count("--model") != 1 or argv[argv.index("--model") + 1] != model
            or argv.count("--strict-config") != 1 or argv.count("--ignore-user-config") != 1
            or any(arg.startswith("skills.config=") for arg in argv) or not isinstance(record, dict) or "argv" in record):
        raise InfrastructureError("CLI projection identity or public argv differs")
    if (argv[:14] != [cli["executable_path"], "exec", "--ignore-user-config", "--strict-config", "--ephemeral",
                      "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
                      "--model", model, "--output-schema"]
            or len(argv) < 20 or argv[15] != "--output-last-message" or argv[17] != "-C" or argv[-1] != "-"
            or len(argv[19:-1]) % 2 or any(argv[i] != "--config" for i in range(19, len(argv) - 1, 2))):
        raise InfrastructureError("CLI public command layout differs from the frozen source-only constructor")
    try:
        config = tomllib.loads("\n".join(argv[i + 1] for i, arg in enumerate(argv) if arg == "--config"))
    except (IndexError, ValueError) as exc:
        raise InfrastructureError("CLI public configuration projection is malformed") from exc
    features = config.get("features")
    if (config.get("model_reasoning_effort") != "max" or config.get("forced_login_method") != "chatgpt"
            or config.get("web_search") != "disabled" or not config.get("features")
            or config.get("approval_policy") != "never" or config.get("project_doc_max_bytes") != 0
            or config.get("model_context_window") != 65536
            or not isinstance(features, dict) or set(features) != set(TASK_CLI_FEATURES)
            or any(features.get(name) is not enabled for name, enabled in TASK_CLI_FEATURES.items())
            or config.get("skills") != {"max_context_tokens": 1, "include_instructions": False,
                                         "bundled": {"enabled": False}}):
        raise InfrastructureError("CLI public no-tools/MAX/OAuth/skills guards differ")
    return record, argv


def check_dependencies(receipt: Path, required_jobs: set[str]) -> dict:
    gate = bounded_json(receipt, 65536)
    if gate.get("status") == "harness_comparison_explicitly_authorized":
        if (gate.get("schema") != "hpc-forest-explicit-harness-comparison-v1"
                or gate.get("scope_id") != "gpt61sol-max-harness-20261015-r2"
                or required_jobs != {gate.get("scope_id")}
                or gate.get("next_model") != MODEL or gate.get("reasoning_effort") != EFFORT
                or gate.get("problems") != ["knn", "sum", "nbody"]
                or gate.get("arms") != ["reference", "mixed-harness"]
                or gate.get("harness_enabled") is not True
                or gate.get("max_calls_per_harness_mission") != 3
                or gate.get("planned_slots_per_problem_per_arm") != 24
                or gate.get("wall_seconds_per_problem_per_arm") != 7200
                or gate.get("token_budget_per_problem_per_arm") != 1500000
                or gate.get("deepseek_completion_claimed") is not False
                or not isinstance(gate.get("user_message"), str)
                or not gate["user_message"].strip()
                or gate.get("expires_at", 0) <= time.time()):
            raise InfrastructureError("The explicit harness comparison authorization is invalid or expired")
        return gate
    if gate.get("status") == "parallel_pilot_explicitly_authorized":
        if (gate.get("schema") != "hpc-forest-explicit-parallel-pilot-v1"
                or gate.get("scope_id") != "gpt61sol-max-pilot-20261015-r1"
                or required_jobs != {gate.get("scope_id")}
                or gate.get("next_model") != MODEL or gate.get("reasoning_effort") != EFFORT
                or gate.get("deepseek_completion_claimed") is not False
                or not isinstance(gate.get("user_message"), str)
                or not gate["user_message"].strip()
                or gate.get("expires_at", 0) <= time.time()):
            raise InfrastructureError("The explicit parallel pilot authorization is invalid or expired")
        return gate
    if (gate.get("status") != "deepseek_results_received_and_audited"
            or gate.get("next_model") != MODEL or gate.get("reasoning_effort") != EFFORT
            or set(gate.get("finished_job_ids", [])) != required_jobs):
        raise InfrastructureError("DeepSeek completion and receipt have not been established")
    archives = gate.get("archives", [])
    if len(archives) != len(required_jobs) or {a.get("job_id") for a in archives} != required_jobs:
        raise InfrastructureError("Missing DeepSeek archive receipts")
    for item in archives:
        archive = Path(item["path"])
        if archive.is_symlink() or not archive.is_file():
            raise InfrastructureError("A received DeepSeek archive is unavailable")
        if sha256(archive.read_bytes()) != item.get("sha256"):
            raise InfrastructureError("A received DeepSeek archive changed")
    return gate


def wire_schema(schema: dict) -> dict:
    """Drop provider-specific array keywords; the source validator keeps enforcing them."""
    schema = copy.deepcopy(schema)

    def visit(value):
        if isinstance(value, dict):
            value.pop("uniqueItems", None)
            value.pop("maxItems", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


def command_for(request: dict, output: Path, executable: str = "codex") -> list[str]:
    if request.get("model") != MODEL or request.get("reasoning_effort") != EFFORT:
        raise InfrastructureError("A different model or reasoning effort is forbidden")
    features = task_feature_overrides()
    executable = shutil.which(executable)
    if not executable:
        raise InfrastructureError("The authenticated Codex CLI is unavailable locally")
    output.mkdir(parents=True, exist_ok=True)
    messages = request["messages"]
    if [m.get("role") for m in messages] != ["system", "user"]:
        raise InfrastructureError("Expected the frozen neutral system/user prompt")
    (output / "instructions.txt").write_text(messages[0]["content"], encoding="utf8")
    atomic_json(output / "output-schema.json", wire_schema(request["schema"]))
    args = [executable, "exec", "--ignore-user-config", "--strict-config", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
            "--model", MODEL, "--output-schema", str(output / "output-schema.json"),
            "--output-last-message", str(output / "agent-result.json"), "-C", str(output)]
    overrides = {
        "model_reasoning_effort": EFFORT,
        "model_instructions_file": str(output / "instructions.txt"),
        "model_context_window": 65536,
        "project_doc_max_bytes": 0,
        "skills.max_context_tokens": 1,
        "skills.config": [{"path": path, "enabled": False}
                          for path in (CLI_POLICY or {}).get("skill_candidate_directories", [])],
        "skills.include_instructions": False,
        "skills.bundled.enabled": False,
        "approval_policy": "never",
        "forced_login_method": "chatgpt",
        "web_search": "disabled",
        "features.skip_host_skill_discovery": False,
        **{f"features.{name}": enabled for name, enabled in features.items()
           if name != "skip_host_skill_discovery"},
    }
    for key, value in overrides.items():
        args.extend(["--config", f"{key}={toml_override_value(value)}"])
    command = [*args, "-"]
    if len(list2cmdline(command).encode("utf-16-le")) // 2 + 1 > 32767:
        raise InfrastructureError("Exact quoted command exceeds the Windows process argument limit")
    return command


def usage_from_events(path: Path) -> tuple[dict, bool]:
    usage_events, tool_events = [], []
    ambiguous, completed = False, 0

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON member")
            result[key] = value
        return result

    for raw_line in path.read_bytes().splitlines():
        try:
            line = raw_line.decode("utf8", errors="strict")
        except UnicodeDecodeError:
            ambiguous = True
            continue
        try:
            event = json.loads(line, object_pairs_hook=pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        except ValueError:
            if line.lstrip().startswith(("{", "[")):
                ambiguous = True
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.completed":
            completed += 1
            if isinstance(event.get("usage"), dict):
                usage_events.append(event["usage"])
        item = event.get("item", {})
        if event.get("type") in {"item.started", "item.completed", "item.updated"}:
            if item.get("type") not in {"agent_message", "reasoning", "error", None}:
                tool_events.append(item.get("type"))
    required_usage = {"input_tokens", "output_tokens"}
    optional_usage = {"cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens"}
    known = not ambiguous and completed == len(usage_events) == 1 and all(
        required_usage <= set(u) <= required_usage | optional_usage
        and all(type(value) is int and value >= 0 for value in u.values())
        and all(u.get(key, 0) <= u.get("input_tokens", -1) for key in ("cached_input_tokens", "cache_write_input_tokens"))
        and u.get("reasoning_output_tokens", 0) <= u.get("output_tokens", -1)
        for u in usage_events)
    return {
        "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in usage_events)
        if known else TOKEN_CEILING,
        "token_accounting": "exact" if known else "upper_bound",
        "events": usage_events, "llm_calls": max(1, len(usage_events)),
        "usage_parse_ambiguity": ambiguous or completed != len(usage_events) or completed > 1,
        "model_requested": MODEL, "reasoning_effort_requested": EFFORT,
        "cached_tokens_included_in_input": True, "tool_events": tool_events,
        "codex_jsonl_sha256": sha256(path.read_bytes()),
    }, bool(tool_events)


def diagnostics_from_events(path: Path) -> dict:
    """Inspect completed raw output without accepting or filtering diagnostic text."""
    raw = path.read_bytes()
    findings = []
    nonempty = 0
    completed_count = 0

    def closed_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON member")
            result[key] = value
        return result

    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        nonempty += 1
        category = None
        try:
            text = line.decode("utf8", errors="strict")
        except UnicodeDecodeError:
            category = "invalid_utf8"
        else:
            try:
                event = json.loads(text, object_pairs_hook=closed_pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
            except ValueError:
                category = "non_json_or_malformed_json"
            else:
                if not isinstance(event, dict):
                    category = "non_object_event"
                else:
                    item = event.get("item")
                    if event.get("type") == "turn.completed":
                        completed_count += 1
                    diagnostic_types = {"error", "warning", "warn", "fatal"}
                    if str(event.get("type", "")).casefold() in diagnostic_types:
                        category = "diagnostic_event"
                    elif isinstance(item, dict) and str(item.get("type", "")).casefold() in diagnostic_types:
                        category = "diagnostic_item"
                    elif event.get("error") is not None:
                        category = "event_error_field"
                    elif any(str(event.get(key, "")).casefold() in diagnostic_types
                             for key in ("level", "severity")):
                        category = "diagnostic_severity"
                    elif event.get("type") == "thread.started":
                        if set(event) != {"type", "thread_id"} or not isinstance(event["thread_id"], str) or not event["thread_id"]:
                            category = "unknown_thread_shape"
                    elif event.get("type") == "turn.started":
                        if set(event) != {"type"}:
                            category = "unknown_turn_shape"
                    elif event.get("type") in {"item.started", "item.updated", "item.completed"}:
                        if (set(event) != {"type", "item"} or not isinstance(item, dict)
                                or set(item) != {"id", "type", "text"}
                                or item.get("type") not in {"reasoning", "agent_message"}
                                or not isinstance(item.get("id"), str) or not item["id"]
                                or not isinstance(item.get("text"), str)):
                            category = "unknown_or_tool_item"
                    elif event.get("type") == "turn.completed":
                        usage = event.get("usage")
                        required = {"input_tokens", "output_tokens"}
                        optional = {"cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens"}
                        if (set(event) != {"type", "usage"} or not isinstance(usage, dict)
                                or not required <= set(usage) <= required | optional
                                or any(type(value) is not int or value < 0 for value in usage.values())
                                or any(usage.get(key, 0) > usage.get("input_tokens", -1)
                                       for key in ("cached_input_tokens", "cache_write_input_tokens"))
                                or usage.get("reasoning_output_tokens", 0) > usage.get("output_tokens", -1)):
                            category = "unknown_or_invalid_usage"
                    else:
                        category = "unknown_event_type"
        if category:
            findings.append({"line": number, "category": category, "line_sha256": sha256(line)})
    if not nonempty:
        findings.append({"line": 0, "category": "empty_cli_log", "line_sha256": sha256(raw)})
    if completed_count != 1:
        findings.append({"line": 0, "category": "missing_or_ambiguous_completed_event", "line_sha256": sha256(raw)})
    counts = {}
    for finding in findings:
        counts[finding["category"]] = counts.get(finding["category"], 0) + 1
    return {"schema": "hpc-forest-completed-cli-diagnostics-v1",
            "clean": not findings, "findings": findings, "counts": counts,
            "nonempty_lines_examined": nonempty, "raw_bytes": len(raw),
            "codex_jsonl_sha256": sha256(raw), "raw_log_preserved": True,
            "diagnostic_allowlist_or_suppression": False,
            "process_interrupted_by_this_check": False}


def run_codex(request: dict, request_sha: str, output: Path, dependency_receipt: Path,
              required_jobs: set[str], executable="codex") -> dict:
    gate = check_dependencies(dependency_receipt, required_jobs)
    if (gate.get("status") in {"parallel_pilot_explicitly_authorized",
                               "harness_comparison_explicitly_authorized"}
            and request.get("session_id") != gate.get("session_id")):
        raise InfrastructureError("Generation belongs to another explicitly authorized session")
    timeout = request["expires_at"] - time.time() - 5
    if timeout <= 0:
        return response_envelope(request, request_sha, error="Request expired before generation",
                                 infrastructure_error=True,
                                 usage={"tokens": 0, "token_accounting": "exact", "llm_calls": 0})
    argv = command_for(request, output, executable)
    atomic_json(output / "invocation.json", {
        "argv": argv, "model": MODEL, "reasoning_effort": EFFORT,
        "request_sha256": request_sha, "hosted_inference": True,
        "source_execution_allowed": False,
    })
    atomic_json(output / "request.json", request)
    result = run_process(argv, output, output / "codex.jsonl", timeout,
                         env={"OPENAI_API_KEY": "", "CODEX_API_KEY": ""},
                         stdin=request["messages"][1]["content"])
    diagnostics = diagnostics_from_events(Path(result.log))
    atomic_json(output / "cli-diagnostics.json", diagnostics)
    usage, tools = usage_from_events(Path(result.log))
    usage["cli_diagnostics_sha256"] = sha256((output / "cli-diagnostics.json").read_bytes())
    usage["cli_diagnostic_count"] = len(diagnostics["findings"])
    error = None
    infra = False
    data = None
    if result.returncode or result.timed_out:
        error, infra = "Codex failed or exceeded the generation deadline; inspect its log", True
    elif not diagnostics["clean"]:
        error, infra = "Completed Codex output contains unaccepted diagnostics; inspect preserved raw log", True
    elif tools:
        error, infra = "Codex attempted a tool call in a source-only generation", True
    else:
        try:
            data = bounded_json(output / "agent-result.json")
        except (OSError, ValueError, InfrastructureError) as exc:
            error = f"Codex returned no valid structured proposal: {exc}"
    response = response_envelope(request, request_sha, data=data, usage=usage,
                                 error=error, infrastructure_error=infra)
    atomic_json(output / "response.json", response)
    return response
