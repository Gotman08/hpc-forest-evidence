"""Bounded allocated wait for the exact post-submit R2 authorization upload; no CLI/socket."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hpc_forest.core import InfrastructureError, file_digest  # noqa: E402
from hpc_forest.native_r2max import (  # noqa: E402
    SCOPE,
    allocation_guard,
    deadline_guard,
    read_json,
    validate_receipt,
)


def await_authorization(path: Path, ready_path: Path, seconds: float, allocation: dict):
    if not 0 < seconds <= 600:
        raise InfrastructureError("Authorization wait must be bounded within 600 seconds")
    end = time.monotonic() + seconds
    while not ready_path.exists():
        if time.monotonic() >= end:
            raise InfrastructureError("Post-submit authorization upload did not arrive; no native call started")
        time.sleep(min(0.2, max(0, end - time.monotonic())))
    deadline_guard()
    ready = read_json(ready_path)
    if (ready.get("schema") != "hpc-forest-primes-r2max-authorization-upload-ready-v1"
            or ready.get("scope_id") != SCOPE
            or ready.get("job_id") != allocation["job_id"]
            or path.is_symlink() or not path.is_file()
            or ready.get("sha256") != file_digest(path)
            or ready.get("bytes") != path.stat().st_size):
        raise InfrastructureError("Invalid, partial or unrelated authorization upload")
    authorized = validate_receipt(path, {SCOPE}, prepared=True)
    if (authorized["job_id"] != allocation["job_id"]
            or ready.get("session_id") != authorized["session_id"]):
        raise InfrastructureError("Uploaded authorization names a different allocated job")
    return authorized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-ready", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=float, default=300)
    args = parser.parse_args()
    allocation = allocation_guard()
    authorization = await_authorization(args.authorization, args.authorization_ready,
                                        args.wait_seconds, allocation)
    if str(args.root) != authorization["remote_root"]:
        raise InfrastructureError("Post-submit root does not match its authorization")
    # Same interpreter, no child process or CLI; all gates run again in the native runner.
    from primes_native_max import main as run
    sys.argv = [sys.argv[0], "--root", str(args.root), "--authorization", str(args.authorization)]
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
