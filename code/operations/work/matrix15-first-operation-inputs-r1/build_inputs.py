"""Pure local input builder for the already-reviewed first-cell producer.

No census, auth probe, model, job, transfer, assembler, or configuration body is
read or invoked. PREPARE is the default; real binding files are required to build.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DELIVERY = BASE / "outputs/HPC-Forest-Matrice15-Admission-Dynamique-Preparation-r1"
STATICS = BASE / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2"
DEST = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/preparation"
INPUT_SCHEMA = "hpc-forest-matrix15-first-operation-builder-input-v1"
PREP_SCHEMA = "hpc-forest-matrix15-first-operation-inputs-prepared-v1"
PLAN_SHA = "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f"
PRODUCER_SHA = "ec17f8be95869eae0e5059d6d99b08b03baaeab22c7b9d7ec642f1d38101d55e"
CAPACITY_SHA = "f3e327ba2aafc386df34e34598bad91b8f1c406b6471ca548988448e7dc50e2b"
APPROVED_PRODUCERS = {PRODUCER_SHA, "806bb6bea6e0bb6141b66fd6170f230c91b18dd54e71d99ed78aa1e35759f132"}
READER_SHA = "dce92d6e1735a8b594528b61bc0134d6069ab524a5fecc0eb08c1d5a024d4e13"
FIRST_SESSION = "9a681c2826854a4b885e94c5e6243f0a"
FIRST_ROOT = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-r2-" + FIRST_SESSION
CLOSED = {
    "gpt-6-luna": ("bb7a58941e74486ba24267f2f526de8f", "749843", "luna"),
    "gpt-6-astra": ("aa970cf8bf5d4c1aaa0fdabb21d73a72", "750122", "astra"),
    "gpt-5.6-terra": ("15219a6fd62b4dcb91b395dcd4ae03d5", "750831", "terra"),
    "gpt-6.1-sol": ("665743a02b824021a697b6a4884a667c", "751592", "sol"),
}


def load_file(name, path, expected):
    # Never load an adjacent .pyc file: execute the exact verified text.
    import hashlib
    class PinnedTextLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            raw = Path(self.path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("Reviewed source changed before import")
            return compile(raw, self.path, "exec", dont_inherit=True)
    loader = PinnedTextLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def reader_runtime():
    import hashlib
    reader_path = BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r1/lecteur/first_batch_audit.py"
    if hashlib.sha256(reader_path.read_bytes()).hexdigest() != READER_SHA:
        raise ValueError("Reviewed source-only reader changed")
    reader = load_file("matrix15_builder_source_checker", reader_path, READER_SHA)
    revision = reader.parse((BASE / "outputs/HPC-Forest-Matrice15-Admission-r2/REVISION-ADMISSION-SANS-CYCLE.json").read_bytes())
    source = {"project_root": str(BASE / "work/matrix15-admission-no-cycle-r2/project"),
              "source_zip": reader.local_ref(revision["source_zip"]["path"]),
              "runtime_manifest": reader.local_ref(revision["runtime_manifest"]["path"])}
    reader.sealed_source(source)
    return reader


def runtime(bundle=None):
    reader = reader_runtime()
    bundle = bundle or {"producer": ref(reader, DELIVERY / "dynamic_admission.py"),
                        "helper": ref(reader, DELIVERY / "capacity.py")}
    producer_path, helper_path = checked(reader, bundle["producer"]), checked(reader, bundle["helper"])
    reader.need(bundle["producer"]["sha256"] in APPROVED_PRODUCERS and bundle["helper"]["sha256"] == CAPACITY_SHA
                and producer_path.name == "dynamic_admission.py" and helper_path.name == "capacity.py"
                and producer_path.parent == helper_path.parent, "Reviewed explicit producer/helper selection required")
    sys.dont_write_bytecode = True
    capacity = load_file("capacity", helper_path, CAPACITY_SHA)
    sys.modules["capacity"] = capacity
    dynamic = load_file("matrix15_first_input_dynamic", producer_path, bundle["producer"]["sha256"])
    return reader, dynamic, capacity


def ref(reader, path):
    return reader.ref2(reader.local_ref(path))


def checked(reader, item):
    reader.need(isinstance(item, dict) and set(item) == {"path", "sha256"}, "Exact path/SHA reference required")
    path = reader.ordinary(item["path"])
    reader.need(reader.local_ref(path)["sha256"] == item["sha256"], "Primary evidence changed")
    return path


def object_ref(reader, item):
    value = reader.parse(checked(reader, item).read_bytes())
    reader.need(isinstance(value, dict), "Object primary evidence required")
    return value


def owned_output(reader, value):
    """Keep every created directory physically inside this builder's ownership."""
    output, base = Path(value), Path(DEST)
    reader.need(output.is_absolute() and base.is_absolute() and ".." not in output.parts and ".." not in base.parts
                and output.is_relative_to(base),
                "Canonical absolute owned output without parent traversal required")
    for path in (output, *output.parents, base, *base.parents):
        reader.need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                    "Linked or junction output ancestor refused")
    resolved, boundary = output.resolve(), base.resolve()
    reader.need(resolved.is_relative_to(boundary) and resolved != boundary and not resolved.exists(),
                "New owned preparation output required")
    return resolved


