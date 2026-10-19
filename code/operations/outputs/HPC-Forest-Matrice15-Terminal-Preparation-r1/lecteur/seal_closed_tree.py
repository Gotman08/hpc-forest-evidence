"""Read-only two-pass snapshot manifest. No engine/model/network imports.

The source must already be terminal. A manifest records stability during these
two reads, not a claim that no process can ever change the tree afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from pathlib import Path


def need(value, message):
    if not value:
        raise ValueError(message)


def signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def ordinary_path(path):
    need(path.is_absolute(), "Absolute path required")
    for part in [path, *path.parents]:
        info = part.lstat()
        need(not stat.S_ISLNK(info.st_mode) and not (hasattr(part, "is_junction") and part.is_junction()),
             "Symlink or junction ancestor refused")
    return path


def inventory(root, hash_files):
    result = {}
    stack = [root]
    while stack:
        directory = stack.pop()
        before = directory.lstat()
        need(stat.S_ISDIR(before.st_mode) and not (hasattr(directory, "is_junction") and directory.is_junction()),
             "Non-directory, junction or symlink encountered")
        names = sorted(directory.iterdir(), key=lambda item: item.name)
        result[directory.relative_to(root).as_posix()] = {"kind": "directory", "stat": signature(before),
                                                        "entries": [item.name for item in names]}
        for item in names:
            info = item.lstat()
            need(not (hasattr(item, "is_junction") and item.is_junction()), "Junction source entry refused")
            if stat.S_ISDIR(info.st_mode):
                stack.append(item)
            else:
                need(stat.S_ISREG(info.st_mode), "Symlink or special source file refused")
                record = {"kind": "file", "stat": signature(info), "bytes": info.st_size}
                if hash_files:
                    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                    descriptor = os.open(item, flags)
                    try:
                        opened = os.fstat(descriptor)
                        need(stat.S_ISREG(opened.st_mode) and signature(opened) == signature(info), "File raced before hashing")
                        digest = hashlib.sha256()
                        while chunk := os.read(descriptor, 1024 * 1024):
                            digest.update(chunk)
                        need(signature(os.fstat(descriptor)) == signature(opened), "File changed while hashing")
                    finally:
                        os.close(descriptor)
                    need(signature(item.lstat()) == signature(info), "File replaced after hashing")
                    record["sha256"] = digest.hexdigest()
                result[item.relative_to(root).as_posix()] = record
        need(signature(directory.lstat()) == signature(before), "Directory entries changed during walk")
    return result


def seal(root, output):
    root = ordinary_path(Path(root)).resolve(strict=True)
    output = Path(output)
    need(root.is_dir() and output.is_absolute() and not output.exists(), "Existing source and new absolute output directory required")
    ordinary_path(output.parent)
    output = output.parent.resolve(strict=True) / output.name
    need(not output.is_relative_to(root) and not root.is_relative_to(output), "Output must be outside source tree")
    output.mkdir()
    started = time.time()
    intent = {"schema": "hpc-forest-closed-tree-seal-intent-v1", "source_root": str(root), "output_root": str(output),
              "started_at": started, "model_calls": 0, "source_files_modified": False}
    write_new(output / "INTENT.json", intent)
    try:
        first = inventory(root, True)
        second = inventory(root, True)
        need(first == second, "Tree changed between complete hashing passes")
        files = {name: {"sha256": item["sha256"], "bytes": item["bytes"]}
                 for name, item in sorted(first.items()) if item["kind"] == "file"}
        need(bool(files), "Empty source tree refused")
        manifest = {"schema": "hpc-forest-closed-tree-files-v1", "source_root": str(root), "files": files,
                    "directories": sorted(name for name, item in first.items() if item["kind"] == "directory")}
        manifest_path = output / "FILES.json"
        write_new(manifest_path, manifest)
        receipt = {"schema": "hpc-forest-closed-tree-seal-v1", "tree_stability_verified": True,
                   "source_root": str(root), "started_at": started, "finished_at": time.time(), "passes": 2,
                   "files": len(files), "bytes": sum(item["bytes"] for item in files.values()),
                   "manifest": {"path": str(manifest_path), "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                                "bytes": manifest_path.stat().st_size},
                   "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "allocation": {"job_id": os.environ.get("SLURM_JOB_ID"), "hostname": os.uname().nodename if hasattr(os, "uname") else None},
                   "model_calls": 0, "source_files_modified": False, "all_raws_received": False,
                   "independent_performance_audit_verified": False}
        write_new(output / "RECEIPT.json", receipt)
        return receipt
    except BaseException as exc:
        write_new(output / "FAILURE.json", {**intent, "failed_at": time.time(), "error_type": type(exc).__name__, "error": str(exc)})
        raise


def write_new(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args(argv)
    if args.seal:
        seal(args.root, args.output)
    else:
        print(json.dumps({"prepared_only": True, "tree_stability_verified": False, "model_calls": 0,
                          "source_files_modified": False, "would_write_to": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
