"""Read tar members virtually. Never extract files or execute received source."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath


def need(test, message):
    if not test:
        raise ValueError(message)


def inspect(path, expected_sha, root, prefix):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected_sha, "Archive hash changed")
    need(root.startswith("/") and not root.endswith("/") and prefix and "/" not in prefix, "Explicit root/prefix required")
    files, json_files, dirs = {}, {}, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = archive.getmembers()
        need(0 < len(members) <= 100000, "Archive member count bound exceeded")
        total = 0
        seen, kinds = set(), {}
        for member in members:
            path = PurePosixPath(member.name)
            need(not path.is_absolute() and "\\" not in member.name and ":" not in member.name
                 and path.as_posix() == member.name and all(member.name.split("/"))
                 and all(part not in {".", ".."} for part in member.name.split("/"))
                 and path.parts[0] == prefix and member.name not in seen, "Unsafe, duplicate or unexpected archive member")
            seen.add(member.name)
            need(member.isfile() or member.isdir(), "Links and special archive members refused")
            kinds[member.name] = "directory" if member.isdir() else "file"
            if member.isdir():
                dirs.add(member.name)
                continue
            total += member.size
            need(0 <= member.size <= 512 * 1024 * 1024 and total <= 4 * 1024 * 1024 * 1024, "Expanded archive size bound exceeded")
            stream = archive.extractfile(member)
            need(stream is not None, "Missing regular archive stream")
            data = stream.read(member.size + 1)
            need(len(data) == member.size, "Archive member truncated")
            files[root + "/" + member.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            if member.name.endswith(".json") and len(data) <= 16 * 1024 * 1024:
                try:
                    json_files[root + "/" + member.name] = json.loads(data.decode("utf8"))
                except (ValueError, UnicodeError):
                    pass
        for name in seen:
            for parent in PurePosixPath(name).parents:
                need(kinds.get(parent.as_posix(), "directory") == "directory", "Archive file/directory collision")
    refs = {}

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
                ref = {"sha256": value["sha256"]}
                if "bytes" in value:
                    ref["bytes"] = value["bytes"]
                key = (value["path"], value["sha256"])
                refs[key] = ref
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for value in json_files.values():
        walk(value)
    missing, mismatches = [], []
    for (name, digest), ref in sorted(refs.items()):
        actual = files.get(name)
        if actual is None:
            missing.append({"path": name, **ref})
        elif actual["sha256"] != digest or ("bytes" in ref and ref["bytes"] != actual["bytes"]):
            mismatches.append({"path": name, "reference": ref, "archive": actual})
    return {"schema": "hpc-forest-matrix15-private-virtual-archive-inventory-v1", "archive_sha256": expected_sha,
            "source_root": root, "files": files, "directories": sorted(dirs), "referenced_artifacts": len(refs),
            "missing_references": missing, "mismatched_references": mismatches,
            "source_executed": False, "files_extracted": False, "independent_performance_audit_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    value = inspect(args.archive, args.sha256, args.root, args.prefix)
    need(args.output.is_absolute() and not args.output.exists(), "New absolute output file required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"files": len(value["files"]), "missing_refs": len(value["missing_references"]),
                      "mismatched_refs": len(value["mismatched_references"]), "source_executed": False}))


if __name__ == "__main__":
    raise SystemExit(main())