def closure_primary(reader):
    old = Path("C:/Users/nicol/Documents/Codex/2026-10-15/cr/outputs/HPC-Forest-Harnais-Comparaison-r1")
    records = {"coordinator": ref(reader, old / "coordinator-state.json"),
        "stop": ref(reader, old / "STOP-AFTER-CURRENT"),
        "global_closure": ref(reader, Path("C:/Users/nicol/Documents/Codex/2026-10-15/cr/outputs/HPC-Forest-Mere-Dynamique-R4-MAX-Preparation-r2/operations-parent-lane-close-20261018T0542/FERMETURE-LOCALE-VERIFIEE.json")),
        "receipts": {}, "terminals": {}}
    expected = {"coordinator": "dbb0695d71789ab8f1ffc6bd6bc7271796cf363f3b97b13ae35d0f253ade539c",
                "stop": "b959980366df851397b4421a7d387c66e473f3ec35fd567a824aace0e61bd59f",
                "global_closure": "cd7823488980ccf5dc0065c4484829ecd757970490e1b0011650061651bd0857"}
    reader.need(all(records[k]["sha256"] == v for k, v in expected.items()), "Historical closure primary pins changed")
    for model, (_session, job, short) in CLOSED.items():
        records["receipts"][model] = ref(reader, old / f"receptions/source-only-{short}-max-{job}/reception-verifiee.json")
        terminal = (old / f"runs/source-only-{model}-max/efficiency.json" if short in {"luna", "astra"} else
                    old / f"receptions/source-only-{short}-max-{job}" / ("statut-terminal.json" if short == "terra" else "efficiency-fresh.json"))
        records["terminals"][model] = ref(reader, terminal)
    return records


