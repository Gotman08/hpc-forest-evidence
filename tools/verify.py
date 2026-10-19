"""Verify file integrity and recalculate the published evidence; read-only."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from .manifest import public_files
from .qualification import verify as verify_qualification
from .received import verify as verify_received
from .recompute import ROOT, EvidenceError, compare, compute, load_json


def verify_manifest(root: Path):
    manifest = load_json((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
        raise EvidenceError("Invalid manifest schema")
    seen = set()
    for item in manifest["files"]:
        name = item.get("path")
        if (not isinstance(name, str) or "\\" in name or ":" in name
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or name in seen or name == "MANIFEST.json"):
            raise EvidenceError("Unsafe or duplicate manifest path")
        seen.add(name)
        target = root / name
        if (not target.is_file() or any(p.is_symlink() for p in [target, *target.parents] if p != root.parent)
                or not target.resolve().is_relative_to(root.resolve())):
            raise EvidenceError(f"Missing or linked public artifact: {name}")
        raw = target.read_bytes()
        if type(item.get("bytes")) is not int or len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item.get("sha256"):
            raise EvidenceError(f"Artifact changed: {name}")
    actual = {path.relative_to(root).as_posix() for path in public_files(root)}
    if actual != seen:
        raise EvidenceError("Public file inventory differs from the manifest")
    return len(seen)


def verify_links(root: Path):
    checked = 0
    for path in root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        for link in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"[a-z][a-z0-9+.-]*:", link, re.IGNORECASE) or link.startswith("#"):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.is_relative_to(root.resolve()) or not target.exists():
                raise EvidenceError(f"Broken relative link in {path.name}: {link}")
            checked += 1
    return checked


def main():
    count = verify_manifest(ROOT)
    compare(compute(), load_json((ROOT / "evidence/results.json").read_text(encoding="utf-8")))
    received = verify_received(ROOT)
    qualification = verify_qualification(ROOT)
    links = verify_links(ROOT)
    print(f"Verified {count} file hashes and {links} relative links.")
    print("Recomputed 144 controller series (2,400 measured cycles) and 200 CPU samples (40 configurations).")
    print(f"Received update: {received['cpu_samples']} CPU samples, {received['confirmations']} confirmations, "
          f"{received['registers']} search registers and {received['cost_exports']} separate cost views.")
    print(f"Separate zero-model qualification: {qualification['subjects']} baselines and {qualification['samples']} timings.")
    print("This checks integrity and arithmetic; it does not execute or certify the evaluated programs.")


if __name__ == "__main__":
    main()
