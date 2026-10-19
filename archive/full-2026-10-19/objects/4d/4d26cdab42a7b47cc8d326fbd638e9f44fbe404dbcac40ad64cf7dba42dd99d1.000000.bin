"""Pure per-cell continuation input builder; never execute an admission or job."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parents[2]
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1"
WORK = BASE / "work/matrix15-extension-operation-inputs-r1"
DELIVERY = BASE / "outputs/HPC-Forest-Matrice15-Admission-Extension-Preparation-r3"
BOOTSTRAP = BASE / "outputs/HPC-Forest-Matrice15-Bootstrap-Extension-Preparation-r3/lecteur"
STATICS = BASE / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2"
FIRST_BUILDER = BASE / "work/matrix15-first-operation-inputs-r1/build_inputs.py"
FIRST_BUILDER_SHA = "e7295bb03e956dc343c70eaabcfca98f240c3b3643963c3381f2013edb6a4124"
PINS = {"dynamic_admission.py": "4d4216536ebf31079d208a9f6fa4a45ce1c0df3b972f4c3baafeba6204d97bda",
    "capacity.py": "a4f9121ef769ae98524f179a92b2ea27ea2a139e3ccc8c8982280f26c74b1a1d",
    "selection.py": "a0d03ff5a5be74a9feef2be50c9aae6ea34a19c3eefd0decc5ae0b0769bf4a15",
    "extension_gate.py": "e8e8ee7e69ccced5d15054f1a61f3970e0019a282e7c20f8cdbc4db77aa9eb30",
    "VENV-RUNTIME-IDENTITY.json": "049c5c1602814ec3541fcaa414f9c70dec4ecebbee9017414fbca9510be72f88"}
BOOT_PINS = {"bootstrap_extension.py": "7b98650d74afdd902ac0466b8459656c21fbfabc23dbf3be1015285b108f51eb",
    "sealed-bootstrap-helper.py": "d4bf5278c8fb698570e111b7e19c632e0bd8929e5aa8ebd833e262e303e56752",
    "job_prefix.py": "ed7c7ad59aa06d905f259e97a0bd83f2af3ed9be006d977bef3c46e92512db16"}
EVIDENCE_PINS = {"VALIDATION-LOCALE.json": "4e14758d31b3ebaa61c50da1de320a2735175b0e4267be93015adee0676b2df8",
    "FILES.sha256.json": "13a42d0d46653f0124a9854fcb3882eeba0c3552f19ae01ca3fa31c5a4e10fde",
    "REVUE-LECTURE-FRAICHE.json": "57efbaebb1f55404779f48ee9b2c04ac80455a4c1cd428a45987518ca5958682",
    "TESTS-NEUTRES-r1.xml": "bc081f0060c8aeeaf4f5b4df6e635dc598d87811ca5f35ffd93b56f30116379b"}
PREP_SCHEMA = "hpc-forest-matrix15-extension-operation-prepared-v1"
INPUT_SCHEMA = "hpc-forest-matrix15-extension-operation-builder-input-v1"
PREREQUISITE_FIELDS = {"first_batch_extension_gate", "gate_arm", "first_batch_received_evidence", "selection_state"}
PREPARED_FIELDS = {"schema", "verified", "cell_key", "binding_without_job_id", "statics", "statics_arm",
    "subject_qualification", "subject_reception", "bridge_report", "closure_primary", "review_evidence", "reviewer",
    "reviewed_at", "prerequisite_ref", "locked_sources", "locked_bootstrap", "user_instructions", "capacity_registry",
    "capacity_lock", "windows_cache", "output_windows", "codex_config", "commands_to_execute", "native_execution_authorized", "automatic_extension"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def load_text(name, path, checksum):
    path = Path(path)
    need(path.is_absolute() and path.is_file()
         and not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)), "Ordinary pinned source required")
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == checksum, "Locked source changed: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def runtime():
    upstream = load_text("matrix15_first_builder_library", FIRST_BUILDER, FIRST_BUILDER_SHA)
    reader = upstream.reader_runtime()
    for name, checksum in PINS.items():
        upstream.checked(reader, {"path": str(DELIVERY / name), "sha256": checksum})
    for name, checksum in EVIDENCE_PINS.items():
        upstream.checked(reader, {"path": str(DELIVERY / name), "sha256": checksum})
    for name, checksum in BOOT_PINS.items():
        upstream.checked(reader, {"path": str(BOOTSTRAP / name), "sha256": checksum})
    capacity = load_text("capacity", DELIVERY / "capacity.py", PINS["capacity.py"])
    sys.modules["capacity"] = capacity
    for name in ("selection", "extension_gate"):
        sys.modules[name] = load_text(name, DELIVERY / (name + ".py"), PINS[name + ".py"])
    dynamic = load_text("matrix15_extension_input_dynamic", DELIVERY / "dynamic_admission.py", PINS["dynamic_admission.py"])
    bootstrap = load_text("matrix15_extension_input_bootstrap", BOOTSTRAP / "bootstrap_extension.py", BOOT_PINS["bootstrap_extension.py"])
    return upstream, reader, dynamic, capacity, bootstrap


def ref(reader, path):
    return reader.ref2(reader.local_ref(path))


def read_ref(reader, item):
    need(isinstance(item, dict) and set(item) == {"path", "sha256"}, "Exact local reference required")
    path = reader.ordinary(item["path"])
    need(reader.local_ref(path)["sha256"] == item["sha256"], "Referenced bytes changed")
    value = reader.parse(path.read_bytes())
    need(isinstance(value, dict), "Object evidence required")
    return value


def owned_output(reader, value):
    path = Path(value)
    need(path.is_absolute() and ".." not in path.parts and any(path.is_relative_to(p) and path != p for p in (OUTPUT, WORK)),
         "New output must remain inside this builder's two owned roots")
    for ancestor in (path, *path.parents):
        need(not ancestor.is_symlink() and not ancestor.is_junction(), "Linked output ancestor refused")
    resolved = path.resolve()
    need(not resolved.exists() and any(resolved.is_relative_to(p.resolve()) and resolved != p.resolve() for p in (OUTPUT, WORK)),
         "Output exists or escapes ownership")
    return resolved


def reviewed_evidence(reader):
    validation_ref = ref(reader, DELIVERY / "VALIDATION-LOCALE.json")
    validation = read_ref(reader, validation_ref)
    review_ref = validation["source_review"]
    review = read_ref(reader, review_ref)
    need(review.get("decision") == "SHIP" and review.get("reviewed_source_sha256") == PINS
         and review.get("blocking_findings") == [], "Exact independently reviewed continuation sources required")
    report_ref = validation["pytest"]["report"]
    report_path = reader.ordinary(report_ref["path"])
    need(ref(reader, report_path) == report_ref, "Test report changed")
    suites = list(ET.fromstring(report_path.read_bytes()).iter("testsuite"))
    need(sum(int(s.get("tests", "0")) for s in suites) == 326 and all(
        all(int(s.get(k, "0")) == 0 for k in ("errors", "failures", "skipped")) for s in suites), "Final successful326-case report required")
    manifest_ref = ref(reader, DELIVERY / "FILES.sha256.json")
    manifest = read_ref(reader, manifest_ref)
    need(all(manifest.get(name) == checksum for name, checksum in PINS.items()), "Delivery inventory differs")
    # The locked validation remains PREPARE/verified:false. It is checked above
    # but cannot be promoted to primary production evidence by capacity.a4f.
    return [review_ref, report_ref, manifest_ref], review["reviewer"]


def prerequisites(dynamic, reader, value, cell_key, registry):
    need(isinstance(value, dict) and set(value) == PREREQUISITE_FIELDS, "Exact continuation prerequisite refs required")
    gate_check, cell = dynamic.verify_extension_gate(value["first_batch_extension_gate"], value["first_batch_received_evidence"],
        state=read_ref(reader, value["selection_state"]), cell_key=cell_key, registry=registry)
    evidence = dynamic.received_evidence(value["first_batch_received_evidence"])
    need(value["gate_arm"]["path"].startswith("/")
         and value["gate_arm"]["sha256"] == value["first_batch_extension_gate"]["sha256"], "Exact byte-identical ARM gate ref required")
    evidence.resolve(value["gate_arm"])
    evidence.recheck()
    return gate_check, cell


def fixed_paths(session):
    registry = str(BASE / "work/matrix15-global-capacity-production-r1")
    return {"capacity_registry": registry, "capacity_lock": registry + ".lock",
        "windows_cache": str(WORK / "worker-cache" / session),
        "output_windows": str(OUTPUT / (session + "-admission-windows")),
        "codex_config": "C:/Users/nicol/.codex/config.toml"}


def prepare(output, cell_key, prerequisite_ref=None):
    upstream, reader, dynamic, _capacity, bootstrap = runtime()
    need(cell_key in dynamic.contract.REGISTERED_CELLS, "Closed sixty-cell identity required")
    review_evidence, reviewer = reviewed_evidence(reader)
    statics = ref(reader, STATICS / "STATICS.json")
    refs, plan, _aliases = dynamic.static_inputs(statics)
    cell = dynamic.contract.validate_cell(dynamic.contract.REGISTERED_CELLS[cell_key])
    bridge_ref = ref(reader, BASE / "outputs/HPC-Forest-Q15-Pont-Natif-r1/production-r3/BRIDGE-REPORT.json")
    bridge = read_ref(reader, bridge_ref)
    need(bridge.get("verified") is True and cell["subject_id"] in bridge["subjects"], "Actual received per-subject Q bridge required")
    closure = upstream.closure_primary(reader)
    upstream.verify_closure(reader, closure)
    registry = str(BASE / "work/matrix15-global-capacity-production-r1")
    prior = read_ref(reader, prerequisite_ref) if prerequisite_ref else None
    if prior is not None:
        prerequisites(dynamic, reader, prior, cell_key, registry)
    helper = bootstrap.load_helper((BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    bootstrap_input = bootstrap.build_cell_input(helper, Path(refs["plan"]["path"]).read_bytes(), cell_key,
        prior["gate_arm"] if prior is not None else None)
    if prior is not None:
        bootstrap.validate_input(helper, bootstrap_input, Path(refs["plan"]["path"]).read_bytes())
    output = owned_output(reader, output)
    output.mkdir(parents=True, exist_ok=False)
    binding = bootstrap_input["binding_without_job_id"]
    prepared = {"schema": PREP_SCHEMA, "verified": False, "cell_key": cell_key, "binding_without_job_id": binding,
        "statics": statics, "statics_arm": ref(reader, STATICS / "STATIC-ARTIFACTS-ARM.json"),
        "subject_qualification": bridge["subjects"][cell["subject_id"]]["qualification"],
        "subject_reception": bridge["subjects"][cell["subject_id"]]["reception"], "bridge_report": bridge_ref,
        "closure_primary": closure, "review_evidence": review_evidence, "reviewer": reviewer,
        "reviewed_at": time.time(), "prerequisite_ref": prerequisite_ref,
        "locked_sources": {name: ref(reader, DELIVERY / name) for name in PINS},
        "locked_bootstrap": {name: ref(reader, BOOTSTRAP / name) for name in BOOT_PINS},
        "user_instructions": ref(reader, BASE / "outputs/HPC-Forest-Matrice15-Operation-Instructions-Utilisateur.md"),
        **fixed_paths(cell["session_id"]), "commands_to_execute": [],
        "native_execution_authorized": False, "automatic_extension": False}
    prepared_ref = reader.ref2(reader.write_exclusive(output / "PREPARED.json", prepared))
    reader.write_exclusive(output / "INPUT-BOOTSTRAP.json", bootstrap_input)
    reader.write_exclusive(output / "INPUT-DYNAMIC-TEMPLATE.json", dynamic.template(cell_key))
    reader.write_exclusive(output / "INPUT-BUILDER-TEMPLATE.json", {"schema": INPUT_SCHEMA, "mode": "PREPARE",
        "prepared": prepared_ref, "marker": None, "marker_readback": None, "job_status": None, "transfers": None,
        "cli_observation": None, "owned_worker_receipts": None, "output_directory": str(output.parent / (output.name + "-binding"))})
    reader.write_exclusive(output / "PREPARATION.json", {"schema": PREP_SCHEMA, "mode": "PREPARE", "verified": False,
        "cell_key": cell_key, "prerequisite_verified": prior is not None, "native_authorization": False,
        "automatic_extension": False, "commands_to_execute": [], "native_model_calls": 0, "jobs_submitted": 0})
    return prepared_ref


def owned_receipts(reader, capacity, refs, now):
    need(isinstance(refs, list), "Explicit owned-worker receipts list required")
    identity = capacity.load_venv_identity()  # files only; full fresh CIM remains admission's job
    sessions = set()
    for item in refs:
        receipt = read_ref(reader, item)
        need(set(receipt) == {"schema", "verified", "ownership_established", "session_id", "channel", "processes"}
             and receipt.get("schema") == "hpc-forest-native-owned-worker-identity-v1"
             and receipt.get("verified") is True and receipt.get("ownership_established") is True
             and receipt["session_id"] not in sessions and len(receipt["processes"]) == 2,
             "Actual complete two-process owned-worker receipt required")
        analysis = capacity.classify_processes(receipt["processes"], now, venv_identity=identity)
        groups = analysis["private_native_groups"]
        need(analysis["native_workers_count"] == analysis["private_windows_venv_pairs_count"] == 1
             and analysis["session_ids"] == [receipt["session_id"]]
             and groups[0][0]["channel"] == receipt["channel"]
             and receipt["processes"] == [{key: process[key] for key in capacity.PROCESS_FIELDS} for process in groups[0]],
             "Owned receipt must retain exact [base child,venv parent] identities")
        sessions.add(receipt["session_id"])


def build(input_ref):
    upstream, reader, dynamic, capacity, bootstrap = runtime()
    inputs = read_ref(reader, input_ref)
    keys = {"schema", "mode", "prepared", "marker", "marker_readback", "job_status", "transfers", "cli_observation",
            "owned_worker_receipts", "output_directory"}
    need(set(inputs) == keys and inputs["schema"] == INPUT_SCHEMA and inputs["mode"] in {"PREPARE", "BUILD"}, "Exact builder input required")
    prepared = read_ref(reader, inputs["prepared"])
    need(set(prepared) == PREPARED_FIELDS and prepared.get("schema") == PREP_SCHEMA
         and prepared.get("verified") is False, "Exact prepared operator data required")
    output = owned_output(reader, inputs["output_directory"])
    if inputs["mode"] != "BUILD" or any(inputs[key] is None for key in keys - {"schema", "mode"}) or prepared.get("prerequisite_ref") is None:
        output.mkdir(parents=True, exist_ok=False)
        return reader.ref2(reader.write_exclusive(output / "PREPARE-INCOMPLETE.json", {"verified": False, "mode": "PREPARE",
            "dynamic_input": None, "commands_to_execute": [], "native_authorization": False, "native_model_calls": 0}))
    now = time.time()
    review_evidence, reviewer = reviewed_evidence(reader)
    need(prepared["locked_sources"] == {name: ref(reader, DELIVERY / name) for name in PINS}
         and prepared["locked_bootstrap"] == {name: ref(reader, BOOTSTRAP / name) for name in BOOT_PINS}, "Prepared source selection cannot be overridden")
    prior = read_ref(reader, prepared["prerequisite_ref"])
    _gate, cell = prerequisites(dynamic, reader, prior, prepared["cell_key"], prepared["capacity_registry"])
    refs, plan, _aliases = dynamic.static_inputs(prepared["statics"])
    need(prepared["statics"] == ref(reader, STATICS / "STATICS.json")
         and prepared["statics_arm"] == ref(reader, STATICS / "STATIC-ARTIFACTS-ARM.json"), "Static selection cannot be overridden")
    helper = bootstrap.load_helper((BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
    _plan, canonical_binding = bootstrap.registered_selection(helper, Path(refs["plan"]["path"]).read_bytes(), prepared["cell_key"])
    bridge_ref = ref(reader, BASE / "outputs/HPC-Forest-Q15-Pont-Natif-r1/production-r3/BRIDGE-REPORT.json")
    bridge = read_ref(reader, bridge_ref)
    need(prepared["binding_without_job_id"] == canonical_binding
         and all(prepared[key] == value for key, value in fixed_paths(cell["session_id"]).items())
         and prepared["bridge_report"] == bridge_ref
         and prepared["subject_qualification"] == bridge["subjects"][cell["subject_id"]]["qualification"]
         and prepared["subject_reception"] == bridge["subjects"][cell["subject_id"]]["reception"]
         and prepared["closure_primary"] == upstream.closure_primary(reader)
         and prepared["review_evidence"] == review_evidence and prepared["reviewer"] == reviewer
         and prepared["user_instructions"] == ref(reader, BASE / "outputs/HPC-Forest-Matrice15-Operation-Instructions-Utilisateur.md")
         and type(prepared["reviewed_at"]) in (int, float) and 0 < prepared["reviewed_at"] <= now
         and prepared["native_execution_authorized"] is False and prepared["automatic_extension"] is False
         and prepared["commands_to_execute"] == [], "Prepared roots, identities, evidence or review cannot be overridden")
    marker = read_ref(reader, inputs["marker"])
    dynamic.reject_fixture(marker)
    binding = marker["binding"]
    expected = {**canonical_binding, "job_id": binding["job_id"]}
    need(binding == expected and all(binding[k] == cell[k] for k in cell), "Actual marker belongs to another registered cell")
    dynamic.validate_cli_observation(inputs["cli_observation"], now=now)
    owned_receipts(reader, capacity, inputs["owned_worker_receipts"], now)
    arm_refs = read_ref(reader, prepared["statics_arm"])
    need(set(inputs["transfers"]) == set(refs) | {"subject_qualification"}
         and all(inputs["transfers"][key]["remote_path"] == arm_refs[key]["path"] for key in refs), "Nine exact final-path transfers required")
    need(not Path(prepared["windows_cache"]).exists() and not Path(prepared["output_windows"]).exists(), "Cache/admission reuse refused")
    closure_evidence = upstream.verify_closure(reader, prepared["closure_primary"])
    expires = min(marker["admission_started_at"] + 3300, marker["allocation_outer_deadline"], dynamic.native.DEADLINE)
    dynamic.authorization_clock(marker, expires, now)
    output.mkdir(parents=True, exist_ok=False)
    observed = {"schema": dynamic.ARM_SCHEMA, "binding": binding, "observed_at": now, "marker": inputs["marker"],
        "marker_readback": inputs["marker_readback"], "job_id_observation": inputs["job_status"], "transfers": inputs["transfers"]}
    arm_ref = reader.ref2(reader.write_exclusive(output / "ARM-OBSERVATION.json", observed))
    dynamic.check_arm(arm_ref, binding, refs, prepared["subject_qualification"], now=now)
    role_extras = {
        "reservation_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": PINS["capacity.py"],
            "exclusive_lock_reviewed": True, "pending_capacity_accounting_reviewed": True, "maximum_native_workers_total": 4, "evidence_refs": review_evidence},
        "local_projection_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": PINS["capacity.py"],
            "private_census_export_excluded": True, "current_census_binding_reviewed": True, "fixture_promotion_excluded": True, "evidence_refs": review_evidence},
        "source_only_received_closure": {"source_only_received": True, "source_only_closed": True, "source_only_may_resume": False,
            "closed_source_only_session_ids": [v[0] for v in upstream.CLOSED.values()], "evidence_refs": closure_evidence}}
    roles = {}
    for name, extra in role_extras.items():
        value = {**binding, "schema": capacity.EVIDENCE_SCHEMAS[name], "verified": bool(review_evidence and closure_evidence), **extra}
        need(set(value) == capacity.CELL_FIELDS | capacity.EVIDENCE_ROLE_FIELDS[name] | {"schema", "verified"}, "Closed role schema differs")
        roles[name] = reader.ref2(reader.write_exclusive(output / (name + ".json"), value))
    files = [refs["source_zip"], refs["plan"], *[ref(reader, DELIVERY / name) for name in PINS], ref(reader, dynamic.COLD_READER)]
    review = {"schema": "hpc-forest-matrix15-observed-integration-review-v1", "source_zip_sha256": refs["source_zip"]["sha256"],
        "plan_sha256": refs["plan"]["sha256"], "neutral_tests_passed": bool(review_evidence), "blocking_findings": [],
        "reviewer": reviewer, "reviewed_at": prepared["reviewed_at"], "reviewed_files": files,
        "worker_argv_template": dynamic.worker_template(), "review_evidence_refs": review_evidence,
        "limitations": ["Code review does not establish current capacity or model success", "Full CIM and global reservation remain inside actual admission"]}
    review_ref = reader.ref2(reader.write_exclusive(output / "INTEGRATION-REVIEW.json", review))
    dynamic.review_input(review_ref, binding, files)
    actual = dynamic.template(prepared["cell_key"])
    actual.update(mode="ASSEMBLE", statics=prepared["statics"], statics_arm=prepared["statics_arm"],
        subject_qualification=prepared["subject_qualification"], subject_reception=prepared["subject_reception"],
        cli_observation=inputs["cli_observation"], arm_observation=arm_ref, integration_review=review_ref,
        user_instructions=prepared["user_instructions"], job_id=binding["job_id"], remote_root=binding["remote_root"],
        windows_cache=prepared["windows_cache"], output_windows=prepared["output_windows"], output_arm=binding["remote_root"] + "-admission",
        capacity_lock=prepared["capacity_lock"], capacity_registry=prepared["capacity_registry"],
        capacity_evidence={**roles, "owned_worker_receipts": inputs["owned_worker_receipts"]}, expires_at=expires,
        codex_config=prepared["codex_config"], first_batch_extension_gate=prior["first_batch_extension_gate"],
        first_batch_received_evidence=prior["first_batch_received_evidence"], selection_state=prior["selection_state"])
    need(set(actual) == set(dynamic.template()) and all(v is not None for v in actual.values()), "Incomplete dynamic input")
    dynamic.check_arm(arm_ref, binding, refs, prepared["subject_qualification"], now=time.time())
    need(time.time() < marker["admission_started_at"] + 600, "Original admission clock expired")
    read_ref(reader, input_ref)
    read_ref(reader, inputs["prepared"])
    result = reader.ref2(reader.write_exclusive(output / "INPUT-DYNAMIC-ASSEMBLE.json", actual))
    reader.write_exclusive(output / "BUILDER-RECEIPT.json", {"schema": INPUT_SCHEMA, "verified": True, "binding": binding,
        "dynamic_input": result, "authorization_created": False, "assemble_invoked": False, "capacity_observed": False,
        "registry_modified": False, "commands_to_execute": [], "native_model_calls": 0, "jobs_submitted": 0})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", allow_abbrev=False)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cell-key", required=True)
    p.add_argument("--prerequisites", type=Path)
    p.add_argument("--prerequisites-sha256")
    p = sub.add_parser("build", allow_abbrev=False)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--input-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        need(bool(args.prerequisites) == bool(args.prerequisites_sha256), "Prerequisite path and SHA must be paired")
        prior = {"path": str(args.prerequisites), "sha256": args.prerequisites_sha256} if args.prerequisites else None
        result = prepare(args.output.absolute(), args.cell_key, prior)
    else:
        result = build({"path": str(args.input.absolute()), "sha256": args.input_sha256})
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