def verify_closure(reader, records):
    reader.need(set(records) == {"coordinator", "stop", "global_closure", "receipts", "terminals"}
                and set(records["receipts"]) == set(records["terminals"]) == set(CLOSED), "Exact four closed MAX cohorts required")
    coordinator = object_ref(reader, records["coordinator"])
    closure = object_ref(reader, records["global_closure"])
    checked(reader, records["stop"])
    reader.need(coordinator.get("stage") == "source_only_max_complete_and_local_closure_reconciled"
        and coordinator.get("source_only_max_cells_received_and_audited") == 60
        and coordinator.get("source_only_max_groups_received_and_audited") == 4
        and coordinator.get("unsafe_legacy_source_only_coordinator_must_not_restart") is True
        and coordinator.get("no_source_only_generation_or_legacy_coordinator_restart_authorized") is True,
        "Coordinator does not establish closed source-only MAX")
    reader.need(closure.get("verified") is True and closure.get("source_only_MAX_cells_received_and_audited") == 60
        and closure.get("no_possible_descendant_unresolved_across_three_censuses") is True
        and closure.get("new_generation_or_OBS4_transition_authorized") is False
        and closure.get("absence_is_historical_not_fresh_at_recording") is True, "Historical global closure missing")
    for model, (session, job, _short) in CLOSED.items():
        receipt = object_ref(reader, records["receipts"][model])
        reader.need(receipt.get("model") == model and receipt.get("session_id") == session and receipt.get("job_id") == job
                    and receipt.get("arm") == "source-only" and receipt.get("effort") == "max",
                    "Foreign source-only reception identity")
        if model in {"gpt-6-luna", "gpt-6-astra"}:
            reader.need(receipt.get("verified") is True and receipt.get("subjects_received_and_audited") == 15,
                        "Source-only independent reception absent")
        else:
            reader.need(receipt.get("coverage_and_final_confirmations_verified") is True
                        and receipt.get("all_outcomes_accounted_for") is True and receipt.get("deliveries_reconciled") is True
                        and len(receipt.get("subjects", [])) == 15, "Source-only scientific reception absent")
        terminal = object_ref(reader, records["terminals"][model])
        # The terminal files are the original primary scheduler observations; one
        # Terra document uses a transport wrapper, so unwrap only explicit layers.
        for _ in range(3):
            if "structuredContent" in terminal:
                terminal = terminal["structuredContent"]
            elif set(terminal) == {"result"}:
                terminal = terminal["result"]
            elif isinstance(terminal.get("scheduler"), dict):
                terminal = terminal["scheduler"]
            else:
                break
        reader.need(terminal.get("job_id") == job and terminal.get("state") in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}
                    and terminal.get("finished") is not False, "Actual terminal scheduler observation required")
    return [records["coordinator"], records["stop"], records["global_closure"],
            *records["receipts"].values(), *records["terminals"].values()]


def verify_review(reader, prepared):
    primary = checked(reader, prepared["review_record"])
    text = primary.read_text(encoding="utf8")
    producer_sha = prepared["producer"]["sha256"]
    reader.need(producer_sha in APPROVED_PRODUCERS and "SHIP" in text and "/root/public_review" in text
                and producer_sha in text and CAPACITY_SHA in text, "Actual independent SHIP review transcription required")
    capacity_record = prepared.get("capacity_review_record", prepared["review_record"])
    capacity_text = checked(reader, capacity_record).read_text(encoding="utf8")
    reader.need("SHIP" in capacity_text and PRODUCER_SHA in capacity_text and CAPACITY_SHA in capacity_text
                and "140" in capacity_text, "Actual original capacity review record required")
    validation = object_ref(reader, prepared["validation"])
    source_review = validation.get("source_review", {})
    source_review_ref = source_review if set(source_review) == {"path", "sha256"} else None
    source_review = object_ref(reader, source_review_ref) if source_review_ref else source_review
    reader.need(source_review.get("decision") == "SHIP"
                and source_review.get("reviewed_source_sha256") == {
                    "dynamic_admission.py": producer_sha, "capacity.py": CAPACITY_SHA}, "Independent exact-source review differs")
    report_path = checked(reader, prepared["tests_report"])
    xml = ET.fromstring(report_path.read_bytes())
    suites = [xml] if xml.tag == "testsuite" else list(xml.iter("testsuite"))
    expected_count = validation["pytest"]["junit_counts"]["tests"]
    reader.need(type(expected_count) is int and expected_count >= 140
                and sum(int(s.get("tests", "0")) for s in suites) == expected_count and all(
        all(int(s.get(k, "0")) == 0 for k in ("failures", "errors", "skipped")) for s in suites), "Actual 140-case successful report required")
    reader.need(prepared["tests_report"] == validation["pytest"]["report"], "Test report does not match reviewed validation")
    inventory = object_ref(reader, prepared["files_inventory"])
    reader.need(inventory["dynamic_admission.py"] == producer_sha and inventory["capacity.py"] == CAPACITY_SHA,
                "Reviewed file inventory differs")
    refs = [prepared[k] for k in ("review_record", "tests_report", "validation", "files_inventory")]
    refs.append(capacity_record)
    if source_review_ref:
        refs.append(source_review_ref)
    return list({(item["path"], item["sha256"]): item for item in refs}.values())


