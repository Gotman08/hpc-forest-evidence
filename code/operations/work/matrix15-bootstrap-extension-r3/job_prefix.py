"""Only the post-srun environment correction; pure prefix, no job or file emission.

The caller must first validate the real first-batch gate and the registered cell.
Append the already reviewed Python/bootstrap/input arguments without changing them.
"""
from __future__ import annotations

import shlex

SRUN = ("srun", "--nodes=1", "--ntasks=1", "--cpus-per-task=4", "--mem=16G", "--cpu-bind=cores")
ENVIRONMENT = ("OMP_NUM_THREADS=4", "OMP_DYNAMIC=FALSE", "OMP_PROC_BIND=TRUE", "CUDA_VISIBLE_DEVICES=",
               "PYTHONDONTWRITEBYTECODE=1", "OPENBLAS_NUM_THREADS=1")
TIMEOUT = ("timeout", "--signal=TERM", "--kill-after=10s", "3310s")


def argument_prefix():
    """Explicit assignments run inside the step, before timeout/Python, with zero GPU."""
    return [*SRUN, "env", *ENVIRONMENT, *TIMEOUT]


def shell_prefix():
    return shlex.join(argument_prefix())
