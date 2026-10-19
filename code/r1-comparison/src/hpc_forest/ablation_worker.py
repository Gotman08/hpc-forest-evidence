"""Owned resumable source-only comparison relay; never replay a claimed generation."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

from .codex_mailbox import bounded_json, sha256
from .codex_worker import RomeoFiles, Worker, validate_request
from .core import FileLock, InfrastructureError, atomic_json
from .harness_ablation import SCOPE, install_model_identity, verify_authorization


def verify_gate(receipt: Path, session: str):
    gate = verify_authorization(receipt, {SCOPE})
    if gate.get("session_id") != session or gate.get("arm") != "source-only":
        raise InfrastructureError("Wrong comparison session or source-only treatment")
    return gate


def verify_source(archive: Path, project: Path, expected_sha: str):
    if archive.is_symlink() or sha256(archive.read_bytes()) != expected_sha:
        raise InfrastructureError("The comparison-source-only source archive changed")
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith("HPC-Forest/"):
                raise InfrastructureError("Unexpected source archive root")
            target = project / info.filename.removeprefix("HPC-Forest/")
            if (not target.resolve().is_relative_to(project.resolve())
                    or target.is_symlink() or not target.is_file()
                    or target.read_bytes() != bundle.read(info)):
                raise InfrastructureError("Frozen comparison-source-only source mismatch")
            count += 1
    return count


def delivered_cache(output: Path, session: str):
    completed = set()
    for folder in output.iterdir():
        if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", folder.name):
            continue
        if not (folder / "delivered.json").exists():
            continue
        request_file = folder / "downloaded-request.json"
        request = bounded_json(request_file)
        validate_request(request, session, folder.name)
        digest = sha256(request_file.read_bytes())
        raw = (folder / "response.json").read_bytes()
        response = bounded_json(folder / "response.json")
        ready = bounded_json(folder / "response-ready.json")
        delivered = bounded_json(folder / "delivered.json")
        expected = {key: request[key] for key in
                    ("protocol", "nonce", "session_id", "model", "reasoning_effort")}
        expected["request_sha256"] = digest
        if (any(response.get(k) != v for k, v in expected.items())
                or delivered.get("request_sha256") != digest
                or delivered.get("response_sha256") != sha256(raw)
                or ready != {"sha256": sha256(raw), "bytes": len(raw)}):
            raise InfrastructureError("The delivered response cache changed")
        completed.add(folder.name)
    return completed


def event(output: Path, name: str, **values):
    with (output / "resume-events.jsonl").open("a", encoding="utf8") as stream:
        stream.write(json.dumps({"utc_epoch": time.time(), "event": name, **values}) + "\n")


async def serve(args):
    args.output.mkdir(parents=True, exist_ok=True)
    verify_gate(args.dependency_receipt, args.session_id)
    count = verify_source(args.source_zip, args.project, args.source_sha256)
    with FileLock(args.output / "worker.lock"):
        atomic_json(args.output / "resume-process-identity.json", {
            "pid": os.getpid(), "parent_pid": os.getppid(), "started_at": time.time(),
            "executable": sys.executable, "argv": sys.argv, "channel": args.channel,
            "session_id": args.session_id, "frozen_source_files_verified": count,
            "source_sha256": args.source_sha256, "resume": True,
        })
        end = time.monotonic() + args.max_seconds
        failures = 0
        while time.monotonic() < end:
            try:
                async with RomeoFiles(args.codex_config) as transfer:
                    worker = Worker(transfer, args.channel, args.session_id, args.output,
                                    args.dependency_receipt, {SCOPE})
                    worker.completed.update(delivered_cache(args.output, args.session_id))
                    await worker.hello()
                    event(args.output, "connection_ready", delivered_cache=len(worker.completed))
                    while time.monotonic() < end:
                        for name in sorted(await transfer.requests(args.channel)):
                            nonce = name.split(".")[0]
                            if nonce in worker.completed:
                                continue
                            verify_gate(args.dependency_receipt, args.session_id)
                            verify_source(args.source_zip, args.project, args.source_sha256)
                            cache = args.output / nonce
                            was_claimed = (cache / "generation-claimed.json").exists()
                            had_response = (cache / "response.json").exists()
                            if await worker.handle(name):
                                event(args.output, "request_delivered", nonce=nonce,
                                      was_claimed=was_claimed, had_response=had_response)
                        failures = 0
                        await asyncio.sleep(2)
            except Exception as exc:
                failures += 1
                event(args.output, "relay_failure", attempt=failures,
                      exception_type=type(exc).__name__, error=str(exc)[:2000])
                if failures >= 3:
                    raise
                await asyncio.sleep(min(30, max(0, end - time.monotonic())))
        event(args.output, "relay_maximum_reached")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex-config", type=Path, required=True)
    parser.add_argument("--dependency-receipt", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--max-seconds", type=int, default=72000)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    args = parser.parse_args()
    install_model_identity(args.model, args.effort, args.dependency_receipt)
    if not 1 <= args.max_seconds <= 72000:
        parser.error("The relay must remain within the twenty-hour allocation maximum")
    return asyncio.run(serve(args))


if __name__ == "__main__":
    raise SystemExit(main())
