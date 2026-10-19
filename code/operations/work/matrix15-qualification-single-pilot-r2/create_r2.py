"""Rebuild Q15 tools from unchanged r1 logic and the reviewed no-cycle parent."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
PREVIOUS = CURRENT / "work/matrix15-qualification-single-pilot-r1"
MANIFEST = CURRENT / "outputs/HPC-Forest-Matrice15-Admission-r2/RUNTIME-PRIVE-LOCAL.json"
PARENT = CURRENT / "work/matrix15-admission-no-cycle-r2/project"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


mapping = json.loads(MANIFEST.read_bytes())
canonical = (json.dumps(mapping, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
parent_sha = sha(canonical)
assert parent_sha == "73ef7751b10368d50f831af67aa7467b0bdb189252b5fa5df94c69f82896f152"
assert len(mapping) == 127
assert all(sha((PARENT / name).read_bytes()) == digest for name, digest in mapping.items())
for name in ("prepare.py", "qualification_contract.py", "qualify15.py", "test_qualification.py", "test_source_binding.py"):
    target = ROOT / name
    assert not target.exists()
    raw = (PREVIOUS / name).read_text(encoding="utf8")
    if name == "qualification_contract.py":
        old = "6d93e23b0930ecfa4d66251f4542a08b140b80351873da8248c154937c8c971b"
        assert raw.count(old) == 1
        raw = raw.replace(old, parent_sha)
    if name == "test_source_binding.py":
        raw = raw.replace("HPC-Forest-Matrice15-Pilote-Unique-r1/RUNTIME-PRIVE-LOCAL.json",
                          "HPC-Forest-Matrice15-Admission-r2/RUNTIME-PRIVE-LOCAL.json")
    with target.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(raw)
print(json.dumps({"parent_files": len(mapping), "parent_manifest_canonical_sha256": parent_sha,
                  "parent_manifest_file_sha256": sha(MANIFEST.read_bytes())}))
