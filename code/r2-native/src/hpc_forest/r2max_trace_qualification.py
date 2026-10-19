"""Future allocated real Evaluator check with unchanged official C; never a model run."""
from __future__ import annotations

import shutil
import time
from dataclasses import asdict
from pathlib import Path

from .core import InfrastructureError, atomic_json, digest, file_digest, protected_manifest
from .evaluator import Evaluator
from .gitops import initialize_source
from .native_r2max import allocation_guard
from .primes_contract import REFERENCE_SHA256
from .r2max_first_start import evaluation_provenance

PURPOSE = "qualification-only-not-model-official"


def qualify_trace(preparation, output, allocation):
    # Refuse locally before copying data, Git, compiler or executable work.
    observed = allocation_guard()
    if observed != allocation:
        raise InfrastructureError("Trace qualification allocation changed")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = Path(preparation["source"])
    if file_digest(source / "src/model-view/primetest.c") != REFERENCE_SHA256:
        raise InfrastructureError("Only the exact official C may exercise the qualifier")
    shutil.copytree(Path(preparation["validation"]), output / "trusted")
    worktree = output / "unchanged-official-source"
    # Same local provenance mechanism as Evaluator's normal clean-worktree contract.
    # It creates no public commit, remote, model proposal or new candidate source.
    commit = initialize_source(source, worktree)
    if file_digest(worktree / "src/model-view/primetest.c") != REFERENCE_SHA256:
        raise InfrastructureError("Official source changed during qualification snapshot")
    protocol = {"build": ["{python}", "{trusted}/contract_tool.py", "build", "{worktree}", "{build}"],
                "check": ["{python}", "{trusted}/contract_tool.py", "check", "{binary}", "{phase}"],
                "benchmark": ["/bin/sh", "{trusted}/benchmark.sh", "{binary}"],
                "repetitions": 3, "confirmation_repetitions": 5, "warmups": 1,
                "timeout_seconds": preparation["protocol_timeout_seconds"], "build_timeout_seconds": 120,
                "environment": {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE",
                                "CUDA_VISIBLE_DEVICES": ""},
                "private_execution_audit": True, "private_execution_purpose": PURPOSE}
    config = {"protocol": protocol, "seed": 23,
              "target_id": "romeo:slurm-" + allocation["job_id"] + ":official-r2max-trace-qualification"}
    manifest = protected_manifest(output / "trusted")
    instance = Evaluator(output, config, manifest, digest({"protocol": protocol, "manifest": manifest}),
                         time.time() + 600)
    search = instance.evaluate(PURPOSE, 1, worktree, commit, None)
    if search.status != "valid" or search.correct is not True or len(search.times) != 3:
        atomic_json(output / "search-negative.json", asdict(search))
        raise InfrastructureError("Official trace qualification search failed; preserve without retry")
    confirmed = instance.confirm([{"id": PURPOSE, "worktree": str(worktree), "commit": commit, "baseline": True}], 1)[PURPOSE]
    if confirmed.status != "valid" or confirmed.correct is not True or len(confirmed.times) != 5:
        atomic_json(output / "confirmation-negative.json", asdict(confirmed))
        raise InfrastructureError("Official trace qualification confirmations failed; preserve without retry")
    references = {"search": evaluation_provenance(asdict(search), PURPOSE),
                  "confirmation": evaluation_provenance(asdict(confirmed), PURPOSE, phase="confirmation")}
    receipt = {"schema": "hpc-forest-primes-r2max-official-evaluator-trace-qualification-v1", "verified": True,
               "execution_purpose": PURPOSE, "reference_source_sha256": REFERENCE_SHA256,
               "allocation": allocation, "official_source_commit": commit, "protocol": protocol,
               "protocol_id": instance.protocol_id, "private_execution_provenance": references,
               "search": asdict(search), "confirmation": asdict(confirmed),
               "native_model_calls": 0, "new_model_candidates": 0, "native_first_start_proved": False,
               "performance_research_result": False, "negative_preserved_no_retry": True}
    atomic_json(output / "trace-qualification.json", receipt)
    return receipt
