"""Capture file-only pinned runtime provenance; never invoke an executable."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = Path("C:/Users/nicol/Documents/Codex/2026-10-15/cr/work/.venv")
BASE = Path("C:/Users/nicol/AppData/Local/Programs/Python/Python313")
PINS = {"launcher": (VENV / "Scripts/python.exe", "819c07dbf55c179f77a71d6f041c74c57b18d86f637f5f5e76ea882a50c9ed8b"),
        "base_python": (BASE / "python.exe", "5ef72c30ca3b82df7c7e186c9220bde665be9a335edbd4a371a4b19d0ac76644"),
        "pyvenv_cfg": (VENV / "pyvenv.cfg", "052c380114af39f78106c6828e87029bb47232adea03763316076e4eaa2ee327")}


def main():
    refs = {}
    for key, (path, pin) in PINS.items():
        if not path.is_file() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError("Ordinary observed runtime files required")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != pin:
            raise ValueError("Observed runtime bytes changed")
        refs[key] = {"path": str(path.resolve()), "sha256": checksum}
    value = {"schema": "hpc-forest-windows-venv-interpreter-pair-v1", "venv_root": str(VENV.resolve()),
        **refs, "home": str(BASE.resolve()), "executable": str((BASE / "python.exe").resolve()), "version": "3.13.4"}
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    destination = ROOT / "VENV-RUNTIME-IDENTITY.json"
    with os.fdopen(os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as target:
        target.write(raw)
    print(json.dumps({"path": str(destination), "sha256": hashlib.sha256(raw).hexdigest()}))


if __name__ == "__main__":
    main()
