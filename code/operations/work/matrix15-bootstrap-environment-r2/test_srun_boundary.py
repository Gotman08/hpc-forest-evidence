"""One neutral fake-srun test of the exact corrected command prefix; no ROMEO calls."""
from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "outputs/HPC-Forest-Matrice15-Bootstrap-Preparation-r1/materialisation-r2/job-body.sh"
NEW = ROOT / "outputs/HPC-Forest-Matrice15-Environnement-Preparation-r2/job-body-r2-02.sh"
BASH = Path("C:/Program Files/Git/bin/bash.exe")
EXPECTED = {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE",
            "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1"}


def observe(body):
    lines = [line for line in body.splitlines() if line.startswith("srun ")]
    assert len(lines) == 1
    command = shlex.split(lines[0])
    prefix = command[:command.index("timeout")]
    # The fake step deliberately corrupts five variables and removes the empty sixth.
    fake = """set -euo pipefail
srun() {
  while [[ "$1" == --* ]]; do shift; done
  export OMP_NUM_THREADS=BAD OMP_DYNAMIC=BAD OMP_PROC_BIND=BAD
  export PYTHONDONTWRITEBYTECODE=BAD OPENBLAS_NUM_THREADS=BAD
  unset CUDA_VISIBLE_DEVICES
  "$@"
}
"""
    receiver = "\n".join(f"printf '%s\\t%s\\t%s\\n' '{name}' \"${{{name}+present}}\" \"${{{name}-}}\""
                         for name in EXPECTED)
    script = fake + shlex.join([*prefix, "/bin/bash", "--noprofile", "--norc", "-c", receiver]) + "\n"
    result = subprocess.run([str(BASH), "--noprofile", "--norc", "-c", script],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    records = {}
    for line in result.stdout.splitlines():
        name, present, value = line.split("\t")
        assert name in EXPECTED and name not in records
        records[name] = value if present == "present" else None
    assert set(records) == set(EXPECTED)
    return records


def main():
    old, new = OLD.read_text(), NEW.read_text()
    before, after = observe(old), observe(new)
    assert before["CUDA_VISIBLE_DEVICES"] is None and before != EXPECTED
    assert after == EXPECTED
    syntax = subprocess.run([str(BASH), "-n", str(NEW)], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr
    old_tail = next(line for line in old.splitlines() if line.startswith("srun ")).split(" timeout ", 1)[1]
    new_tail = next(line for line in new.splitlines() if line.startswith("srun ")).split(" timeout ", 1)[1]
    assert old_tail == new_tail
    print(json.dumps({"schema": "hpc-forest-fake-srun-inline-environment-test-v1", "passed": True,
        "evidence_origin": "local-neutral-test", "fake_srun_rewrites_environment": True,
        "negative_control_original_wrapper": before, "corrected_wrapper_observed": after,
        "expected": EXPECTED, "bash_syntax_returncode": syntax.returncode,
        "timeout_python_input_and_flags_tail_unchanged": True,
        "jobs_submitted": 0, "native_model_calls": 0, "remote_transfers": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
