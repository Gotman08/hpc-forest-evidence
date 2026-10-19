"""R2-specific worker adapter; inherited transport retains claim/no-replay behavior."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .core import InfrastructureError, atomic_json, file_digest
from .native_r2max import (
    EFFORT,
    SCOPE,
    artifact,
    bind_worker_cache,
    cell_binding,
    install_identity,
    read_json,
    selected_identity,
)


def check_technical_hold(output: Path, filename: str):
    """An existing technical hold permits only already-produced response retransmission."""
    if not re.fullmatch(r"[0-9a-f]{32}\.request\.json", filename):
        raise InfrastructureError("Unsafe request filename")
    if (output / "cli-technical-hold.json").exists():
        response = output / filename.split(".")[0] / "response.json"
        if not response.is_file() or response.is_symlink():
            raise InfrastructureError("Delivered technical failure holds all new R2e generations")


def preserve_delivered_technical_hold(output: Path, local: Path):
    """Latch only after delivery; never stop a process or reinterpret a model negative."""
    response_path = local / "response.json"
    response = read_json(response_path)
    if response.get("infrastructure_error") is not True:
        return
    delivered = read_json(local / "delivered.json")
    response_sha = file_digest(response_path)
    if delivered.get("response_sha256") != response_sha:
        raise InfrastructureError("Technical hold requires the fully delivered exact response")
    hold = output / "cli-technical-hold.json"
    if hold.exists():
        return
    value = {"schema": "hpc-forest-r2e-delivered-technical-hold-v1",
             "scope_id": SCOPE, "nonce": local.name, "created_at": time.time(),
             "response_sha256": response_sha,
             "delivered_sha256": file_digest(local / "delivered.json"),
             "new_generations_allowed": False, "byte_identical_retransmissions_only": True,
             "process_stop_or_retry": False, "model_algorithmic_negative_repaired": False}
    diagnostics = local / "cli-diagnostics.json"
    if diagnostics.is_file():
        value["cli_diagnostics_sha256"] = file_digest(diagnostics)
    descriptor = os.open(hold, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf8") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class LocalCliProjectionTransfers:
    """Only two exact metadata records are projected; stderr and responses stay raw."""
    def __init__(self, transfer, channel, policy_sha256):
        self.transfer, self.channel, self.policy_sha256 = transfer, channel, policy_sha256

    def __getattr__(self, name):
        return getattr(self.transfer, name)

    async def upload(self, local, remote):
        kinds = {"invocation.json": "invocation", "codex.jsonl.json": "process"}
        if local.name in kinds:
            nonce = local.parent.name
            if (not re.fullmatch(r"[0-9a-f]{32}", nonce)
                    or remote != self.channel + "/logs/" + nonce + "." + local.name):
                raise InfrastructureError("Private CLI metadata has an unexpected destination")
            from .codex_process import cli_metadata_projection
            projection = cli_metadata_projection(local, self.policy_sha256, kinds[local.name])
            projected = local.with_name(local.name + ".arm-projection.json")
            if projected.exists():
                if read_json(projected) != projection:
                    raise InfrastructureError("Existing CLI metadata projection differs; never overwrite it")
            else:
                atomic_json(projected, projection)
            return await self.transfer.upload(projected, remote)
        return await self.transfer.upload(local, remote)


def main():
    # Consume only adapter-owned options; the inherited parser still needs every
    # shared option and must reject any remaining unknown or misspelled argument.
    private_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    private_parser.add_argument("--cli-policy", required=True)
    private_parser.add_argument("--cli-policy-sha256", required=True)
    _, inherited_args = private_parser.parse_known_args()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dependency-receipt", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--required-jobs", nargs="+", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transport-smoke", action="store_true")
    parser.add_argument("--cli-policy", type=Path, required=True)
    parser.add_argument("--cli-policy-sha256", required=True)
    args, _ = parser.parse_known_args()
    authorization = install_identity(args.dependency_receipt, prepared=False)
    model, session = selected_identity(authorization)
    if args.session_id != session or set(args.required_jobs) != {SCOPE} or args.transport_smoke:
        raise InfrastructureError("Only the admitted normal fresh selected MAX worker is authorized")
    cli = read_json(artifact(authorization["artifacts"]["cli_identity"]))
    executable = Path(args.executable)
    if (not executable.is_absolute() or executable.is_symlink() or not executable.is_file()
            or str(executable.resolve()) != str(Path(cli.get("executable_path", "")).resolve())
            or file_digest(executable) != cli.get("executable_sha256")):
        raise InfrastructureError("Explicit immutable CLI identity changed before invocation")
    from . import codex_process
    if args.cli_policy_sha256 != cli.get("task_cli_policy_sha256"):
        raise InfrastructureError("Local CLI policy digest differs from the admitted identity")
    policy = codex_process.load_task_cli_policy(args.cli_policy, args.cli_policy_sha256,
                                               cell_binding(authorization), cli["executable_sha256"])
    codex_process.CLI_POLICY = policy
    expected_channel = (authorization["remote_root"] + "/results-" + authorization["job_id"] + "/mailbox")
    if args.channel != expected_channel:
        raise InfrastructureError("The R2 worker channel is not the exact owned job/session")
    # Bind before the inherited worker opens its lock or transport.
    bind_worker_cache(args.output, authorization)
    from . import codex_worker as worker

    def remote_gate(channel):
        if channel != expected_channel:
            raise InfrastructureError("R2 channel changed")
    worker.validate_remote_channel = remote_gate
    legacy_worker = worker.Worker

    class R2Worker(legacy_worker):
        def __init__(self, *positional, **keywords):
            super().__init__(*positional, **keywords)
            bind_worker_cache(self.output, authorization)
            self.transfer = LocalCliProjectionTransfers(self.transfer, self.channel, args.cli_policy_sha256)

        async def hello(self):
            # Validate version/auth before publishing readiness; no race with a rejected CLI.
            worker.check_dependencies(self.dependency_receipt, self.required_jobs)
            version = await asyncio.to_thread(subprocess.run, [str(executable), "--version"],
                                              capture_output=True, text=True, timeout=30, check=True)
            if version.stdout.strip() != cli.get("version"):
                raise InfrastructureError("CLI version differs from the admitted identity")
            auth = await asyncio.to_thread(subprocess.run, [str(executable), "login", "status"],
                                           capture_output=True, text=True, timeout=30, check=True)
            if "Logged in using ChatGPT" not in auth.stdout + auth.stderr:
                raise InfrastructureError("Existing local ChatGPT authentication required")
            self.executable = str(executable)
            await self.transfer.download(self.channel + "/OWNER.json", self.output / "OWNER.json")
            marker = worker.bounded_json(self.output / "OWNER.json", 4096)
            expected = {"protocol": worker.PROTOCOL, "session_id": session, "owner": authorization["job_id"],
                        "model": model, "reasoning_effort": EFFORT, **cell_binding(authorization)}
            if any(marker.get(k) != value for k, value in expected.items()):
                raise InfrastructureError("R2 owner differs from admitted worker")
            ready = {**expected, "scope_id": SCOPE, "mode": "codex", "pid": os.getpid(),
                     "started_at": time.time(), "local_python": sys.executable,
                     "codex_executable": str(executable), "codex_cli_version": version.stdout.strip(),
                     "codex_executable_sha256": file_digest(executable),
                     "authentication": "existing-local-ChatGPT", "weight_digest_available": False,
                     "model_weights_on_romeo": False,
                     "source_zip_sha256": authorization["artifacts"]["source_zip"]["sha256"],
                     "plan_sha256": authorization["artifacts"]["plan"]["sha256"]}
            ready.update(task_cli_policy_sha256=args.cli_policy_sha256,
                         task_cli_policy_candidate_count=len(policy["skill_candidate_directories"]),
                         local_skill_paths_exported=False)
            atomic_json(self.output / "worker-ready.json", ready)
            await self.transfer.upload(self.output / "worker-ready.json", self.channel + "/worker-ready.json")

        async def handle(self, filename):
            # Every generation goes through the exact session gate, including cached delivery.
            check_technical_hold(self.output, filename)
            worker.check_dependencies(self.dependency_receipt, self.required_jobs)
            bind_worker_cache(self.output, authorization)
            if file_digest(executable) != cli["executable_sha256"]:
                raise InfrastructureError("Immutable CLI bytes changed")
            done = await super().handle(filename)
            if done:
                nonce = filename.split(".")[0]
                local = self.output / nonce
                delivered = read_json(local / "delivered.json")
                delivered.update(scope_id=SCOPE, model=model, effort=EFFORT, session_id=session,
                                 job_id=authorization["job_id"],
                                 source_zip_sha256=authorization["artifacts"]["source_zip"]["sha256"],
                                 plan_sha256=authorization["artifacts"]["plan"]["sha256"])
                atomic_json(local / "delivered.json", delivered)
                preserve_delivered_technical_hold(self.output, local)
                for name in ("codex.jsonl.json", "delivered.json"):
                    if (local / name).is_file():
                        await self.transfer.upload(local / name, self.channel + f"/logs/{nonce}.{name}")
            return done

    # The source worker's request validator already uses the per-process selected constants.
    # Add session checking at run_codex as well because legacy authorization statuses differ.
    legacy_run = worker.run_codex

    def generate(request, request_sha, output, receipt, jobs, executable="codex"):
        if file_digest(args.cli_policy) != args.cli_policy_sha256:
            raise InfrastructureError("Local task CLI policy changed before generation")
        if (request.get("session_id") != session or request.get("kind") != "source-proposal"
                or request.get("model") != model or request.get("reasoning_effort") != EFFORT):
            raise InfrastructureError("Unrelated or smoke request forbidden in R2 native search")
        return legacy_run(request, request_sha, output, receipt, jobs, executable)
    worker.run_codex = generate
    worker.Worker = R2Worker
    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0], *inherited_args]
        return worker.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
