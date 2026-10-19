"""Read-only, closed-inventory validation of a settled source127 worker cache.

This module never imports the native runtime, collects processes, or writes files.
The caller establishes worker absence and supplies nonces from received cold
terminal evidence; this check cannot establish either fact on its own.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from pathlib import Path

PROTOCOL = "hpc-forest-codex-mailbox-v1"
BINDING_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
                  "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
ROOT_FILES = {"CELL-BINDING.json", "OWNER.json", "worker-ready.json", "worker.lock"}
NONCE_FILES = {"downloaded-request.json", "download-receipt.json", "generation-claimed.json", "instructions.txt",
               "output-schema.json", "invocation.json", "request.json", "codex.jsonl", "codex.jsonl.json",
               "cli-diagnostics.json", "agent-result.json", "response.json", "response-ready.json", "delivered.json",
               "invocation.json.arm-projection.json", "codex.jsonl.json.arm-projection.json"}
REQUIRED_NONCE_FILES = {"downloaded-request.json", "generation-claimed.json", "response.json",
                        "response-ready.json", "delivered.json", "codex.jsonl", "codex.jsonl.json",
                        "invocation.json", "cli-diagnostics.json"}
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
SOURCE127_PINS = {
    "codex_mailbox.py": "864207e639aa99d5a7d5a0a51b914ed5225df09e4cd357547eb7ef173e79f14c",
    "codex_worker.py": "a07d231e5bec01b6402503b391afb0a164c833420ce4bc67f5957aabb8ffb3ec",
    "matrix15_worker.py": "4544fc1fa0ca1074349a3a9e5b58038302e786b7ee78f4088ac3cb2228210ed3",
    "native_matrix15.py": "7cd89d37dec6da660d4c5942054444fa789cb944c69fa9b34dad02b70a426e32",
    "codex_process.py": "efe23b4c69a769e58f620e3938a3f6549fc9d6b93960abf4e19f66a3e7254868",
}


class CacheError(ValueError):
    """The cache cannot support a settled, fully accounted closure."""


def need(condition, message):
    if not condition:
        raise CacheError(message)


def _pairs(items):
    value = {}
    for key, item in items:
        need(key not in value, "Duplicate cache JSON member")
        value[key] = item
    return value


def _constant(_):
    raise CacheError("Nonfinite cache JSON value")


def _json(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CacheError("Invalid cache JSON") from exc
    need(type(value) is dict, "Cache JSON must be an object")
    return value


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _same(actual, expected):
    """JSON structural equality that keeps booleans distinct from integers."""
    return json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(expected, sort_keys=True, separators=(",", ":"))


def _snapshot(root, no_redirects):
    """Reject redirects and unknown entries, and retain stable file identity/bytes."""
    files, directories = {}, set()

    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def inspect(path, directory):
        no_redirects(path)
        info = path.lstat()
        need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()
             and not getattr(info, "st_file_attributes", 0) & 0x400, "Linked cache entry refused")
        need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "Nonregular cache entry")
        if not directory:
            need(info.st_nlink == 1, "Hard-linked cache file refused")
        return info

    inspect(root, True)
    root_entries = list(root.iterdir())
    for path in root_entries:
        name = path.name
        if name in ROOT_FILES:
            inspect(path, False)
        else:
            need(HEX32.fullmatch(name), "Unknown cache root entry or technical hold")
            inspect(path, True)
            directories.add(name)
    need({path.name for path in root_entries if path.name in ROOT_FILES} == ROOT_FILES,
         "Incomplete worker cache root identity")
    paths = [root / name for name in ROOT_FILES]
    for nonce in sorted(directories):
        children = list((root / nonce).iterdir())
        names = {path.name for path in children}
        need(names <= NONCE_FILES, "Unknown nonce file, temporary file or nested directory")
        need(REQUIRED_NONCE_FILES <= names, "Incomplete claimed nonce evidence")
        paths.extend(children)
    for path in sorted(paths):
        before = inspect(path, False)
        raw = path.read_bytes()
        after = inspect(path, False)
        need(identity(before) == identity(after) and len(raw) == after.st_size, "Cache file changed during reading")
        files[path.relative_to(root).as_posix()] = (raw, identity(after))
    return directories, files


def _identity(value, binding):
    return all(value.get(key) == item for key, item in binding.items())


def _validate_root(files, binding):
    def load(name):
        return _json(files[name][0])

    need(load("CELL-BINDING.json") == binding, "Cache CELL-BINDING differs")
    expected_owner = {**binding, "protocol": PROTOCOL, "owner": binding["job_id"], "reasoning_effort": "max"}
    need(load("OWNER.json") == expected_owner, "Cache OWNER differs from the native cell")
    ready = load("worker-ready.json")
    extra = {"mode", "pid", "started_at", "local_python", "codex_executable", "codex_cli_version",
             "codex_executable_sha256", "authentication", "weight_digest_available", "model_weights_on_romeo",
             "task_cli_policy_sha256", "task_cli_policy_candidate_count", "local_skill_paths_exported"}
    need(set(ready) == set(expected_owner) | extra and _identity(ready, expected_owner), "Cache ready identity differs")
    need(ready["mode"] == "codex" and type(ready["pid"]) is int and ready["pid"] > 0
         and _finite(ready["started_at"]) and ready["authentication"] == "existing-local-ChatGPT"
         and all(ready[key] is False for key in ("weight_digest_available", "model_weights_on_romeo", "local_skill_paths_exported"))
         and type(ready["task_cli_policy_candidate_count"]) is int and ready["task_cli_policy_candidate_count"] >= 0
         and all(isinstance(ready[key], str) and ready[key] for key in ("local_python", "codex_executable", "codex_cli_version"))
         and all(isinstance(ready[key], str) and SHA.fullmatch(ready[key])
                 for key in ("codex_executable_sha256", "task_cli_policy_sha256")), "Invalid native worker readiness metadata")
    need(files["worker.lock"][0] == b"0", "Unexpected worker lock bytes")


def _usage_from_log(raw):
    events, completed, nonempty = [], 0, 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        nonempty += 1
        value = _json(line)
        kind = value.get("type")
        if kind == "thread.started":
            need(set(value) == {"type", "thread_id"} and isinstance(value["thread_id"], str) and value["thread_id"],
                 "Unknown thread event in CLI log")
        elif kind == "turn.started":
            need(set(value) == {"type"}, "Unknown turn event in CLI log")
        elif kind in {"item.started", "item.completed", "item.updated"}:
            item = value.get("item")
            need(set(value) == {"type", "item"} and type(item) is dict and set(item) == {"id", "type", "text"}
                 and item["type"] in {"agent_message", "reasoning"} and isinstance(item["id"], str) and item["id"]
                 and isinstance(item["text"], str), "Diagnostic, unknown or tool item in CLI log")
        elif kind == "turn.completed":
            completed += 1
            need(set(value) == {"type", "usage"} and type(value.get("usage")) is dict, "CLI turn has no exact usage")
            events.append(value["usage"])
        else:
            raise CacheError("Diagnostic or unknown event in CLI log")
    need(completed == len(events) == 1, "CLI usage is ambiguous or incomplete")
    value = events[0]
    required, optional = {"input_tokens", "output_tokens"}, {"cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens"}
    need(required <= set(value) <= required | optional and all(type(item) is int and item >= 0 for item in value.values())
         and all(value.get(key, 0) <= value["input_tokens"] for key in ("cached_input_tokens", "cache_write_input_tokens"))
         and value.get("reasoning_output_tokens", 0) <= value["output_tokens"], "Invalid CLI exact usage event")
    return events, value["input_tokens"] + value["output_tokens"], nonempty


def _validate_nonce(nonce, files, binding):
    def raw(name):
        return files[nonce + "/" + name][0]

    def load(name):
        return _json(raw(name))

    request, claim = load("downloaded-request.json"), load("generation-claimed.json")
    response, ready, delivered = load("response.json"), load("response-ready.json"), load("delivered.json")
    request_sha, response_sha = hashlib.sha256(raw("downloaded-request.json")).hexdigest(), hashlib.sha256(raw("response.json")).hexdigest()
    identity = {"protocol": PROTOCOL, "nonce": nonce, "session_id": binding["session_id"], "model": binding["model"], "reasoning_effort": "max"}
    need(_identity(request, identity) and request.get("kind") == "source-proposal"
         and isinstance(request.get("mission_id"), str) and request["mission_id"], "Claim request belongs to another native cell")
    need(set(claim) == {"request_sha256", "claimed_at"} and claim["request_sha256"] == request_sha
         and _finite(claim["claimed_at"]), "Claim does not bind its exact downloaded request")
    need(_identity(response, identity) and response.get("request_sha256") == request_sha
         and response.get("infrastructure_error") is False, "Unsettled, foreign or technical response")
    need(set(ready) == {"sha256", "bytes"} and ready["sha256"] == response_sha
         and type(ready["bytes"]) is int and ready["bytes"] == len(raw("response.json")), "Response-ready digest/size differs")
    need(set(delivered) == BINDING_FIELDS | {"request_sha256", "response_sha256", "delivered_at"}
         and _identity(delivered, binding) and delivered["request_sha256"] == request_sha
         and delivered["response_sha256"] == response_sha and _finite(delivered["delivered_at"])
         and delivered["delivered_at"] >= claim["claimed_at"], "Claim lacks its exact cell-bound delivered response")
    invocation, process, diagnostics = load("invocation.json"), load("codex.jsonl.json"), load("cli-diagnostics.json")
    need(invocation.get("request_sha256") == request_sha and invocation.get("model") == binding["model"]
         and invocation.get("reasoning_effort") == "max" and invocation.get("source_execution_allowed") is False
         and type(invocation.get("argv")) is list and invocation["argv"]
         and process.get("argv") == invocation["argv"] and type(process.get("returncode")) is int
         and process["returncode"] == 0 and process.get("timed_out") is False, "CLI process was not settled successfully")
    events, tokens, nonempty = _usage_from_log(raw("codex.jsonl"))
    expected_diagnostics = {"schema": "hpc-forest-completed-cli-diagnostics-v1", "clean": True, "findings": [],
                            "counts": {}, "nonempty_lines_examined": nonempty, "raw_bytes": len(raw("codex.jsonl")),
                            "codex_jsonl_sha256": hashlib.sha256(raw("codex.jsonl")).hexdigest(), "raw_log_preserved": True,
                            "diagnostic_allowlist_or_suppression": False, "process_interrupted_by_this_check": False}
    need(_same(diagnostics, expected_diagnostics), "Completed CLI diagnostics do not match the clean preserved log")
    usage = response.get("usage")
    need(type(usage) is dict and usage.get("token_accounting") == "exact" and type(usage.get("tokens")) is int
         and usage["tokens"] == tokens and type(usage.get("llm_calls")) is int and usage["llm_calls"] == 1
         and usage.get("tool_events") == [] and usage.get("usage_parse_ambiguity") is False
         and _same(usage.get("events"), events) and usage.get("codex_jsonl_sha256") == hashlib.sha256(raw("codex.jsonl")).hexdigest()
         and usage.get("cli_diagnostics_sha256") == hashlib.sha256(raw("cli-diagnostics.json")).hexdigest()
         and type(usage.get("cli_diagnostic_count")) is int and usage["cli_diagnostic_count"] == 0,
         "Response usage is not exact or does not match the preserved CLI records")
    if nonce + "/request.json" in files:
        need(_same(load("request.json"), request), "CLI request differs from the claimed downloaded request")
    return tokens


def validate_cache(cache_root, binding, expected_nonces, *, no_redirects):
    """Return private minimal accounting and a hash inventory; never modify cache.

    ``no_redirects(Path)`` must reject redirected ancestors and may return a Path.
    Expected nonces must come from the caller's independently checked cold receipt.
    Negative algorithmic outcomes are allowed; no response ``data`` is examined.
    ``inventory`` is sorted by relative POSIX path and holds exactly
    ``{path, sha256, bytes}`` for each file. ``inventory_sha256`` hashes the UTF-8
    encoding of ``json.dumps(inventory, sort_keys=True, separators=(",", ":"))``.
    ``exact_tokens`` is an integer sum of every reconciled CLI turn's input and
    output tokens, including mother calls. Both snapshots retain bytes and stat
    identities privately, and neither raw records nor argv enter the result.
    """
    need(callable(no_redirects), "A redirect-checking callback is required")
    need(type(binding) is dict and set(binding) == BINDING_FIELDS and all(isinstance(value, str) and value for value in binding.values())
         and binding["effort"] == "max" and HEX32.fullmatch(binding["session_id"])
         and all(SHA.fullmatch(binding[key]) for key in BINDING_FIELDS if key.endswith("sha256")), "Exact native cell binding required")
    need(type(expected_nonces) in (list, tuple, set, frozenset) and all(isinstance(value, str) and HEX32.fullmatch(value) for value in expected_nonces)
         and len(expected_nonces) == len(set(expected_nonces)), "Exact unique expected native nonce collection required")
    root = Path(cache_root)
    need(root.is_absolute() and ".." not in root.parts, "Absolute physical cache root required")
    try:
        nonces, files = _snapshot(root, no_redirects)
        need(nonces == set(expected_nonces), "Cache nonce set differs from the cold terminal receipt")
        _validate_root(files, binding)
        tokens = sum(_validate_nonce(nonce, files, binding) for nonce in sorted(nonces))
        after_nonces, after_files = _snapshot(root, no_redirects)
        need(nonces == after_nonces and files == after_files, "Cache changed during validation")
    except OSError as exc:
        raise CacheError("Cache evidence cannot be read completely") from exc
    inventory = [{"path": name, "sha256": hashlib.sha256(value[0]).hexdigest(), "bytes": len(value[0])}
                 for name, value in sorted(files.items())]
    inventory_sha = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": "hpc-forest-matrix15-settled-worker-cache-check-v1", "session_id": binding["session_id"],
            "nonces": sorted(nonces), "claims_count": len(nonces), "exact_tokens": tokens,
            "inventory_sha256": inventory_sha, "inventory": inventory}
