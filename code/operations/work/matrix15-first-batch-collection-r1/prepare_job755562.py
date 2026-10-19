"""Prepare only the known local/remote reference slots for job755562 reception."""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("collection_job_preparer", Path(__file__).with_name("collect_inputs.py"))
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
reader = helper.runtime()
admission = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/admission-windows-r2"
cache = BASE / "work/matrix15-first-operation-inputs-r1/9a681c2826854a4b885e94c5e6243f0a-worker-r2"
science = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-r2-9a681c2826854a4b885e94c5e6243f0a"
output = BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Collecte-Preparation-r1/job-755562-preparation-r1"
reader.need(not output.exists(), "New job preparation directory required")
windows_ref = reader.local_ref(admission / "authorization.json")
arm_stage_ref = reader.local_ref(admission / "arm-stage/authorization.json")
reader.need(windows_ref["sha256"] == "0a7613019780014730f2f82f7fdb8637fa6c5aba0646c410dcc3779ce3c2c2cb"
            and arm_stage_ref["sha256"] == "4fcbb19d5fc64747bf33d2c58b5efe6eb0de5ffa7e217d1d8a9d718bfd5a4acd",
            "Original host authorization pins changed")
windows = reader.parse(Path(windows_ref["path"]).read_bytes())
arm = reader.parse(Path(arm_stage_ref["path"]).read_bytes())
identity = {"job_id": "755562", "session_id": "9a681c2826854a4b885e94c5e6243f0a", "model": "gpt-6-luna",
            "effort": "max", "subject_id": "2020-quicksort", "remote_root": science}
reader.need(all(windows.get(k) == arm.get(k) == v for k, v in identity.items()), "Exact live job/model/MAX/session required")
policy_ref = reader.local_ref(admission / "cli-policy-9a681c2826854a4b885e94c5e6243f0a.json")
cli_ref = windows["artifacts"]["cli_identity"]
reader.need(reader.local_ref(cli_ref["path"])["sha256"] == cli_ref["sha256"], "Local CLI identity changed")
cli = reader.parse(Path(cli_ref["path"]).read_bytes())
reader.need(policy_ref["sha256"] == cli["task_cli_policy_sha256"], "Actual policy differs from admitted CLI identity")
files = []
for original in cli["files"].values():
    actual = reader.local_ref(original["path"])
    reader.need(actual["sha256"] == original["sha256"], "Actual local CLI file differs")
    files.append(actual)
reader.need(len(files) == 4, "Four actual local CLI files required")
binding_ref = reader.local_ref(cache / "CELL-BINDING.json")
binding = reader.parse(Path(binding_ref["path"]).read_bytes())
reader.need(all(binding.get(k) == v for k, v in identity.items()), "Actual worker cache binding differs")
requests = []
for path in sorted(cache.glob("*/downloaded-request.json")):
    item = reader.parse(reader.ordinary(path).read_bytes())
    reader.need(item.get("session_id") == identity["session_id"] and item.get("model") == "gpt-6-luna"
                and item.get("reasoning_effort") == "max", "Observed request belongs to another model/effort/session")
    requests.append({"reference": reader.local_ref(path), **{k: item.get(k) for k in
        ("nonce", "model", "reasoning_effort", "session_id", "kind", "meta_role", "mission_id")}})
template = {"schema": helper.SCHEMA, "mode": "PREPARE",
    "authorization": {"path": science + "-admission/authorization.json", "sha256": arm_stage_ref["sha256"]},
    "paused_snapshot": None, "catalog": [], "local_refs": files, "cache_root": str(cache), "policy_ref": policy_ref,
    "audit_output_directory": str(BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r1/production-job755562-r1"),
    "output_directory": str(output.parent / "job-755562-collection-r1")}
reader.need(not Path(template["output_directory"]).exists() and not Path(template["audit_output_directory"]).exists(),
            "Future collection/audit outputs must remain absent")
output.mkdir(parents=True, exist_ok=False)
template_ref = reader.write_exclusive(output / "INPUT-COLLECTE-PREPARE.json", template)
receipt = {"schema": "hpc-forest-matrix15-real-job-collection-template-prepared-v1", "verified": False,
    "prepared_only": True, "observed_local_metadata_at": time.time(), "identity": identity,
    "template": template_ref, "original_windows_authorization": windows_ref, "original_arm_stage_authorization": arm_stage_ref,
    "remote_authorization_claim_source": "ROOT reported admitted ARM ref; local staged bytes rehashed only",
    "remote_download_receipts_invented": False, "catalog_downloads": 0,
    "pending_snapshot_remote_path": science + "/results-755562/premier-batch-en-attente.json",
    "snapshot_sha256": None, "cache_binding": binding_ref, "requested_calls_observed": requests,
    "requested_effort_counts": {"gpt-6-luna/max": len(requests)}, "actual_token_usage_claimed": False,
    "completed_model_call_claimed": False, "collector_or_audit_invoked": False,
    "network_or_job_or_process_or_model_action": False, "current_files_modified": False}
ref = reader.write_exclusive(output / "PREPARATION-JOB755562.json", receipt)
print(ref["path"], ref["sha256"])
