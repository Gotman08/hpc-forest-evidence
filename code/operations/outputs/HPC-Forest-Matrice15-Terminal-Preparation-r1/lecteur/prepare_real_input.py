"""Bind existing received evidence to a new input; never verify or launch it."""
import json
from pathlib import Path

from terminal_audit import INPUT_SCHEMA, local_ref

BASE = Path(__file__).resolve().parents[2]
EXECUTION = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01"
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Terminal-Preparation-r1"


def main():
    bootstrap = json.loads((EXECUTION / "terminal-received-r1/bootstrap.json").read_text(encoding="utf8"))
    binding = bootstrap["binding"]
    artifacts = {}
    for name, wave, local, raw in [("bootstrap", "r1", "bootstrap.json", "bootstrap.json"),
                                    ("results", "r1", "results.json", "results.json"),
                                    ("final_reconciliation", "r2", "reconciliation.json", "reconciliation.json"),
                                    ("confirmations", "r2", "confirmations.json", "confirmations.json")]:
        local_path = EXECUTION / ("terminal-received-" + wave) / local
        receipt_path = EXECUTION / ("terminal-raw-" + wave) / raw
        receipt = json.loads(receipt_path.read_text(encoding="utf8"))
        file_ref = local_ref(local_path)
        artifacts[name] = {"remote_ref": {"path": receipt["arguments"]["remote_path"], "sha256": file_ref["sha256"]},
                           "local_ref": file_ref, "transfer_receipt": local_ref(receipt_path)}
    value = {"schema": INPUT_SCHEMA, "binding": binding,
             "status_ref": local_ref(EXECUTION / "JOB-STATUS-r4-REEL.json"),
             "efficiency_ref": local_ref(EXECUTION / "JOB-755562-EFFICIENCY-TERMINAL-REEL.json"), "artifacts": artifacts,
             "first_batch_private_audit": local_ref(EXECUTION / "first-batch-audit-r2/AUDIT-PRIVE.json"),
             "first_batch_root_review": local_ref(EXECUTION / "extension-gate-r1/ROOT-REVIEW-REEL.json")}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "INPUT-TERMINAL-REEL-r1.json"
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print(json.dumps(local_ref(path)))


if __name__ == "__main__":
    main()
