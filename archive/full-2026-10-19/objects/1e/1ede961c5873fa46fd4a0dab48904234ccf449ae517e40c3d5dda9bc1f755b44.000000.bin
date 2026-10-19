"""Explicitly rebuild the public bundle manifest after reviewing changed bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

IGNORED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "local-runs"}


def public_files(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file() and p != root / "MANIFEST.json"
                  and not any(part in IGNORED_PARTS for part in p.relative_to(root).parts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", required=True,
                        help="Acknowledge that the new file projection was reviewed")
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = []
    for path in public_files(root):
        if path.is_symlink():
            raise ValueError("Linked artifacts are not admitted to a release")
        raw = path.read_bytes()
        files.append({"path": path.relative_to(root).as_posix(), "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()})
    (root / "MANIFEST.json").write_text(json.dumps({"schema": 1, "algorithm": "sha256", "files": files},
                                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Recorded {len(files)} reviewed files. Re-run verification before committing.")


if __name__ == "__main__":
    main()
