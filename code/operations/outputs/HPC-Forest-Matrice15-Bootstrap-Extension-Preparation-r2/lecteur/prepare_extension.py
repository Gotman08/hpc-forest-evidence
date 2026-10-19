"""Prepared-only extension inventory. There is deliberately no operational emit switch."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_extension as ext


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    b = ext.load_helper(Path(__file__).with_name("sealed-bootstrap-helper.py").absolute())
    raw = b.regular_bytes(args.plan.resolve(strict=True))
    plan = b.read_json(raw)
    records = []
    for cell in plan["cells"]:
        _plan, binding = ext.registered_selection(b, raw, cell["cell_key"])
        records.append(binding)
    output = args.output.absolute()
    b.need(b.absent(output), "Preparation output exists; preserve and choose a fresh destination")
    output.mkdir(parents=True, exist_ok=False)
    b.save(output / "PREPARATION.json", {"schema": "hpc-forest-matrix15-bootstrap-extension-prepared-v1",
           "verified": False, "evidence_origin": "prepared", "native_authorization": False,
           "jobs_submitted": 0, "native_model_calls": 0, "automatic_extension": False,
           "first_batch_gate": None, "first_batch_actually_received_and_released": False,
           "plan_sha256": ext.PLAN_SHA, "source_zip_sha256": b.SOURCE_SHA256,
           "shared_reuse_only": True, "shared_expected_files": 375, "registered_cells": records,
           "operational_files_emitted": False})
    b.save(output / "INPUT-TEMPLATE-PREPARED.json", ext.build_cell_input(b, raw, records[0]["cell_key"], None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
