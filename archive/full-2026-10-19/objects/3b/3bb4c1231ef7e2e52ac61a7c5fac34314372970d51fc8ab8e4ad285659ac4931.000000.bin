"""Update only sealed package pins/count in the reviewed generic bootstrap."""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
PREVIOUS = CURRENT / "work/matrix15-qualification-single-pilot-r1"
PACKAGE = CURRENT / "outputs/HPC-Forest-Q15-Pilote-Unique-r2/paquet"
ARCHIVE = PACKAGE.parent / "HPC-Forest-Q15-baseline-source-r1.tar.gz"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


old = (PREVIOUS / "bootstrap_q15.py").read_text(encoding="utf8")
new = old
pins = {"ARCHIVE_SHA256": sha(ARCHIVE), "PLAN_SHA256": sha(PACKAGE / "PLAN-Q15.json"),
        "PACKAGE_MANIFEST_SHA256": sha(PACKAGE / "PACKAGE-MANIFEST.json"),
        "PARENT_RUNTIME_SHA256": sha(PACKAGE / "ORIGINAL-RUNTIME-MANIFEST.json"),
        "Q_RUNTIME_SHA256": sha(PACKAGE / "RUNTIME-Q-MANIFEST.json"),
        "RUNNER_SHA256": sha(PACKAGE / "qualify15.py"),
        "HELPER_SHA256": sha(PACKAGE / "qualification_contract.py")}
for name, digest in pins.items():
    new, count = re.subn(r'^' + name + r' = "[0-9a-f]{64}"$', name + ' = "' + digest + '"', new, flags=re.MULTILINE)
    assert count == 1
new = new.replace("MEMBER_COUNT = 353", "MEMBER_COUNT = 354")
old_functions = [ast.dump(node, include_attributes=False) for node in ast.parse(old).body if isinstance(node, ast.FunctionDef)]
new_functions = [ast.dump(node, include_attributes=False) for node in ast.parse(new).body if isinstance(node, ast.FunctionDef)]
assert old_functions == new_functions
with (ROOT / "bootstrap_q15.py").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(new)
tests = (PREVIOUS / "test_bootstrap_q15.py").read_text(encoding="utf8")
tests = tests.replace("HPC-Forest-Q15-Pilote-Unique-r1", "HPC-Forest-Q15-Pilote-Unique-r2")
tests = tests.replace("len(material) == 353", "len(material) == boot.MEMBER_COUNT")
with (ROOT / "test_bootstrap_q15.py").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(tests)
print(pins)
