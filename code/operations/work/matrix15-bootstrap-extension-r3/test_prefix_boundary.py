"""Neutral fake-srun test; invokes only local Bash and prints six allowlisted variables."""
from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

from job_prefix import ENVIRONMENT, SRUN, TIMEOUT, argument_prefix, shell_prefix

BASH = Path("C:/Program Files/Git/bin/bash.exe")
EXPECTED = dict(item.split("=", 1) for item in ENVIRONMENT)


def observe(prefix):
    before_timeout = prefix[:prefix.index("timeout")]
    script = """set -euo pipefail
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
    script += shlex.join([*before_timeout, "/bin/bash", "--noprofile", "--norc", "-c", receiver]) + "\n"
    process = subprocess.run([str(BASH), "--noprofile", "--norc", "-c", script],
                             capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stderr
    rows = [line.split("\t") for line in process.stdout.splitlines()]
    assert len(rows) == 6 and {row[0] for row in rows} == set(EXPECTED)
    return {name: value if present == "present" else None for name, present, value in rows}


def main():
    prefix = argument_prefix()
    assert shlex.split(shell_prefix()) == prefix
    assert prefix == [*SRUN, "env", *ENVIRONMENT, *TIMEOUT]
    negative = observe([*SRUN, *TIMEOUT])
    positive = observe(prefix)
    assert negative["CUDA_VISIBLE_DEVICES"] is None and negative != EXPECTED
    assert positive == EXPECTED
    syntax = subprocess.run([str(BASH), "-n", "-c", shell_prefix() + " /bin/true"],
                            capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr
    print(json.dumps({"schema": "hpc-forest-extension-post-srun-env-prefix-neutral-test-v1", "passed": True,
        "fake_srun_rewrites_five_and_unsets_cuda": True, "negative_control": negative, "corrected_prefix": positive,
        "srun_resources_preserved": list(SRUN), "outer_timeout_preserved": list(TIMEOUT),
        "bash_syntax_returncode": syntax.returncode, "jobs_submitted": 0, "native_model_calls": 0,
        "transfers": 0, "operational_cell_commands_emitted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
