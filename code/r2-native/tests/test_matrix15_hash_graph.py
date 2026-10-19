"""NEUTRAL temporary hash graphs, never operational campaign evidence.

All content and digests are real temporary files. Only the three historical
static pins and the external CLI/primes prerequisites are replaced; no hashing,
artifact, directory, qualification, reception or dependency check is mocked.
"""
from __future__ import annotations

import copy
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import matrix15_contract as contract
from hpc_forest import matrix15_lane_contract as lane_contract
from hpc_forest import native_matrix15 as native
from hpc_forest.core import InfrastructureError, digest, file_digest


def references(value):
    if contract.reference(value):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


class NeutralFiles:
    """Append-only constructor: every reference must already have final bytes."""

    def __init__(self, root):
        self.root = root / "NEUTRAL-NOT-AN-ADMISSION"
        self.root.mkdir()
        self.frozen = {}
        self.order = []

    def freeze(self, path):
        ref = {"path": str(path.resolve()), "sha256": file_digest(path)}
        for old_path, old_sha in self.frozen.items():
            assert file_digest(old_path) == old_sha
        assert path not in self.frozen
        self.frozen[path] = ref["sha256"]
        self.order.append(path)
        return ref

    def raw(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return self.freeze(path)

    def json(self, name, value):
        for ref in references(value):
            assert file_digest(Path(ref["path"])) == ref["sha256"]
            assert Path(ref["path"]).resolve() in self.frozen
        return self.raw(name, json.dumps(value, sort_keys=True).encode("utf8"))

    def archive(self, name, members):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for relative, ref in members.items():
                archive.write(ref["path"], relative)
        return self.freeze(path)


def directory_entry(canonical, actual, prefix, inventory, subject_id, role):
    return {"kind": "directory", "subject_id": subject_id, "role": role,
        "canonical_path": canonical,
        "windows_path": str(actual) if os.name == "nt" else "C:/NEUTRAL/" + prefix,
        "arm_path": str(actual) if os.name != "nt" else "/scratch/NEUTRAL/" + prefix,
        "inventory_prefix": prefix, "inventory_sha256": digest(inventory)}


@pytest.fixture
def graph(tmp_path, monkeypatch):
    files = NeutralFiles(tmp_path)
    monkeypatch.setattr(native, "_INSTALLED_ALIASES", None)
    protocol_ref = files.json("static/protocol.json", {"fixture": "NEUTRAL protocol"})
    harness_ref = files.raw("static/harness.txt", b"NEUTRAL inert harness bytes")
    runtime_ref = files.json("static/runtime.json", {"NEUTRAL.txt": harness_ref["sha256"]})
    source_ref = files.archive("NEUTRAL-source.zip", {"NEUTRAL.txt": harness_ref})
    evidence_ref = files.raw("static/NEUTRAL-evidence.txt", b"NEUTRAL fixture; no real observation")
    primes_ref = files.json("static/NEUTRAL-external-primes.json", {"fixture": "NEUTRAL external prerequisite"})
    subjects, records, manifest_files, entries, aggregate = {}, {}, {}, [], {}
    for subject_id in contract.SUBJECTS:
        prefix = "preparation/" + subject_id + "/frozen"
        root = files.root / prefix
        r1_ref = files.json("static/" + subject_id + "/r1.json", {
            "fixture": "NEUTRAL " + subject_id, "benchmark": {"reference_seconds": 1.0, "repetitions": 3}})
        prepared_ref = files.json(prefix + "/validation/contract.json", {
            "fixture": "NEUTRAL " + subject_id, "benchmark": {"reference_seconds": 2.0, "repetitions": 3}})
        source_member = files.raw(prefix + "/source/fixture.txt", b"NEUTRAL inert source metadata")
        statement_ref = files.raw("static/" + subject_id + "/statement.txt", b"NEUTRAL inert statement")
        inventory = {"validation/contract.json": prepared_ref["sha256"], "source/fixture.txt": source_member["sha256"]}
        manifest_files.update({prefix + "/" + name: sha for name, sha in inventory.items()})
        canonical = "/gpfs/NEUTRAL/" + prefix
        for role, suffix in (("official", ""), ("source", "/source"), ("validation", "/validation")):
            selected = {name[len(suffix):].lstrip("/"): sha for name, sha in inventory.items()
                        if not suffix or name.startswith(suffix[1:] + "/")}
            entries.append(directory_entry(canonical + suffix, root if not suffix else root / suffix[1:],
                                           prefix + suffix, selected, subject_id, role))
        record = {"status": "ready", "prepared": {"source": canonical + "/source", "validation": canonical + "/validation"}}
        records[subject_id] = record
        aggregate[subject_id] = {"contract": r1_ref}
        subjects[subject_id] = {"subject_id": subject_id, "official_preparation_path": canonical,
            "preparation_sha256": digest(record), "r1_contract_ref": r1_ref,
            "prepared_contract_ref": prepared_ref, "statement_ref": statement_ref,
            "qualification_ref": None, "reception_ref": None,
            "config": {"neutral": "NEUTRAL metadata only", "codex": {"model": "{cell.model}", "reasoning_effort": "max"}}}
    preparation = {"records": records, "files": manifest_files}
    preparation_ref = files.json("static/preparation.json", preparation)
    r1s_ref = files.json("static/r1-contracts.json", {"schema": "hpc-forest-harness-reference-contracts-v1", "subjects": aggregate})
    for module in (contract, native):
        monkeypatch.setattr(module, "PROTOCOL_SHA256", protocol_ref["sha256"])
        monkeypatch.setattr(module, "R1_CONTRACTS_SHA256", r1s_ref["sha256"])
        monkeypatch.setattr(module, "HARNESS_SHA256", harness_ref["sha256"])
    aliases = {"schema": "hpc-forest-matrix15-artifact-aliases-v2", "scope_id": contract.SCOPE,
        "source_zip_sha256": source_ref["sha256"], "preparation_manifest_sha256": preparation_ref["sha256"], "entries": entries}
    aliases_ref = files.json("aliases.json", native.validate_aliases(aliases, source_ref["sha256"]))
    plan = {"schema": "hpc-forest-matrix15-native-max-plan-v2", "scope_id": contract.SCOPE,
        "protocol": protocol_ref, "models": list(contract.MODELS), "efforts": ["max"], "subjects": list(contract.SUBJECTS),
        "cells": copy.deepcopy(list(contract.REGISTERED_CELLS.values())), "subject_bindings": subjects,
        "source_zip_sha256": source_ref["sha256"], "runtime_manifest": runtime_ref,
        "preparation_manifest": preparation_ref, "artifact_aliases": aliases_ref,
        "r1_contracts": r1s_ref, "harness": harness_ref, "primes_release": primes_ref,
        "maximum_native_workers_total": 4, "maximum_cells_per_authorization": 1,
        "budgets_per_cell": copy.deepcopy(contract.BUDGETS), "target": copy.deepcopy(contract.TARGET),
        "automatic_extension": False, "scientific_contract": "exact-R1-harness-mixed-calibration-only-excluded",
        "exclusive_deadline_utc": "2026-10-31T23:00:00Z", "reception_audit_reserve_seconds": 10800}
    plan_ref = files.json("plan.json", contract.validate_plan(plan))
    cell = copy.deepcopy(next(iter(contract.REGISTERED_CELLS.values())))
    subject = contract.resolve_subject(plan, cell["cell_key"])
    binding = {**cell, "scope_id": contract.SCOPE, "job_id": "900001",
        "remote_root": "/scratch/NEUTRAL/" + contract.SCOPE + "-" + cell["session_id"],
        "source_zip_sha256": source_ref["sha256"], "plan_sha256": plan_ref["sha256"],
        "preparation_manifest_sha256": preparation_ref["sha256"], "r1_contract_sha256": subject["r1_contract_ref"]["sha256"]}
    common = {key: binding[key] for key in ("scope_id", "subject_id", "source_zip_sha256", "plan_sha256",
        "preparation_manifest_sha256", "r1_contract_sha256")}
    _, inventory = native.directory_artifact(subject["official_preparation_path"], subject_id=subject["subject_id"],
        role="official", aliases=aliases, preparation_manifest=preparation,
        preparation_manifest_sha256=preparation_ref["sha256"])
    qualification = {**common, "schema": "hpc-forest-matrix15-subject-qualification-v1", "verified": True,
        "observation_mode": "command-stream-v1", "native_model_calls": 0, "r1_paired_contract_verified": True,
        "allocation": {"architecture": "aarch64", "job_id": "900001", "nodes": 1, "tasks": 1,
            "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0},
        "execution_semantics_changed": False, "independent_raw_stdout_per_candidate_verified": False,
        "independent_performance_audit_verified": False, "prepared_contract": subject["prepared_contract_ref"],
        "prepared_root": subject["official_preparation_path"], "prepared_files": inventory, "evidence_refs": [evidence_ref]}
    qualification_ref = files.json("qualification.json", qualification)
    archive_ref = files.archive("NEUTRAL-received.zip", {"qualification.json": qualification_ref})
    audit = {**common, "schema": "hpc-forest-matrix15-subject-reception-audit-v1", "verified": True,
        "qualification_sha256": qualification_ref["sha256"], "archive_sha256": archive_ref["sha256"],
        "all_members_regular_unique": True, "restored_files_byte_identical": True,
        "r1_paired_contract_verified": True, "actual_official_evaluator_trace_verified": True,
        "independent_raw_stdout_per_candidate_verified": False, "independent_performance_audit_verified": False}
    audit_ref = files.json("audit.json", audit)
    reception = {**common, "schema": "hpc-forest-matrix15-subject-reception-v1", "verified": True,
        "qualification": qualification_ref, "archive": archive_ref, "audit": audit_ref, "evidence_refs": [evidence_ref]}
    reception_ref = files.json("reception.json", reception)
    cli_files = {name: files.raw("static/cli/" + name, ("NEUTRAL inert " + name).encode()) for name in native.CLI_FILES}
    monkeypatch.setattr(native, "CLI_FILES", {name: ref["sha256"] for name, ref in cli_files.items()})
    # This only bypasses the separate external primes admission, never this graph.
    monkeypatch.setattr(native, "verify_primes_release", lambda path, *_: native.read_json(path))
    proof_values = {
        "cli_identity": {"version": "codex-cli 0.163.0-alpha.10.2", "executable_path": cli_files["codex.exe"]["path"],
            "executable_sha256": cli_files["codex.exe"]["sha256"], "source_execution_allowed": False,
            "authentication": "existing-local-ChatGPT", "files": cli_files, "observed_at": 1000.0,
            "task_cli_policy_sha256": evidence_ref["sha256"]},
        "integration_review": {"neutral_tests_passed": True, "blocking_findings": [], "reviewer": "NEUTRAL fixture only",
            "reviewed_at": 1000.0, "limitations": ["NEUTRAL fixtures; no operation observed"],
            "reviewed_files": [plan_ref], "reviewed_command_sha256": evidence_ref["sha256"]},
        "cell_admission": {"human_max_only": True, "one_cell_only": True, "automatic_extension": False,
            "all_prior_calls_reconciled": True, "maximum_native_workers": 4,
            "primes_release_sha256": primes_ref["sha256"], "one_submission_only": True},
        "session_freshness": {"observed_at": 1000.0, "verified_no_prior_claims": True, "new_cache": True,
            "new_registry": True, "new_mailbox": True, "native_calls_started_at_admission": 0}}
    refs = {"plan": plan_ref, "artifact_aliases": aliases_ref, "source_zip": source_ref,
        "runtime_manifest": runtime_ref, "preparation_manifest": preparation_ref, "r1_contracts": r1s_ref,
        "harness": harness_ref, "primes_release": primes_ref, "subject_qualification": qualification_ref,
        "subject_reception": reception_ref}
    for key, extra in proof_values.items():
        refs[key] = files.json("proofs/" + key + ".json", {**binding, **extra, "verified": True,
            "schema": "hpc-forest-matrix15-" + key.replace("_", "-") + "-v1", "evidence_refs": [evidence_ref]})
    refs["transport_admission"] = files.json("proofs/transport.json", {**binding,
        "schema": "hpc-forest-matrix15-transport-admission-v1", "verified": True, "evidence_refs": [evidence_ref],
        "native_model_calls": 0, "normal_first_call_proved": False, "cli_tools_disabled": True,
        "cli_identity_sha256": refs["cli_identity"]["sha256"], "subject_qualification_sha256": qualification_ref["sha256"],
        "neutral_tests_passed": True})
    reservation_ref = files.json("proofs/reservation.json", {**binding, "schema": lane_contract.RESERVATION_SCHEMA,
        "verified": True, "reservation_id": "e" * 32, "exclusive_global_lock_held_at_census": True,
        "all_native_workers_known": True, "launcher_python_pairs_count_as_one": True, "observed_at": 1000.0,
        "active_native_workers_before_start": 0, "maximum_native_workers_total": 4, "one_cell_only": True,
        "one_submission_only": True, "consumed": False, "private_full_census_sha256": evidence_ref["sha256"]})
    evidence = {key: evidence_ref["sha256"] for key in lane_contract.EVIDENCE_FIELDS}
    evidence["global_slot_reservation"] = reservation_ref["sha256"]
    projection_ref = files.json("proofs/projection.json", {**binding, "schema": lane_contract.PROJECTION_SCHEMA,
        "verified": True, "other_native_workers_count": 0, "active_native_workers_before_start": 0,
        "maximum_native_workers_total": 4, "observed_at": 1000.0, "observation_origin": "parent-private-Windows-census",
        "windows_census_observed_by_arm": False, "full_census_exported": False,
        "foreign_configuration_or_credentials_exported": False, "evidence_sha256": evidence,
        "all_native_workers_known": True, "launcher_python_pairs_count_as_one": True, "source_only_active_workers": 0})
    refs["worker_lane_admission"] = files.json("proofs/lane.json", {**binding, "schema": lane_contract.LANE_SCHEMA,
        "verified": True, "maximum_native_workers_total": 4, "active_native_workers_before_start": 0,
        "full_census_locally_verified": True, "new_cache_registry_root": True, "native_calls_started": 0,
        "observed_at": 1000.0, "private_full_census_sha256": evidence_ref["sha256"],
        "minimal_owned_observations": projection_ref, "slot_reservation": reservation_ref})
    authorization = {**cell, "schema": "hpc-forest-matrix15-authorization-v1", "scope_id": contract.SCOPE,
        "verified": True, "expires_at": 2000.0, "user_messages": ["NEUTRAL fixture, never user authorization"],
        "old_candidates_imported": False, "operator_algorithm_advice": False,
        "native_calls_started_at_authorization": 0, "job_id": binding["job_id"],
        "remote_root": binding["remote_root"], "artifacts": refs}
    authorization_ref = files.json("authorization.json", authorization)
    downstream = [qualification_ref, archive_ref, audit_ref, reception_ref, projection_ref, reservation_ref,
        authorization_ref, *(ref for key, ref in refs.items() if key in native.PROOF_FIELDS or key == "worker_lane_admission")]
    return SimpleNamespace(files=files, plan=plan, plan_ref=plan_ref, aliases=aliases, aliases_ref=aliases_ref,
        subject=subject, binding=binding, preparation=preparation, qualification=qualification,
        qualification_ref=qualification_ref, reception=reception, reception_ref=reception_ref, audit=audit,
        downstream=downstream, authorization=authorization, authorization_ref=authorization_ref)


def verify(graph, **changes):
    options = {"qualification": graph.qualification, "reception": graph.reception, "subject": graph.subject,
        "binding": graph.binding, "qualification_ref": graph.qualification_ref, "prepared": True,
        "aliases": graph.aliases, "preparation_manifest": graph.preparation}
    options.update(changes)
    return native.verify_qualification(**options)


def validate(graph):
    return native.validate_receipt(graph.authorization_ref["path"], {contract.SCOPE}, runtime=False, now=1000.0)


def test_real_forward_only_graph_is_constructible_without_rehashing_earlier_files(graph):
    assert contract.validate_plan(native.read_json(native.artifact(graph.plan_ref))) == graph.plan
    assert graph.files.order.index(Path(graph.aliases_ref["path"])) < graph.files.order.index(Path(graph.plan_ref["path"]))
    assert graph.files.order.index(Path(graph.plan_ref["path"])) < graph.files.order.index(Path(graph.qualification_ref["path"]))
    assert graph.files.order.index(Path(graph.qualification_ref["path"])) < graph.files.order.index(Path(graph.reception_ref["path"]))
    assert graph.files.order[-1] == Path(graph.authorization_ref["path"])
    assert all(subject["qualification_ref"] is None and subject["reception_ref"] is None
               for subject in graph.plan["subject_bindings"].values())
    assert native.validate_alias_dependencies(graph.aliases, graph.plan_ref, graph.aliases_ref, graph.downstream) == graph.aliases
    verify(graph)
    assert validate(graph) == graph.authorization
    assert file_digest(Path(graph.plan_ref["path"])) == graph.plan_ref["sha256"]
    assert all(file_digest(path) == sha for path, sha in graph.files.frozen.items())


def test_two_local_host_projections_keep_static_and_transported_bytes_unchanged(graph):
    """Exercise host-specific paths on this OS; this never claims a live ARM run."""
    admissions = []
    original_refs = graph.authorization["artifacts"]
    lane = native.read_json(native.artifact(original_refs["worker_lane_admission"]))
    for host in ("NEUTRAL-Windows-projection", "NEUTRAL-ARM-projection"):
        def transported(name, ref, host=host):
            copied = graph.files.raw(host + "/" + name, Path(ref["path"]).read_bytes())
            assert copied["sha256"] == ref["sha256"]
            return copied

        refs = copy.deepcopy(original_refs)
        for key in ("subject_qualification", *native.PROOF_FIELDS):
            refs[key] = transported(key + ".json", original_refs[key])
        archive_ref = transported("received.zip", graph.reception["archive"])
        audit_ref = transported("audit.json", graph.reception["audit"])
        reception = {**graph.reception, "qualification": refs["subject_qualification"],
            "archive": archive_ref, "audit": audit_ref}
        refs["subject_reception"] = graph.files.json(host + "/reception.json", reception)
        reservation_ref = transported("reservation.json", lane["slot_reservation"])
        projection_ref = transported("projection.json", lane["minimal_owned_observations"])
        refs["worker_lane_admission"] = graph.files.json(host + "/lane.json", {
            **lane, "slot_reservation": reservation_ref, "minimal_owned_observations": projection_ref})
        authorization = {**graph.authorization, "artifacts": refs}
        authorization_ref = graph.files.json(host + "/authorization.json", authorization)
        assert native.validate_receipt(authorization_ref["path"], {contract.SCOPE}, runtime=False, now=1000.0) == authorization
        assert refs["plan"] == graph.plan_ref and refs["artifact_aliases"] == graph.aliases_ref
        admissions.append(authorization)
    assert admissions[0]["artifacts"]["subject_reception"]["path"] != admissions[1]["artifacts"]["subject_reception"]["path"]
    assert file_digest(Path(graph.plan_ref["path"])) == graph.plan_ref["sha256"]
    assert file_digest(Path(graph.aliases_ref["path"])) == graph.aliases_ref["sha256"]


def test_rehashed_authorization_cannot_reuse_proofs_for_another_registered_session(graph):
    other = next(cell for cell in contract.REGISTERED_CELLS.values()
                 if cell["subject_id"] == graph.subject["subject_id"]
                 and cell["session_id"] != graph.binding["session_id"])
    authorization = {**graph.authorization, **other,
        "remote_root": "/scratch/NEUTRAL/" + contract.SCOPE + "-" + other["session_id"]}
    assert native.selected_identity(authorization) == (other["model"], other["session_id"])
    authorization_ref = graph.files.json("NEUTRAL-cross-session-authorization.json", authorization)
    with pytest.raises(InfrastructureError, match="matrix proof"):
        native.validate_receipt(authorization_ref["path"], {contract.SCOPE}, runtime=False, now=1000.0)


@pytest.mark.parametrize("field", ["qualification_ref", "reception_ref"])
def test_plan_cannot_embed_a_future_received_subject_reference(graph, field):
    plan = copy.deepcopy(graph.plan)
    plan["subject_bindings"][graph.subject["subject_id"]][field] = graph.qualification_ref
    with pytest.raises(InfrastructureError):
        contract.validate_plan(plan)


def test_old_plan_schema_is_not_silently_reinterpreted(graph):
    plan = copy.deepcopy(graph.plan)
    plan["schema"] = "hpc-forest-matrix15-native-max-plan-v1"
    with pytest.raises(InfrastructureError):
        contract.validate_plan(plan)


@pytest.mark.parametrize("target", ["plan", "aliases", "qualification", "archive", "audit", "reception", "proof", "authorization"])
def test_alias_table_refuses_every_hash_dependency_back_edge(graph, target):
    targets = {"plan": graph.plan_ref, "aliases": graph.aliases_ref, "qualification": graph.qualification_ref,
        "archive": graph.reception["archive"], "audit": graph.reception["audit"], "reception": graph.reception_ref,
        "proof": graph.authorization["artifacts"]["transport_admission"], "authorization": graph.authorization_ref}
    ref = targets[target]
    aliases = copy.deepcopy(graph.aliases)
    aliases["entries"].append({"kind": "file", "canonical_path": ref["path"], "sha256": ref["sha256"],
        "windows_path": ref["path"] if os.name == "nt" else "C:/NEUTRAL/forbidden-" + target,
        "arm_path": ref["path"] if os.name != "nt" else "/scratch/NEUTRAL/forbidden-" + target})
    native.validate_aliases(aliases, graph.binding["source_zip_sha256"])
    with pytest.raises(InfrastructureError):
        native.validate_alias_dependencies(aliases, graph.plan_ref, graph.aliases_ref, graph.downstream)


@pytest.mark.parametrize("field", ["plan_sha256", "source_zip_sha256", "subject_id"])
def test_real_qualification_for_another_plan_source_or_subject_is_rejected(graph, field):
    qualification = copy.deepcopy(graph.qualification)
    qualification[field] = contract.SUBJECTS[-1] if field == "subject_id" else "f" * 64
    qualification_ref = graph.files.json("NEUTRAL-wrong-" + field + ".json", qualification)
    with pytest.raises(InfrastructureError):
        verify(graph, qualification=qualification, qualification_ref=qualification_ref)


@pytest.mark.parametrize("missing", ["qualification", "reception"])
def test_absent_qualification_or_reception_is_rejected(graph, missing):
    with pytest.raises(InfrastructureError):
        verify(graph, **{missing: {}})


def test_received_qualification_ref_must_be_the_same_real_file(graph):
    duplicate_ref = graph.files.json("NEUTRAL-duplicate-qualification.json", graph.qualification)
    assert duplicate_ref["sha256"] == graph.qualification_ref["sha256"]
    with pytest.raises(InfrastructureError):
        verify(graph, qualification_ref=duplicate_ref)


def test_supplied_qualification_must_equal_the_sha_bound_received_bytes(graph):
    qualification = copy.deepcopy(graph.qualification)
    qualification["allocation"]["job_id"] = "900002"
    with pytest.raises(InfrastructureError):
        verify(graph, qualification=qualification)


@pytest.mark.parametrize("changed", ["qualification", "reception", "audit", "archive"])
def test_changed_received_artifact_bytes_fail_full_admission(graph, changed):
    refs = {"qualification": graph.qualification_ref, "reception": graph.reception_ref,
            "audit": graph.reception["audit"], "archive": graph.reception["archive"]}
    Path(refs[changed]["path"]).write_bytes(b"NEUTRAL changed after hashing")
    with pytest.raises(InfrastructureError):
        validate(graph)


def test_missing_reception_file_cannot_be_admitted_from_the_plan(graph):
    Path(graph.reception_ref["path"]).unlink()
    with pytest.raises(InfrastructureError):
        validate(graph)


@pytest.mark.parametrize("changed", ["prepared-bytes", "prepared-inventory", "received-qualification-hash"])
def test_real_directory_inventory_and_received_hash_remain_enforced(graph, changed):
    if changed == "prepared-bytes":
        root, _ = native.directory_artifact(graph.subject["official_preparation_path"],
            subject_id=graph.subject["subject_id"], role="official", aliases=graph.aliases,
            preparation_manifest=graph.preparation, preparation_manifest_sha256=graph.binding["preparation_manifest_sha256"])
        (root / "source/fixture.txt").write_bytes(b"NEUTRAL changed prepared bytes")
        with pytest.raises(InfrastructureError):
            verify(graph)
    elif changed == "prepared-inventory":
        qualification = copy.deepcopy(graph.qualification)
        qualification["prepared_files"]["source/fixture.txt"] = "f" * 64
        qualification_ref = graph.files.json("NEUTRAL-wrong-inventory.json", qualification)
        archive_ref = graph.files.archive("NEUTRAL-wrong-inventory.zip", {"qualification.json": qualification_ref})
        audit_ref = graph.files.json("NEUTRAL-wrong-inventory-audit.json", {**graph.audit,
            "qualification_sha256": qualification_ref["sha256"], "archive_sha256": archive_ref["sha256"]})
        reception = {**graph.reception, "qualification": qualification_ref, "archive": archive_ref, "audit": audit_ref}
        with pytest.raises(InfrastructureError, match="Qualified directory"):
            verify(graph, qualification=qualification, qualification_ref=qualification_ref, reception=reception)
    else:
        reception = copy.deepcopy(graph.reception)
        reception["qualification"]["sha256"] = "f" * 64
        with pytest.raises(InfrastructureError):
            verify(graph, reception=reception)