def prepare(output, selection_ref=None):
    reader = reader_runtime()
    selection = (object_ref(reader, selection_ref) if selection_ref else {
        "producer": ref(reader, DELIVERY / "dynamic_admission.py"), "helper": ref(reader, DELIVERY / "capacity.py"),
        "validation": ref(reader, DELIVERY / "VALIDATION-LOCALE.json"),
        "files_inventory": ref(reader, DELIVERY / "FILES.sha256.json"),
        "review_record": ref(reader, DEST.parent / "DYNAMIQUE-REVUE-INDEPENDANTE-RECUE.md")})
    reader.need(set(selection) == {"producer", "helper", "validation", "files_inventory", "review_record"},
                "Explicit reviewed delivery selection fields required")
    reader, dynamic, _capacity = runtime(selection)
    output = owned_output(reader, output)
    output.mkdir(parents=True, exist_ok=False)
    statics_ref = ref(reader, STATICS / "STATICS.json")
    refs, _plan, _aliases = dynamic.static_inputs(statics_ref)
    reader.need(refs["plan"]["sha256"] == PLAN_SHA, "Only final r2 plan is supported")
    bridge_ref = ref(reader, BASE / "outputs/HPC-Forest-Q15-Pont-Natif-r1/production-r3/BRIDGE-REPORT.json")
    bridge = object_ref(reader, bridge_ref)
    reader.need(bridge.get("verified") is True, "Actual Q bridge reception required")
    prepared = {"schema": PREP_SCHEMA, "verified": False, "prepared_only": True,
        "producer": selection["producer"], "helper": selection["helper"],
        "statics": statics_ref, "statics_arm": ref(reader, STATICS / "STATIC-ARTIFACTS-ARM.json"),
        "bridge_report": bridge_ref,
        "subject_qualification": bridge["subjects"]["2020-quicksort"]["qualification"],
        "subject_reception": bridge["subjects"]["2020-quicksort"]["reception"],
        "review_record": selection["review_record"],
        "capacity_review_record": ref(reader, DEST.parent / "DYNAMIQUE-REVUE-INDEPENDANTE-RECUE.md"),
        "reviewer": "/root/public_review", "review_record_observed_at": time.time(),
        "validation": selection["validation"],
        "tests_report": object_ref(reader, selection["validation"])["pytest"]["report"],
        "files_inventory": selection["files_inventory"],
        "closure_primary": closure_primary(reader),
        "user_instructions": ref(reader, BASE / "outputs/HPC-Forest-Matrice15-Operation-Instructions-Utilisateur.md"),
        "windows_cache": str(BASE / "work/matrix15-first-operation-inputs-r1" / (FIRST_SESSION + "-worker-r1")),
        "output_windows": str(DEST.parent / "admission-windows-r1"),
        "capacity_registry": str(BASE / "work/matrix15-global-capacity-production-r1"),
        "capacity_lock": str(BASE / "work/matrix15-global-capacity-production-r1.lock"),
        "codex_config": "C:/Users/nicol/.codex/config.toml", "native_model_calls": 0, "capacity_observed": False}
    verify_closure(reader, prepared["closure_primary"])
    verify_review(reader, prepared)
    prepared_ref = reader.ref2(reader.write_exclusive(output / "PREPARED.json", prepared))
    template = {"schema": INPUT_SCHEMA, "mode": "PREPARE", "prepared": prepared_ref,
                "marker": None, "marker_readback": None, "job_status": None, "transfers": None,
                "cli_observation": None, "owned_worker_receipts": [], "output_directory": str(output.parent / "actual-binding-r1")}
    reader.write_exclusive(output / "INPUT-TEMPLATE-PREPARED.json", template)
    return prepared_ref


