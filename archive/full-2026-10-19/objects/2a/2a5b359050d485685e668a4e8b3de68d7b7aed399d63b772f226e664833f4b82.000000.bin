"""Finalize evidence for the isolated private delta; no external or scientific run."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OUTPUT = CURRENT / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1"
PROJECT = ROOT / "project"
EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path)}


def write_json(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


baseline = json.loads((OUTPUT / "SOURCE-ORIGINALE-AVANT.json").read_text(encoding="utf8"))
source = Path(baseline["source"])
original_files = baseline["files"]
for name, digest in original_files.items():
    assert sha(source / name) == digest, name
for name, digest in baseline["historical_protocols_and_release"].items():
    assert sha(Path(name)) == digest, name
current = {p.relative_to(PROJECT).as_posix(): sha(p) for p in sorted(PROJECT.rglob("*"))
           if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(PROJECT).parts)}
assert set(original_files) <= set(current)
changed = [name for name, digest in current.items() if original_files.get(name) != digest]
patch = []
for name in changed:
    old = (source / name).read_text(encoding="utf8").splitlines(True) if name in original_files else []
    new = (PROJECT / name).read_text(encoding="utf8").splitlines(True)
    patch.extend(difflib.unified_diff(old, new, fromfile="a/" + name, tofile="b/" + name))
patch_path = ROOT / "single-pilot-final.patch"
with patch_path.open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(patch))
manifest = OUTPUT / "RUNTIME-PRIVE-LOCAL.json"
write_json(manifest, current)
tests = OUTPUT / "TESTS-NEUTRES-PILOTE-UNIQUE-FINAL.xml"
suite = ElementTree.parse(tests).getroot().find("testsuite")
assert suite is not None
counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
assert counts == {"tests": 317, "failures": 0, "errors": 0, "skipped": 0}
receipt = {
    "schema": "hpc-forest-matrix15-single-pilot-private-local-validation-v1",
    "protocol": ref(OUTPUT / "PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"),
    "cell_manifest": ref(OUTPUT / "MANIFESTE-60-CELLULES-NEUVES.json"),
    "private_project": str(PROJECT), "private_patch": ref(patch_path),
    "private_runtime_manifest": ref(manifest), "runtime_files": len(current),
    "modified_or_added_files": changed, "tests": {**counts, "junit": ref(tests)},
    "ruff": {"exit_code": 0, "result": "All checks passed!", "scope": "src tests --no-cache",
             "evidence_kind": "operator_attestation_of_actual_tool_result"},
    "original_source_files_rehashed_unchanged": len(original_files),
    "historical_protocols_and_release_rehashed_unchanged": baseline["historical_protocols_and_release"],
    "qualification_instructions": ref(OUTPUT / "REVISION-ET-QUALIFICATION.md"),
    "public_specification_only": ref(OUTPUT / "SPECIFICATION-PUBLIABLE.md"),
    "native_model_calls": 0, "jobs_submitted": 0, "transfers": 0,
    "active_chat_modified": False, "launch_ready": False,
    "subject_qualifications_and_receptions_still_required": True,
    "fresh_capacity_and_single_cell_admissions_still_required": True,
    "private_engine_publication_authorized": False,
}
write_json(OUTPUT / "REVISION-VALIDEE-LOCALEMENT.json", receipt)
print(json.dumps({"final_patch": ref(patch_path), "runtime_files": len(current), "tests": counts,
                  "original_source_files_unchanged": len(original_files)}))
