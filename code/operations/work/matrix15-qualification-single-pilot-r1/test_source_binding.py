"""Neutral Q15 source-plan binding tests; no HPC runtime or baseline execution."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import qualification_contract as q


def neutral():
    parent, runtime = q.data({"NEUTRAL/source.py": "1" * 64}), q.data({"NEUTRAL/qualified.py": "2" * 64})
    binding = {"schema": "hpc-forest-Q15-single-pilot-source-binding-v1",
               "parent_runtime_manifest_sha256": q.sha(parent),
               "q_runtime_manifest_sha256": q.sha(runtime),
               "single_pilot_protocol_sha256": q.SINGLE_PILOT_PROTOCOL_SHA256}
    return {"source_bindings": binding}, parent, runtime


def test_neutral_binding_returns_detached_copy_without_hpc_imports():
    plan, parent, runtime = neutral()
    before = set(sys.modules)
    with patch.object(q, "PARENT_RUNTIME_MANIFEST_SHA256", q.sha(parent)):
        actual = q.verify_source_bindings(plan, parent, runtime)
    assert actual == plan["source_bindings"] and actual is not plan["source_bindings"]
    assert not any(name == "hpc_forest" or name.startswith("hpc_forest.") for name in set(sys.modules) - before)


@pytest.mark.parametrize("mutation", ["parent", "runtime", "protocol", "missing", "extra", "parent_bytes", "runtime_bytes"])
def test_wrong_source_plan_protocol_or_bytes_are_rejected(mutation):
    plan, parent, runtime = neutral()
    original_parent = parent
    plan = copy.deepcopy(plan)
    if mutation in {"parent", "runtime", "protocol"}:
        field = {"parent": "parent_runtime_manifest_sha256", "runtime": "q_runtime_manifest_sha256",
                 "protocol": "single_pilot_protocol_sha256"}[mutation]
        plan["source_bindings"][field] = "f" * 64
    elif mutation == "missing":
        plan.pop("source_bindings")
    elif mutation == "extra":
        plan["source_bindings"]["native_authorization"] = True
    elif mutation == "parent_bytes":
        parent += b" "
    else:
        runtime += b" "
    with patch.object(q, "PARENT_RUNTIME_MANIFEST_SHA256", q.sha(original_parent)), pytest.raises(q.Refusal):
        q.verify_source_bindings(plan, parent, runtime)


def test_parent_pin_matches_actual_reviewed_single_pilot_manifest():
    root = Path(__file__).resolve().parents[2]
    manifest = root / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1/RUNTIME-PRIVE-LOCAL.json"
    protocol = root / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1/PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"
    assert q.sha(q.data(json.loads(manifest.read_bytes()))) == q.PARENT_RUNTIME_MANIFEST_SHA256
    assert q.sha(protocol.read_bytes()) == q.SINGLE_PILOT_PROTOCOL_SHA256