def build(input_ref):
    reader = reader_runtime()
    inputs = object_ref(reader, input_ref)
    keys = {"schema", "mode", "prepared", "marker", "marker_readback", "job_status", "transfers",
            "cli_observation", "owned_worker_receipts", "output_directory"}
    reader.need(set(inputs) == keys and inputs.get("schema") == INPUT_SCHEMA and inputs.get("mode") == "BUILD"
                and all(v is not None for v in inputs.values()), "PREPARE/missing binding files cannot build actual inputs")
    now = time.time()  # No operational clock override is exposed.
    prepared = object_ref(reader, inputs["prepared"])
    reader, dynamic, capacity = runtime(prepared)
    reader.need(prepared.get("schema") == PREP_SCHEMA and prepared.get("verified") is False
                and prepared.get("producer", {}).get("sha256") in APPROVED_PRODUCERS
                and prepared.get("helper", {}).get("sha256") == CAPACITY_SHA, "Exact prepared operator inputs required")
    review_evidence = verify_review(reader, prepared)
    closure_evidence = verify_closure(reader, prepared["closure_primary"])
    refs, plan, _aliases = dynamic.static_inputs(prepared["statics"])
    reader.need(refs["plan"]["sha256"] == PLAN_SHA, "Final plan drift")
    arm_refs = object_ref(reader, prepared["statics_arm"])
    marker = object_ref(reader, inputs["marker"])
    dynamic.reject_fixture(marker)
    binding = marker.get("binding")
    capacity.validate_binding(binding)
    subject = dynamic.contract.resolve_subject(plan, dynamic.FIRST_CELL)
    authorization_seed = {**{k: subject[k] for k in ("cell_key", "subject_id", "model", "effort", "session_id")},
        "scope_id": dynamic.contract.SCOPE, "job_id": binding["job_id"], "remote_root": FIRST_ROOT, "artifacts": refs}
    reader.need(binding == dynamic.native.cell_binding(authorization_seed), "Fresh marker differs from exact first-cell source/plan/session")
    observed = {"schema": dynamic.ARM_SCHEMA, "binding": binding, "observed_at": now, "marker": inputs["marker"],
        "marker_readback": inputs["marker_readback"], "job_id_observation": inputs["job_status"], "transfers": inputs["transfers"]}
    reader.need(set(inputs["transfers"]) == set(refs) | {"subject_qualification"}, "Exactly nine actual transfer records required")
    reader.need(all(inputs["transfers"][key]["remote_path"] == arm_refs[key]["path"] for key in refs), "Actual remote final shared paths differ")
    dynamic.validate_cli_observation(inputs["cli_observation"], now=now)
    expires = marker["admission_started_at"] + 3300
    dynamic.authorization_clock(marker, expires, now)
    output = owned_output(reader, inputs["output_directory"])
    reader.need(not Path(prepared["windows_cache"]).exists() and not Path(prepared["output_windows"]).exists(),
                "Actual worker cache/admission paths must still be absent")
    reader.need(Path(prepared["capacity_registry"]).is_dir(), "ROOT must create the private capacity registry first")
    reader.need(isinstance(inputs["owned_worker_receipts"], list), "Owned worker receipt list required")
    output.mkdir(parents=True, exist_ok=False)
    try:
        arm_ref = reader.ref2(reader.write_exclusive(output / "ARM-OBSERVATION.json", observed))
        dynamic.check_arm(arm_ref, binding, refs, prepared["subject_qualification"], now=now)
        common = {**binding, "verified": True}
        role_extras = {
            "reservation_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": CAPACITY_SHA,
                "exclusive_lock_reviewed": True, "pending_capacity_accounting_reviewed": True,
                "maximum_native_workers_total": 4, "evidence_refs": review_evidence},
            "local_projection_producer_review": {"decision": "accept", "reviewed_capacity_producer_sha256": CAPACITY_SHA,
                "private_census_export_excluded": True, "current_census_binding_reviewed": True,
                "fixture_promotion_excluded": True, "evidence_refs": review_evidence},
            "source_only_received_closure": {"source_only_received": True, "source_only_closed": True,
                "source_only_may_resume": False, "closed_source_only_session_ids": [v[0] for v in CLOSED.values()],
                "evidence_refs": closure_evidence}}
        role_refs = {}
        for name, extra in role_extras.items():
            value = {**common, "schema": capacity.EVIDENCE_SCHEMAS[name], **extra}
            reader.need(set(value) == capacity.CELL_FIELDS | capacity.EVIDENCE_ROLE_FIELDS[name] | {"schema", "verified"},
                        "Role schema differs from immutable helper")
            role_refs[name] = reader.ref2(reader.write_exclusive(output / (name + ".json"), value))
        reviewed_files = [refs["source_zip"], refs["plan"], prepared["producer"], prepared["helper"]]
        review = {"schema": "hpc-forest-matrix15-observed-integration-review-v1", "source_zip_sha256": refs["source_zip"]["sha256"],
            "plan_sha256": PLAN_SHA, "neutral_tests_passed": True, "blocking_findings": [], "reviewer": prepared["reviewer"],
            "reviewed_at": prepared["review_record_observed_at"], "limitations": [
                "Timestamp records transcription observation, not exact chat review time",
                "Independent code review covers producer and helper; ZIP and plan are checked by static producers and parent",
                "Local review and tests do not establish current capacity, ARM runtime or model success",
                "Private census and original 600/3300-second envelope remain runtime prerequisites; science stays 1800 seconds"],
            "reviewed_files": reviewed_files, "worker_argv_template": dynamic.worker_template(), "review_evidence_refs": review_evidence}
        review_ref = reader.ref2(reader.write_exclusive(output / "INTEGRATION-REVIEW.json", review))
        dynamic.review_input(review_ref, binding, reviewed_files)
        actual = dynamic.template()
        actual.update(mode="ASSEMBLE", statics=prepared["statics"], statics_arm=prepared["statics_arm"],
            subject_qualification=prepared["subject_qualification"], subject_reception=prepared["subject_reception"],
            cli_observation=inputs["cli_observation"], arm_observation=arm_ref, integration_review=review_ref,
            user_instructions=prepared["user_instructions"], job_id=binding["job_id"], remote_root=FIRST_ROOT,
            windows_cache=prepared["windows_cache"], output_windows=prepared["output_windows"], output_arm=FIRST_ROOT + "-admission",
            capacity_lock=prepared["capacity_lock"], capacity_registry=prepared["capacity_registry"],
            capacity_evidence={**role_refs, "owned_worker_receipts": inputs["owned_worker_receipts"]},
            expires_at=expires, codex_config=prepared["codex_config"])
        reader.need(set(actual) == set(dynamic.template()) and all(v is not None for v in actual.values()), "Incomplete actual producer input")
        reader.need(time.time() < marker["admission_started_at"] + 600, "Initial window expired during input building")
        checked(reader, input_ref)
        checked(reader, inputs["prepared"])
        dynamic.check_arm(arm_ref, binding, refs, prepared["subject_qualification"], now=time.time())
        actual_ref = reader.ref2(reader.write_exclusive(output / "INPUT-DYNAMIC-ASSEMBLE.json", actual))
        reader.write_exclusive(output / "BUILDER-RECEIPT.json", {"schema": "hpc-forest-matrix15-first-operation-inputs-built-v1",
            "verified": True, "binding": binding, "input": input_ref, "prepared": inputs["prepared"], "dynamic_input": actual_ref,
            "actual_absence_or_reconciliation_precomputed": False, "assemble_invoked": False, "native_model_calls": 0,
            "capacity_observed": False, "authorization_created": False, "config_body_read_or_exported": False})
        return actual_ref
    except Exception as exc:
        reader.write_exclusive(output / "REFUS.json", {"verified": False, "reason": type(exc).__name__ + ": " + str(exc),
            "assemble_invoked": False, "native_model_calls": 0, "authorization_created": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="mode", required=True)
    prep = sub.add_parser("prepare", allow_abbrev=False)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--selection", type=Path)
    prep.add_argument("--selection-sha256")
    actual = sub.add_parser("build", allow_abbrev=False)
    actual.add_argument("--input", type=Path, required=True)
    actual.add_argument("--input-sha256", required=True)
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        if bool(args.selection) != bool(args.selection_sha256):
            parser.error("--selection and --selection-sha256 must be provided together")
        selected = {"path": str(args.selection), "sha256": args.selection_sha256} if args.selection else None
        result = prepare(args.output, selected)
    else:
        result = build({"path": str(args.input), "sha256": args.input_sha256})
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
