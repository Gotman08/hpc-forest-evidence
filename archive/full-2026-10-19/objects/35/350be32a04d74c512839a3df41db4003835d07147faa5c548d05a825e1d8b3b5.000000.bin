"""Materialize three registered cells locally; no admission or remote action."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Unit-Operation-Preparation-r2"
WORK = BASE / "work/matrix15-extension-operation-inputs-r1"
UNIT = BASE / "work/matrix15-unit-operation-r2/materialize_unit.py"
BUILDER = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1/build_inputs.py"
PRIOR = BASE / "outputs/HPC-Forest-Matrice15-Extension-Gate-Packet-r1/finalisation-r3/PREREQUISITES.json"
PINS = {UNIT: "9eab974b5d408cd4e0b269d2a0bdb2b483761b6702d384c038227c074fda57d4",
        BUILDER: "4d26cdab42a7b47cc8d326fbd638e9f44fbe404dbcac40ad64cf7dba42dd99d1",
        PRIOR: "0f48eb59a1ff807223fff605b887f70fb5d47b82b4b6146a95fbe7d9fa2f4931"}
CELLS = (("luna-count", "forest-r2/gpt-6-luna/max/2023-count/seed-23"),
         ("terra-count", "forest-r2/gpt-5.6-terra/max/2023-count/seed-23"),
         ("sol-tropical", "forest-r2/gpt-6.1-sol/max/2020-tropical/seed-23"))
BASH = Path("C:/Program Files/Git/bin/bash.exe")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write(path, value):
    with Path(path).open("x", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def call(argv, cwd=None):
    result = subprocess.run([str(v) for v in argv], cwd=cwd, capture_output=True, text=True,
                            encoding="utf8", timeout=60, check=False)
    need(result.returncode == 0, result.stderr or result.stdout or str(argv))
    return {"argv": [str(v) for v in argv], "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def main():
    need(all(ref(path)["sha256"] == sha for path, sha in PINS.items()), "Locked producer or prerequisite changed")
    for slug, _cell in CELLS:
        need(not (OUTPUT / (slug + "-materialisation-r1")).exists(), "Unit output already exists")
        need(not (WORK / (slug + "-prepare-r1")).exists(), "Generic output already exists")
    commands = []
    for slug, cell in CELLS:
        shared = ["--cell-key", cell, "--prerequisites", PRIOR, "--prerequisites-sha256", PINS[PRIOR]]
        commands.append(call([sys.executable, "-I", "-B", UNIT, "--output",
                              OUTPUT / (slug + "-materialisation-r1"), *shared]))
        commands.append(call([sys.executable, "-I", "-B", BUILDER, "prepare", "--output",
                              WORK / (slug + "-prepare-r1"), *shared]))
    write(HERE / "COMMANDES-REELLES.json", commands)
    spec = importlib.util.spec_from_file_location("reviewed_unit_r2", UNIT)
    unit = importlib.util.module_from_spec(spec)
    exec(compile(UNIT.read_bytes(), str(UNIT), "exec", dont_inherit=True), unit.__dict__)
    builder, _upstream, reader, dynamic, _capacity, bootstrap, prefix = unit.runtime()
    refs, _plan, _aliases = dynamic.static_inputs(unit.ref(builder.STATICS / "STATICS.json"))
    arm = read(builder.STATICS / "STATIC-ARTIFACTS-ARM.json")
    bridge = read(BASE / "outputs/HPC-Forest-Q15-Pont-Natif-r1/production-r3/BRIDGE-REPORT.json")
    prior = read(PRIOR)
    evidence = dynamic.received_evidence(prior["first_batch_received_evidence"])
    helper = bootstrap.load_helper((builder.BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    rows = []
    for slug, cell in CELLS:
        out = OUTPUT / (slug + "-materialisation-r1")
        generic = WORK / (slug + "-prepare-r1")
        prep = read(out / "PREPARATION.json")
        prepared = read(generic / "PREPARED.json")
        inputs = read(out / "stage/INPUT-BOOTSTRAP.json")
        generic_inputs = read(generic / "INPUT-BOOTSTRAP.json")
        binding = inputs["binding_without_job_id"]
        need(binding == prep["binding_without_job_id"] == prepared["binding_without_job_id"], "Binding mismatch")
        need(binding["cell_key"] == cell and binding["session_id"] != unit.NEXT_SESSION, "Wrong registered selection")
        need(prep["native_authorization"] is False and prep["jobs_submitted"] == prep["native_model_calls"] == 0,
             "Preparation promoted to an action")
        need(prepared["commands_to_execute"] == [] and prepared["native_execution_authorized"] is False,
             "Generic preparation authorizes execution")
        gate = inputs["first_batch_gate"]
        need(set(gate) == {"path", "sha256", "bytes"} and gate["bytes"] == 3119, "Real sized REF3 required")
        need(len(helper.read_ref({**gate, "path": str(evidence.resolve(prior["gate_arm"]))})) == 3119,
             "Serialized REF3 cannot cross sealed read_ref")
        normalized = json.loads(json.dumps(inputs))
        normalized["first_batch_gate"].pop("bytes")
        need(normalized == generic_inputs, "Generic and actual staged inputs differ beyond sized gate")
        upload = read(out / "UPLOAD-MANIFEST.json")
        need(upload["uploaded"] is False and upload["shared_reuse_only"] is True
             and upload["expected_shared_files"] == 375 and len(upload["members"]) == 3, "Wrong upload scope")
        for entry in upload["members"]:
            actual = ref(entry["local"]["path"])
            need(actual == entry["local"] and entry["remote"]["sha256"] == actual["sha256"], "Stage pin differs")
        body = (out / "job-body.sh").read_bytes()
        args = read(out / "JOB-PREPARE-ARGS.json")
        expected = unit.body(inputs, ref(out / "stage/INPUT-BOOTSTRAP.json")["sha256"], upload["remote_stage"],
                             ref(out / "stage/bootstrap_extension.py")["sha256"],
                             ref(out / "stage/extension_gate.py")["sha256"], prefix)
        need(body == expected and args["command"].encode("utf8") == body, "Job body differs from pinned producer")
        need((args["nodes"], args["cpus_per_task"], args["mem_gb"], args["gpus_per_node"], args["time_limit"])
             == (1, 4, 16, 0, "01:00:00"), "Resource contract changed")
        syntax = call([BASH, "-n", (out / "job-body.sh").as_posix()])
        line = next(line for line in body.decode("utf8").splitlines() if line.startswith("printf "))
        checksum = call([BASH, "-c", line], cwd=out / "stage")
        need(checksum["stdout"].splitlines() == ["bootstrap_extension.py: OK", "extension_gate.py: OK", "INPUT-BOOTSTRAP.json: OK"],
             "Emitted actual Bash checksum line did not verify the three files")
        local_refs = {**refs, "subject_qualification": prepared["subject_qualification"]}
        remote_refs = {**arm, "subject_qualification": bridge["arm_subjects"][binding["subject_id"]]["qualification"]}
        entries = []
        for key in sorted(local_refs):
            expected_ref = ref(local_refs[key]["path"])
            need(expected_ref["sha256"] == local_refs[key]["sha256"] == remote_refs[key]["sha256"], "Static source mismatch")
            dest = out / "static-received" / (key + ".bin")
            raw = out / "static-raw" / (key + ".json")
            need(not dest.exists() and not raw.exists(), "Future transfer path already exists")
            entries.append({"key": key, "remote_ref": remote_refs[key], "expected_local_source": local_refs[key],
                            "expected_bytes": expected_ref["bytes"], "actual_transfer_receipt": None,
                            "download_arguments": {"local_path": str(dest), "remote_path": remote_refs[key]["path"], "verify": True},
                            "primary_raw_output_path": str(raw)})
        pending = out / "STATIC9-READBACKS-PENDING.json"
        write(pending, {"schema": "hpc-forest-matrix15-unit-static-readbacks-prepared-v1", "mode": "PREPARE", "verified": False,
                        "cell_key": cell, "prepared": ref(generic / "PREPARED.json"), "entries": entries,
                        "actual_transfers_observed": False, "network_calls": 0})
        rows.append({"cell_key": cell, "binding": binding, "unit_preparation": ref(out / "PREPARATION.json"),
                     "input": ref(out / "stage/INPUT-BOOTSTRAP.json"), "body": ref(out / "job-body.sh"),
                     "job_prepare_arguments": ref(out / "JOB-PREPARE-ARGS.json"), "upload_manifest": ref(out / "UPLOAD-MANIFEST.json"),
                     "generic_prepared": ref(generic / "PREPARED.json"), "generic_builder_template": ref(generic / "INPUT-BUILDER-TEMPLATE.json"),
                     "generic_bootstrap_not_for_upload": ref(generic / "INPUT-BOOTSTRAP.json"),
                     "static9_pending": ref(pending), "bash_syntax_returncode": syntax["returncode"],
                     "actual_three_file_sha_check_stdout": checksum["stdout"], "serialized_ref3_boundary_passed": True})
    evidence.recheck()
    need(all(ref(path)["sha256"] == sha for path, sha in PINS.items()), "Locked sources changed during preparation")
    need(len({row["binding"]["session_id"] for row in rows}) == 3, "Duplicate session")
    write(OUTPUT / "TROIS-UNITES-VALIDATION-LOCALE-r1.json", {
        "schema": "hpc-forest-matrix15-three-units-local-verification-v1", "mode": "PREPARE", "verified": False,
        "units": rows, "source_pins_checked_before_and_after": [ref(path) for path in PINS],
        "actual_local_commands": ref(HERE / "COMMANDES-REELLES.json"),
        "native_authorization_created": False, "remote_calls": 0, "jobs_submitted": 0, "native_model_calls": 0,
        "workers_started": 0, "capacity_registry_modified": False,
        "execution_blocked_by_root_diagnostic": {"basis": "ROOT message, not independently observed by this preparation",
            "job_id": "755862", "status": "FAILED 1:0", "invocation_unknown": True,
            "error": "InfrastructureError: Missing, linked or oversized matrix JSON artifact"},
        "limitations": ["No fresh capacity or remote absence observation", "No upload, job plan or submit performed",
            "Use only unit stage/INPUT-BOOTSTRAP.json for the three-file bootstrap upload; the unchanged generic template has a REF2 gate",
            "Sol/count session4bb93e081ad042a185b7029f3ade2605 remains excluded; no replay"]})
    print(json.dumps({"units": [{"cell_key": row["cell_key"], "session_id": row["binding"]["session_id"],
                                 "input_sha256": row["input"]["sha256"], "body_sha256": row["body"]["sha256"]} for row in rows]}))


if __name__ == "__main__":
    main()
