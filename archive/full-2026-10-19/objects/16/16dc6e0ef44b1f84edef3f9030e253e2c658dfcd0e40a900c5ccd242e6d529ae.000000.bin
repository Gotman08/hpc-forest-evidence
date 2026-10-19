"""Package this standalone private producer; never create a production receipt."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("first_batch_preparer", HERE / "first_batch_audit.py")
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)

output = ROOT / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r1"
reader = output / "lecteur"
reader.mkdir(exist_ok=False)
copied = reader / "first_batch_audit.py"
copied.write_bytes((HERE / "first_batch_audit.py").read_bytes())
source_output = ROOT / "outputs/HPC-Forest-Matrice15-Admission-r2"
source = {"project_root": str(ROOT / "work/matrix15-admission-no-cycle-r2/project"),
          "source_zip": producer.local_ref(source_output / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"),
          "runtime_manifest": producer.local_ref(source_output / "RUNTIME-PRIVE-LOCAL.json")}
template = {"schema": producer.INPUT_SCHEMA, "evidence_origin": "prepared", "source": source,
            "authorization": None, "paused_snapshot": None, "received": [], "local_refs": [],
            "cache_root": None, "private_nonces": {}, "policy_ref": None,
            "output_directory": str(HERE / "PREPARE-DEFAULT-DEMO")}
template_ref = producer.write_exclusive(output / "INPUT-TEMPLATE-PREPARED.json", template)
tests_ref = producer.local_ref(HERE / "test_first_batch_audit.py")
report_ref = producer.local_ref(HERE / "TESTS-r6.xml")
producer.write_exclusive(output / "PREPARATION.json", {
    "schema": "hpc-forest-matrix15-first-batch-audit-delivery-prepared-v1", "verified": False,
    "evidence_origin": "prepared", "reader": producer.local_ref(copied), "source": source,
    "template": template_ref, "tests_source": tests_ref, "tests_report": report_ref,
    "tests_are_neutral_only": True, "production_invoked": False, "native_model_calls": 0,
    "network_or_CLI_or_jobs_called": False, "release_installed": False,
    "new_model_or_budget_authorized": False,
    "limitations": ["No real first-batch files received yet", "No independent frozen SQLite database audit",
                    "Command-stream evidence does not establish per-case provenance or independent speedup"]})
