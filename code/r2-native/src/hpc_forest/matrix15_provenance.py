"""Operator-only command observations for unchanged, non-instrumented R1 checkers.

This mode records the original combined process stream.  It cannot establish
individual-case output or an independent performance audit.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from pathlib import Path

from .core import (
    BudgetExhausted,
    ForestError,
    InfrastructureError,
    atomic_json,
    file_digest,
)
from .gitops import ensure_clean, git

MODE = "command-stream-v1"
CONTEXT_SCHEMA = "hpc-forest-matrix15-command-context-v1"
EXECUTION_SCHEMA = "hpc-forest-matrix15-command-execution-v1"
SCOPE = "hpc-forest-matrix15-native-max-r2"
MODELS = {"gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra"}
SUBJECTS = {
    "2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
    "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
    "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci",
}
POLICY_FIELDS = {
    "mode", "cell_binding", "source_runtime_sha256", "cell_contract_sha256",
    "protocol_plan_sha256",
}
CELL_FIELDS = {
    "scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
    "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256",
    "r1_contract_sha256",
}
HASH = re.compile(r"[a-f0-9]{64}")
GIT_HASH = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})")


def command_stream_policy(config: dict) -> dict | None:
    """Validate the exact optional operator policy without touching files/processes."""
    if type(config) is not dict:
        raise ForestError("Command-stream configuration must be an object")
    if "execution_provenance" not in config:
        return None
    policy = config["execution_provenance"]
    if type(policy) is not dict or set(policy) != POLICY_FIELDS or policy.get("mode") != MODE:
        raise ForestError("execution_provenance needs the exact command-stream-v1 policy")
    protocol = config.get("protocol", {})
    if type(protocol) is not dict or protocol.get("private_execution_audit", False) is not False:
        raise ForestError("command-stream-v1 is separate from private case-v2 auditing")
    cell = policy["cell_binding"]
    if type(cell) is not dict or set(cell) != CELL_FIELDS:
        raise ForestError("command-stream-v1 needs the exact twelve-field cell binding")
    if any(type(value) is not str or not value for value in cell.values()):
        raise ForestError("command-stream-v1 cell binding fields must be nonempty strings")
    if (cell["scope_id"] != SCOPE or cell["model"] not in MODELS or cell["effort"] != "max"
            or cell["subject_id"] not in SUBJECTS
            or cell["cell_key"] != f"forest-r2/{cell['model']}/max/{cell['subject_id']}/seed-23"
            or not re.fullmatch(r"[a-f0-9]{32}", cell["session_id"])
            or not re.fullmatch(r"[1-9][0-9]*", cell["job_id"])
            or not cell["remote_root"].startswith("/")
            or any(part in {".", ".."} for part in cell["remote_root"].split("/"))):
        raise ForestError("command-stream-v1 cell identity is invalid")
    for key in ("source_zip_sha256", "plan_sha256", "preparation_manifest_sha256",
                "r1_contract_sha256"):
        if not HASH.fullmatch(cell[key]):
            raise ForestError(f"command-stream-v1 cell {key} must be a SHA-256")
    for key in ("source_runtime_sha256", "cell_contract_sha256", "protocol_plan_sha256"):
        if type(policy[key]) is not str or not HASH.fullmatch(policy[key]):
            raise ForestError(f"execution_provenance.{key} must be a SHA-256")
    return copy.deepcopy(policy)


def provenance_path(log: Path) -> Path:
    return log.with_suffix(log.suffix + ".command-stream.json")


def _file(path: Path) -> dict:
    return {"path": str(path), "sha256": file_digest(path), "bytes": path.stat().st_size}


def _read_ref(ref: dict) -> dict:
    if (type(ref) is not dict or set(ref) != {"path", "sha256", "bytes"}
            or type(ref["path"]) is not str or type(ref["sha256"]) is not str
            or not HASH.fullmatch(ref["sha256"])
            or type(ref["bytes"]) is not int or ref["bytes"] < 0):
        raise InfrastructureError("Invalid command-stream file reference")
    path = Path(ref["path"])
    if not path.is_file() or _file(path) != ref:
        raise InfrastructureError("Command-stream file missing or changed")
    return ref


def _snapshot(worktree: Path, commit: str, tree_hash: str) -> dict:
    ensure_clean(worktree, commit)
    actual_tree = git(worktree, "rev-parse", "HEAD^{tree}")
    if actual_tree != tree_hash:
        raise InfrastructureError("Command-stream source tree changed; no replay")
    return {"commit": commit, "tree_hash": actual_tree, "clean": True}


def _argument_files(command: list[str], cwd: Path) -> list[dict]:
    files = []
    for index, argument in enumerate(command):
        path = Path(argument)
        if not path.is_absolute():
            path = cwd / path
        if path.is_file():
            files.append({"argument_index": index, "argument": argument, **_file(path)})
    return files


def _positive_timeout(timeout: Callable[[], float]) -> float:
    value = timeout()
    try:
        valid = type(value) in {float, int} and math.isfinite(value)
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise InfrastructureError("Invalid command-stream execution timeout")
    if value <= 0:
        raise BudgetExhausted("Wall-clock deadline reached before command observation")
    return value


def observe_command(*, config: dict, protocol_id: str, operation: str, variables: dict,
                    command: list[str], log: Path, timeout: Callable[[], float], run):
    """Wrap the original run_process call; all observations remain outside its timer."""
    policy = command_stream_policy(config)
    if policy is None:
        raise ForestError("Command-stream observation requires its explicit operator policy")
    _positive_timeout(timeout)  # Expired admission has no file/process effects.
    if (type(operation) is not str or operation not in {"build", "check", "benchmark"}
            or type(protocol_id) is not str
            or not HASH.fullmatch(protocol_id) or type(command) is not list or not command
            or any(type(arg) is not str for arg in command)):
        raise InfrastructureError("Invalid command-stream operation/protocol/argv")
    for key in ("experiment_id", "commit", "tree_hash", "worktree", "binary", "phase"):
        if type(variables.get(key)) is not str or not variables[key]:
            raise InfrastructureError(f"Missing command-stream variable: {key}")
    if (not GIT_HASH.fullmatch(variables["commit"])
            or not GIT_HASH.fullmatch(variables["tree_hash"])
            or type(variables.get("epoch")) is not int or variables["epoch"] < 1
            or variables["phase"] not in {"search", "confirmation"}):
        raise InfrastructureError("Invalid command-stream source/epoch/phase binding")
    environment = config["protocol"]["environment"]
    if (type(environment) is not dict
            or any(type(k) is not str or type(v) is not str for k, v in environment.items())):
        raise InfrastructureError("Command-stream environment must be the unchanged string map")
    cwd, binary = Path(variables["worktree"]), Path(variables["binary"])
    before = _snapshot(cwd, variables["commit"], variables["tree_hash"])
    binary_before = _file(binary) if binary.is_file() else None
    if operation != "build" and binary_before is None:
        raise InfrastructureError("Command-stream contracted binary is missing")
    argument_files_before = _argument_files(command, cwd)
    context = {
        "schema": CONTEXT_SCHEMA, "mode": MODE, "never_model_input": True,
        "operator_binding": policy, "protocol_id": protocol_id, "operation": operation,
        **{key: variables[key] for key in ("experiment_id", "epoch", "commit", "tree_hash", "phase")},
        "argv": list(command), "worktree": str(cwd), "binary_path": str(binary),
        "environment_overrides": copy.deepcopy(environment), "source_before": before,
        "binary_before": binary_before, "argument_files_before": argument_files_before,
        "stdin_layout": "original_run_process_DEVNULL_unchanged",
        "inherited_environment_captured": False,
    }
    context_path = log.with_suffix(log.suffix + ".command-context.json")
    if context_path.exists() or provenance_path(log).exists() or log.exists():
        raise InfrastructureError("Command-stream log/sidecar already exists; no replay")
    _positive_timeout(timeout)
    atomic_json(context_path, context)
    context_ref = _file(context_path)
    # Preserve argv, cwd, environment, process implementation, and measured interval.
    result = run(command, cwd, log, _positive_timeout(timeout), environment)
    after = _snapshot(cwd, variables["commit"], variables["tree_hash"])
    binary_after = _file(binary) if binary.is_file() else None
    argument_files_after = _argument_files(command, cwd)
    # A build may create/change its contracted output; other command files may not change.
    stable_arguments = [item for item in argument_files_before if item["path"] != str(binary)]
    stable_after = [item for item in argument_files_after if item["path"] != str(binary)]
    result_path = log.with_suffix(log.suffix + ".json")
    try:
        result_record = json.loads(result_path.read_text(encoding="utf-8"))
        result_ref = _file(result_path)
    except (OSError, ValueError) as exc:
        raise InfrastructureError("Original command process receipt is missing or malformed") from exc
    result_valid = (result.argv == command and type(result.returncode) is int and type(result.timed_out) is bool
                    and type(result.seconds) in {int, float} and math.isfinite(result.seconds)
                    and result.seconds >= 0 and result.log == str(log)
                    and result_record == {"argv": command, "returncode": result.returncode,
                                          "seconds": result.seconds, "timed_out": result.timed_out,
                                          "log": str(log)})
    verified = (result_valid and _file(context_path) == context_ref and before == after
                and stable_arguments == stable_after
                and (operation == "build" or binary_before == binary_after))
    proof = {
        **context, "schema": EXECUTION_SCHEMA, "verified": verified, "context": context_ref,
        "source_after": after, "binary_after": binary_after,
        "argument_files_after": argument_files_after, "returncode": result.returncode,
        "timed_out": result.timed_out, "measured_seconds": result.seconds,
        "original_process_result": result_ref,
        "hashing_outside_measured_interval": True, "execution_semantics_changed": False,
        "streams": {"combined_stdout_stderr": _file(log), "separate_stdout": None,
                    "separate_stderr": None, "layout": "original_run_process_combined_unchanged"},
        "case_execution_records": [], "individual_case_provenance_verified": False,
        "independent_raw_stdout_per_candidate_verified": False,
        "independent_performance_audit_verified": False,
    }
    atomic_json(provenance_path(log), proof)
    if not verified:
        raise InfrastructureError("Command-stream provenance incomplete or changed; no replay")
    return result


def command_stream_provenance(outcome: dict, experiment_id: str, *, expected_policy: dict,
                              protocol_id: str) -> list[dict]:
    """Coldly verify existing sidecars; never execute received code or infer case records."""
    policy = command_stream_policy({"execution_provenance": expected_policy, "protocol": {}})
    if (type(outcome) is not dict or type(outcome.get("logs")) is not list
            or not outcome["logs"] or type(experiment_id) is not str or not experiment_id
            or type(protocol_id) is not str or not HASH.fullmatch(protocol_id)
            or type(outcome.get("commit")) is not str or not GIT_HASH.fullmatch(outcome["commit"])
            or type(outcome.get("tree_hash")) is not str or not GIT_HASH.fullmatch(outcome["tree_hash"])
            or any(type(path) is not str for path in outcome["logs"])
            or len(outcome["logs"]) != len(set(outcome["logs"]))):
        raise InfrastructureError("Invalid command-stream outcome/protocol/log inventory")
    proofs = []
    for name in outcome["logs"]:
        log = Path(name)
        path = provenance_path(log)
        try:
            proof = json.loads(path.read_text(encoding="utf-8"))
            if type(proof) is not dict:
                raise InfrastructureError("Command-stream sidecar must be an object")
            context_ref = _read_ref(proof["context"])
            context = json.loads(Path(context_ref["path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise InfrastructureError("Missing or malformed command-stream sidecar") from exc
        if (type(proof) is not dict or proof.get("schema") != EXECUTION_SCHEMA
                or proof.get("mode") != MODE or proof.get("verified") is not True
                or proof.get("operator_binding") != policy or proof.get("protocol_id") != protocol_id
                or proof.get("experiment_id") != experiment_id
                or proof.get("commit") != outcome.get("commit")
                or proof.get("tree_hash") != outcome.get("tree_hash")
                or proof.get("source_before") != proof.get("source_after")
                or proof.get("hashing_outside_measured_interval") is not True
                or proof.get("execution_semantics_changed") is not False
                or proof.get("never_model_input") is not True
                or proof.get("case_execution_records") != []
                or any(proof.get(flag) is not False for flag in (
                    "individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified",
                    "independent_performance_audit_verified"))):
            raise InfrastructureError("Command-stream identity or declared evidence level changed")
        context_fields = {
            "schema", "mode", "never_model_input", "operator_binding", "protocol_id", "operation",
            "experiment_id", "epoch", "commit", "tree_hash", "phase", "argv", "worktree",
            "binary_path", "environment_overrides", "source_before", "binary_before",
            "argument_files_before", "stdin_layout", "inherited_environment_captured",
        }
        execution_fields = context_fields | {
            "verified", "context", "source_after", "binary_after", "argument_files_after", "returncode",
            "timed_out", "measured_seconds", "original_process_result", "hashing_outside_measured_interval",
            "execution_semantics_changed", "streams", "case_execution_records",
            "individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified",
            "independent_performance_audit_verified",
        }
        if (type(context) is not dict or set(context) != context_fields
                or context.get("schema") != CONTEXT_SCHEMA or set(proof) != execution_fields):
            raise InfrastructureError("Invalid command-stream context schema")
        if any(proof.get(key) != value for key, value in context.items() if key != "schema"):
            raise InfrastructureError("Command-stream execution/context mismatch")
        if (type(context["operation"]) is not str
                or context["operation"] not in {"build", "check", "benchmark"}
                or type(context["phase"]) is not str or context["phase"] not in {"search", "confirmation"}
                or type(context["epoch"]) is not int or context["epoch"] < 1
                or not GIT_HASH.fullmatch(context["commit"])
                or not GIT_HASH.fullmatch(context["tree_hash"])
                or context["source_before"] != {
                    "commit": context["commit"], "tree_hash": context["tree_hash"], "clean": True}
                or context["source_before"].get("clean") is not True
                or context["stdin_layout"] != "original_run_process_DEVNULL_unchanged"
                or context["inherited_environment_captured"] is not False
                or any(type(context[key]) is not str or not context[key]
                       for key in ("worktree", "binary_path"))
                or type(context["argv"]) is not list or not context["argv"]
                or any(type(arg) is not str for arg in context["argv"])
                or type(context["environment_overrides"]) is not dict
                or any(type(k) is not str or type(v) is not str
                       for k, v in context["environment_overrides"].items())):
            raise InfrastructureError("Command-stream command/source context is invalid")
        before_files, after_files = context["argument_files_before"], proof["argument_files_after"]
        if type(before_files) is not list or type(after_files) is not list:
            raise InfrastructureError("Command-stream argument file inventory is invalid")
        for item in [*before_files, *after_files]:
            if (type(item) is not dict or set(item) != {
                    "argument_index", "argument", "path", "sha256", "bytes"}
                    or type(item["argument_index"]) is not int
                    or not 0 <= item["argument_index"] < len(context["argv"])
                    or item["argument"] != context["argv"][item["argument_index"]]
                    or type(item["path"]) is not str or type(item["sha256"]) is not str
                    or not HASH.fullmatch(item["sha256"])
                    or type(item["bytes"]) is not int or item["bytes"] < 0):
                raise InfrastructureError("Command-stream argument file reference is invalid")
        if ([item for item in before_files if item["path"] != context["binary_path"]]
                != [item for item in after_files if item["path"] != context["binary_path"]]
                or (context["operation"] != "build" and (
                    context["binary_before"] is None
                    or context["binary_before"] != proof["binary_after"]))):
            raise InfrastructureError("Command-stream binary or command input changed")
        streams = proof.get("streams")
        if (type(streams) is not dict or set(streams) != {
                "combined_stdout_stderr", "separate_stdout", "separate_stderr", "layout"}
                or streams["separate_stdout"] is not None or streams["separate_stderr"] is not None
                or streams["layout"] != "original_run_process_combined_unchanged"
                or type(streams["combined_stdout_stderr"]) is not dict
                or streams["combined_stdout_stderr"].get("path") != str(log)):
            raise InfrastructureError("Command-stream stream layout changed")
        _read_ref(streams["combined_stdout_stderr"])
        process_ref = _read_ref(proof["original_process_result"])
        try:
            process = json.loads(Path(process_ref["path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InfrastructureError("Command-stream original process receipt is invalid") from exc
        if (process_ref["path"] != str(log.with_suffix(log.suffix + ".json"))
                or type(proof["returncode"]) is not int or type(proof["timed_out"]) is not bool
                or type(proof["measured_seconds"]) not in {int, float}
                or not math.isfinite(proof["measured_seconds"]) or proof["measured_seconds"] < 0
                or process != {"argv": context["argv"], "returncode": proof["returncode"],
                               "seconds": proof["measured_seconds"], "timed_out": proof["timed_out"],
                               "log": str(log)}):
            raise InfrastructureError("Command-stream original return or timing receipt changed")
        proofs.append({"path": str(path), "sha256": file_digest(path), "bytes": path.stat().st_size,
                       "mode": MODE, "operation": proof["operation"], "verified": True,
                       "individual_case_provenance_verified": False,
                       "independent_performance_audit_verified": False})
    return proofs
