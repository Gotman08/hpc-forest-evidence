"""Prepare r2 producer code; final generation refuses until the real Q list exists."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT.parents[1]
OLD = CURRENT / "work/matrix15-static-operation-r1"

text = (OLD / "produce_static.py").read_text(encoding="utf8")
text = text.replace("HPC-Forest-Matrice15-Operation-Preparation-r1", "HPC-Forest-Matrice15-Operation-Preparation-r2")
old = "def main():\n    if OUTPUT.exists():"
assert old in text
text = text.replace(old, 'def main():\n'
    '    sys.path.insert(0, str(Path(__file__).resolve().parent))\n'
    '    from q_upstream import read_spec\n'
    '    upstream_rows = read_spec(Path(__file__).with_name("Q-UPSTREAM-FILES.json"))\n'
    '    if OUTPUT.exists():')
old = '    aliases = {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": contract.SCOPE,'
assert old in text
text = text.replace(old,
    '    upstream_local_rows = []\n'
    '    for number, row in enumerate(upstream_rows, 1):\n'
    '        relative = "evidence/q15-upstream/" + str(number).zfill(2) + "-" + Path(row["reference"]["path"]).name\n'
    '        bound = copy_file(row["reference"]["path"], relative,\n'
    '            canonical=row["reference"]["path"], arm=row["arm_path"], expected=row["reference"]["sha256"])\n'
    '        upstream_local_rows.append({"role": row["role"], "reference": bound,\n'
    '            "windows_path": str(shared / relative), "arm_path": row["arm_path"]})\n'
    + old)
old = '    if inventory(PARENT) != original_runtime or checked(original_preparation_file) != original_preparation_raw:'
assert old in text
text = text.replace(old,
    '    for row in upstream_rows:\n'
    '        checked(row["reference"]["path"], row["reference"]["sha256"])\n'
    '    write_json(OUTPUT / "UPSTREAM-Q-ALIASES.json", {\n'
    '        "schema": "hpc-forest-matrix15-real-Q-upstream-static-aliases-v1",\n'
    '        "qualification_job_id": "755488", "files": upstream_local_rows,\n'
    '        "native_final_qualification_reception_and_admissions_included": False,\n'
    '        "qualification_admissibility_claimed_by_static_copy": False})\n'
    + old)
target = ROOT / "produce_static.py"
with target.open("x", encoding="utf8", newline="\n") as stream:
    stream.write(text)
tests = (OLD / "test_static_operation.py").read_text(encoding="utf8")
with (ROOT / "test_static_operation.py").open("x", encoding="utf8", newline="\n") as stream:
    stream.write(tests)
print("Producer r2 prepared; no Q-UPSTREAM-FILES.json supplied and no output generated")
