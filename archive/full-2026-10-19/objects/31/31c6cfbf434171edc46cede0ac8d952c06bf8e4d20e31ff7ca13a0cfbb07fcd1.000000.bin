from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import random
import socket
import statistics
import sys
import tempfile
import time
from pathlib import Path

from .core import (
    BudgetExhausted,
    FileLock,
    InfrastructureError,
    Outcome,
    atomic_json,
    digest,
    expand_command,
    file_digest,
    run_process,
    verify_protected,
)
from .gitops import ensure_clean, git
from .matrix15_provenance import command_stream_policy, observe_command


def target_identity(config: dict) -> dict:
    return {
        "target": config["target_id"],
        "hostname": socket.gethostname(),
        "system": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpus": os.cpu_count(),
        "python": sys.version,
        "python_executable": sys.executable,
        "compiler": config.get("compiler", {}),
        "dependencies": {
            name: importlib.metadata.version(name) for name in ["treequest", "numpy", "scipy"]
        },
        "controller_implementation": digest(
            {
                p.relative_to(Path(__file__).parent).as_posix(): file_digest(p)
                for p in sorted(Path(__file__).parent.rglob("*.py"))
            }
        ),
        "environment": config["protocol"]["environment"],
    }


class Evaluator:
    def __init__(self, root: Path, config: dict, manifest: dict, protocol_id: str, deadline: float):
        self.root, self.config = root, config
        self.protocol = config["protocol"]
        self.manifest, self.protocol_id, self.deadline = manifest, protocol_id, deadline
        command_stream_policy(config)
        # Same target string across campaigns -> same exclusive OS lock.
        self.lock_path = (
            Path(tempfile.gettempdir())
            / "hpc-forest-locks"
            / (digest(config["target_id"]) + ".lock")
        )

    def _timeout(self, build=False) -> float:
        limit = self.protocol["build_timeout_seconds" if build else "timeout_seconds"]
        return min(limit, self.deadline - time.time())

    def _variables(self, worktree: Path, build: Path, phase: str) -> dict:
        return {
            "python": sys.executable,
            "trusted": str(self.root / "trusted"),
            "worktree": str(worktree),
            "build": str(build),
            "binary": str(build / ("solution.exe" if os.name == "nt" else "solution")),
            "phase": phase,
        }

    def _run(self, name, variables, log, build=False):
        if command_stream_policy(self.config) is not None:
            return observe_command(
                config=self.config, protocol_id=self.protocol_id, operation=name,
                variables=variables, command=expand_command(self.protocol[name], **variables),
                log=log, timeout=lambda: self._timeout(build), run=run_process,
            )
        if self.protocol.get("private_execution_audit") is not True:
            return run_process(expand_command(self.protocol[name], **variables), Path(variables["worktree"]),
                               log, self._timeout(build), self.protocol["environment"])
        # All context/hash work is outside run_process's unchanged measured interval.
        command = expand_command(self.protocol[name], **variables)
        binary = Path(variables["binary"])
        context = {"schema": "hpc-forest-private-evaluation-context-v1", "never_model_input": True,
                   "execution_purpose": self.protocol.get("private_execution_purpose", "native-search"),
                   **{key: variables[key] for key in ("experiment_id", "epoch", "commit", "tree_hash", "phase")},
                   "protocol_id": self.protocol_id, "operation": name, "argv": command,
                   "worktree": variables["worktree"], "binary_path": str(binary),
                   "binary_sha256_before": file_digest(binary) if binary.is_file() else None,
                   "command_file_sha256": {arg: file_digest(Path(arg)) for arg in command
                                           if Path(arg).is_absolute() and Path(arg).is_file()}}
        contract = json.loads((self.root / "trusted/contract.json").read_text(encoding="utf8"))
        cases = ([contract["benchmark"]] if name == "benchmark" else
                 [*contract[variables["phase"]], contract["benchmark"]] if name == "check" else [])
        context["private_cases"] = [{"name": case["name"], "case_sha256": digest(case),
            "stdin_sha256": file_digest(self.root / "trusted" / case["stdin"]),
            "stdin_bytes": (self.root / "trusted" / case["stdin"]).stat().st_size} for case in cases]
        context_path = log.with_suffix(log.suffix + ".private-context.json")
        atomic_json(context_path, context)
        context_sha = file_digest(context_path)
        environment = dict(self.protocol["environment"])
        if name == "check":
            # Only the trusted checker receives the private pointer; it removes it for child C.
            environment.update(HPC_FOREST_PRIVATE_CONTEXT=str(context_path.resolve()),
                               HPC_FOREST_PRIVATE_CONTEXT_SHA256=context_sha)
        result = run_process(
            command,
            Path(variables["worktree"]),
            log,
            self._timeout(build),
            environment,
        )
        after = file_digest(binary) if binary.is_file() else None
        case_records = []
        if name == "check":
            for path in sorted((self.root / "private-audit/executions").glob("*/execution-provenance.json")):
                value = json.loads(path.read_text(encoding="utf8"))
                if (value.get("context") or {}).get("sha256") == context_sha:
                    case_records.append({"path": str(path), "sha256": file_digest(path)})
        valid = (file_digest(context_path) == context_sha
                 and (name == "build" or context["binary_sha256_before"] == after)
                 and (name != "check" or bool(case_records)))
        combined = {"path": str(log), "sha256": file_digest(log), "bytes": log.stat().st_size}
        proof = {**context, "schema": "hpc-forest-private-evaluation-execution-v2", "verified": valid,
                 "context": {"path": str(context_path), "sha256": context_sha},
                 "binary_sha256_after": after, "returncode": result.returncode, "timed_out": result.timed_out,
                 "measured_seconds": result.seconds, "hashing_outside_measured_interval": True,
                 "streams": {"combined_stdout_stderr": combined, "separate_stdout": None,
                             "separate_stderr": None, "layout": "original_run_process_combined_unchanged"},
                 "case_execution_records": case_records, "execution_semantics_changed": False}
        atomic_json(log.with_suffix(log.suffix + ".private-execution.json"), proof)
        if not valid:
            raise InfrastructureError("Private execution provenance incomplete or changed; no replay")
        return result

    def _prepare(self, experiment: str, epoch: int, worktree: Path, commit: str, phase: str,
                 *, warmups: bool = True):
        verify_protected(self.root / "trusted", self.manifest)
        ensure_clean(worktree, commit)
        tree_hash = git(worktree, "rev-parse", "HEAD^{tree}")
        cache_key = digest({"tree": tree_hash, "protocol": self.protocol_id, "epoch": epoch})
        outcome = Outcome("pending", commit=commit, tree_hash=tree_hash, cache_key=cache_key)
        history = self.root / "logs" / f"e{epoch}" / experiment / phase
        attempt = f"attempt-{len(list(history.glob('attempt-*'))) + 1:03d}"
        logs = history / attempt
        logs.mkdir(parents=True, exist_ok=False)
        build = self.root / "builds" / f"e{epoch}" / experiment / phase / attempt
        build.mkdir(parents=True, exist_ok=True)
        variables = self._variables(worktree, build, phase)
        variables.update(experiment_id=experiment, epoch=epoch, commit=commit, tree_hash=tree_hash)
        built = self._run("build", variables, logs / "build.log", build=True)
        outcome.logs.append(built.log)
        if built.returncode == 70:
            raise InfrastructureError("Compiler/toolchain unavailable; inspect build log")
        if built.returncode or built.timed_out:
            outcome.status, outcome.correct, outcome.score = "build_failed", False, 0.0
            outcome.reason = "Build failed or exceeded candidate timeout"
            return outcome, variables, logs
        if not Path(variables["binary"]).is_file():
            raise InfrastructureError("Successful build did not produce the contracted executable")
        outcome.binary_sha256 = file_digest(Path(variables["binary"]))
        checked = self._run("check", variables, logs / "correctness.log")
        outcome.logs.append(checked.log)
        if checked.returncode == 70:
            raise InfrastructureError("Correctness runner infrastructure failed")
        if checked.returncode or checked.timed_out:
            outcome.status, outcome.correct, outcome.score = "incorrect", False, 0.0
            outcome.reason = "Protected correctness checks failed"
            return outcome, variables, logs
        try:
            check_data = json.loads(Path(checked.log).read_text(encoding="utf-8"))
            valid = (
                check_data["correct"] is True
                and type(check_data["cases"]) is int
                and check_data["cases"] > 0
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InfrastructureError(
                "Checker must return JSON {correct: true, cases: positive-int}"
            ) from exc
        if not valid:
            outcome.status, outcome.correct, outcome.score = "incorrect", False, 0.0
            return outcome, variables, logs
        outcome.correct = True
        for i in range(self.protocol["warmups"] if warmups else 0):
            result = self._run("benchmark", variables, logs / f"warmup-{i}.log")
            outcome.logs.append(result.log)
            if result.returncode or result.timed_out:
                outcome.status, outcome.correct, outcome.score = "runtime_failed", False, 0.0
                return outcome, variables, logs
        return outcome, variables, logs

    def _sample(self, item, index: int) -> None:
        outcome, variables, logs = item
        if file_digest(Path(variables["binary"])) != outcome.binary_sha256:
            raise InfrastructureError("Executable changed after compilation")
        result = self._run("benchmark", variables, logs / f"sample-{index}.log")
        if file_digest(Path(variables["binary"])) != outcome.binary_sha256:
            raise InfrastructureError("Executable changed during benchmarking")
        outcome.logs.append(result.log)
        if result.returncode or result.timed_out:
            outcome.status, outcome.correct, outcome.score = "runtime_failed", False, 0.0
            outcome.times.clear()
        else:
            outcome.times.append(result.seconds)

    @staticmethod
    def _finalize(outcome: Outcome, baseline: float | None) -> Outcome:
        if outcome.correct is True and outcome.times:
            outcome.mean_seconds = statistics.mean(outcome.times)
            t0 = baseline if baseline is not None else outcome.mean_seconds
            outcome.score = 1.0 / (1.0 + outcome.mean_seconds / t0)
            outcome.status = "valid"
        return outcome

    def evaluate(
        self, experiment: str, epoch: int, worktree: Path, commit: str, baseline: float | None
    ) -> Outcome:
        with FileLock(self.lock_path):
            try:
                item = self._prepare(experiment, epoch, worktree, commit, "search")
                for i in range(self.protocol["repetitions"]):
                    if item[0].correct is not True:
                        break
                    self._sample(item, i)
                ensure_clean(worktree, commit)
                return self._finalize(item[0], baseline)
            finally:
                verify_protected(self.root / "trusted", self.manifest)

    def precheck(self, experiment: str, epoch: int, worktree: Path, commit: str) -> Outcome:
        """Development-only compile/check: no benchmark, holdout, cache, or tree reward."""
        lock = FileLock(self.lock_path)
        while True:
            try:
                lock.__enter__()
                break
            except InfrastructureError as exc:
                if not str(exc).startswith("Resource already locked:"):
                    raise
                if time.time() >= self.deadline:
                    raise BudgetExhausted("Development check expired waiting for target") from exc
                time.sleep(min(0.05, max(0, self.deadline - time.time())))
        try:
            outcome, _, _ = self._prepare(
                experiment, epoch, worktree, commit, "search", warmups=False)
            ensure_clean(worktree, commit)
            if outcome.correct:
                outcome.status = "development_valid"
            outcome.score = None
            return outcome
        finally:
            lock.__exit__(None, None, None)
            verify_protected(self.root / "trusted", self.manifest)

    def confirm(self, candidates: list[dict], epoch: int) -> dict[str, Outcome]:
        with FileLock(self.lock_path):
            items = {}
            try:
                for candidate in candidates:
                    items[candidate["id"]] = self._prepare(
                        candidate["id"],
                        epoch,
                        Path(candidate["worktree"]),
                        candidate["commit"],
                        "confirmation",
                    )
                # Fresh seeds in the correctness runner; timing samples alternate across finalists.
                rng = random.Random(self.config["seed"] + epoch)
                for repeat in range(self.protocol["confirmation_repetitions"]):
                    order = list(items)
                    rng.shuffle(order)
                    for key in order:
                        if items[key][0].correct is True:
                            self._sample(items[key], repeat)
                for candidate in candidates:
                    ensure_clean(Path(candidate["worktree"]), candidate["commit"])
                reference = next((items[c["id"]][0] for c in candidates if c.get("baseline")), None)
                t0 = statistics.mean(reference.times) if reference and reference.times else None
                return {key: self._finalize(item[0], t0) for key, item in items.items()}
            finally:
                verify_protected(self.root / "trusted", self.manifest)

    def serialize_identity(self) -> dict:
        return {
            "protocol_id": self.protocol_id,
            "target": target_identity(self.config),
            "protocol": self.protocol,
            "protected_files": self.manifest,
        }
