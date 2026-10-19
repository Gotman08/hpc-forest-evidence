"""Unit fixtures are never actual primary receipts or campaign proof."""
import copy
import io
import json
import tarfile

import inspect_archive
import pytest
import seal_closed_tree
import terminal_audit as audit


@pytest.fixture
def fixture_data(monkeypatch):
    binding = {key: "a" * 64 for key in audit.BINDING_FIELDS}
    binding.update(scope_id="hpc-forest-matrix15-native-max-r2", model="gpt-6-luna", subject_id="2020-quicksort",
                   effort="max", session_id="a" * 32, job_id="123", remote_root="/gpfs/scratch/unit-test")
    binding["cell_key"] = "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23"
    stored = {}

    def ref(name, value):
        result = {"path": name, "sha256": "b" * 64, "bytes": 1}
        stored[name] = value
        return result

    def primary(tool, arguments, value):
        return {"schema": "hpc-forest-primary-tool-observation-v1", "tool": tool, "arguments": arguments,
                "observed_at": 20, "response": {"isError": False, "structuredContent": value,
                "content": [{"type": "text", "text": json.dumps(value)}]}}

    costs = {"slots": 1, "tokens_used": 12, "exact_tokens_used": 12, "tokens_reserved": 0,
             "unknown_usage_calls": 0, "bounded_usage_calls": 0}
    policy = {key: "a" * 64 for key in ("invocation_sha256", "process_sha256", "argv_sha256", "skill_override_sha256", "task_cli_policy_sha256")}
    nonce = "c" * 32
    call = {"request": {"path": binding["remote_root"] + "/results-123/mailbox/requests/" + nonce + ".request.json"},
            "private_cli_records": policy, "invocation": {"sha256": "a" * 64}, "process": {"sha256": "a" * 64},
            "normal_delivered": True, "usage_exact": True, "exact_tokens": 12, "known_model_negative": False, "mother_phase": None,
            "mother_call": False}
    closed = [{"nonce": nonce, "mother_phase": None, "exact_tokens": 12, "known_model_negative": False}]
    no_performance = {"private_case_v2_claimed": False, "independent_raw_stdout_per_candidate_verified": False,
                      "independent_performance_audit_verified": False}
    final = {"schema": "hpc-forest-matrix15-first-start-v1", **binding, **no_performance, "protocol_id": "d" * 64,
             "verified": True, "technical_errors_found": False, "invocation_unknown": False, "blocking_reasons": [],
             "pending_first_real_evaluation": False, "all_started_calls_reconciled": [call],
             "usage_and_mother_reconciliation": {"budget_or_chronology_reset": False, "all_delivered_tokens_exact": 12,
                 "registry_costs": costs, "mother_claims": {}}}
    best = {"experiment_id": "baseline-e1", "epoch": 1, "evaluation_digest": "e" * 64}
    results = {"schema": "hpc-forest-matrix15-native-single-cell-v1", **binding, **no_performance,
               "pipeline_complete": True, "five_confirmations_verified": True, "other_cells_started": 0,
               "automatic_extension": False, "protocol_id": "d" * 64, "costs": costs,
               "mother": {"preparation": None, "synthesis": None}, "best_confirmed": best}
    confirmations = {"schema": "hpc-forest-matrix15-final-confirmations-v1", **binding, **no_performance,
                     "verified": True, "protocol_id": "d" * 64, "confirmation_repetitions": 5,
                     "interleaving_owner": "unchanged-Evaluator.confirm", "best_confirmed": best,
                     "evaluation_digests": {"baseline-e1": "e" * 64}, "command_stream_provenance": {"baseline-e1": [
                         {"path": binding["remote_root"] + "/results-123/stream.json", "sha256": "f" * 64, "bytes": 12,
                          "mode": "command-stream-v1", "verified": True, "operation": "build",
                          "individual_case_provenance_verified": False, "independent_performance_audit_verified": False}]}}
    bootstrap = {"schema": "hpc-forest-matrix15-bootstrap-result-v1", "binding": binding, "passed": True,
                 "admission_accepted": True, "native_child_launch_attempted": True, "native_child_returncode": 0,
                 "native_model_calls_before_authorization": 0, "finished_at": 10}
    private = {"schema": "hpc-forest-matrix15-private-first-batch-review-v1", **binding, "verified": True,
               "protocol_id": "d" * 64, "all_private_raws_received_and_hashed": True,
               "argv_matches_projections_and_local_policy": True, "cli_diagnostics_clean": True,
               "call_bindings": {nonce: {**policy, "invocation_projection_sha256": "a" * 64, "process_projection_sha256": "a" * 64}},
               "calls": closed, "exact_tokens_all_calls": 12}
    review = {"schema": "hpc-forest-matrix15-extension-first-batch-root-review-v1", "verified": True,
              "evidence_origin": "received", "first_binding": binding, "private_review_receipt_sha256": "b" * 64,
              "all_private_raws_received_and_hashed": True, "actual_arm_release_received": True}
    states = {"bootstrap": bootstrap, "results": results, "final_reconciliation": final, "confirmations": confirmations,
              "private": private, "review": review}
    paths = {"bootstrap": binding["remote_root"] + "-admission/bootstrap-result.json",
             "results": binding["remote_root"] + "/results-123/results.json",
             "final_reconciliation": binding["remote_root"] + "/results-123/reconciliation-finale-verifiee.json",
             "confirmations": binding["remote_root"] + "/results-123/confirmations-finales-verifiees.json"}
    artifacts = {}
    for key, path in paths.items():
        local = ref(key, states[key])
        args = {"remote_path": path, "local_path": key, "verify": True}
        transfer = {"ok": True, "transport": "scp", "verifie": True, "downloaded": path, "to": key, "bytes": 1,
                    "remote_sha256": "b" * 64, "empreinte_locale": "b" * 64, "empreinte_distante": "b" * 64}
        artifacts[key] = {"remote_ref": {"path": path, "sha256": "b" * 64}, "local_ref": local,
                          "transfer_receipt": ref(key + "-raw", primary("mcp__romeo__download_from_romeo", args, transfer))}
    status = {"ok": True, "job_id": "123", "state": "COMPLETED", "exit_code": "0:0", "finished": True,
              "scheduler_completed": True, "scheduler_success_observed": True}
    efficiency = {"ok": True, "found": True, "job_id": "123", "state": "COMPLETED", "exit_code": "0:0", "alloc_cpus": 4, "alloc_gpus": 0}
    value = {"schema": audit.INPUT_SCHEMA, "binding": binding, "artifacts": artifacts,
             "status_ref": ref("status", primary("mcp__romeo__job_status", {"job_id": "123"}, status)),
             "efficiency_ref": ref("efficiency", primary("mcp__romeo__job_efficiency", {"job_id": "123"}, efficiency)),
             "first_batch_private_audit": ref("private", private), "first_batch_root_review": ref("review", review)}
    monkeypatch.setattr(audit, "checked", lambda reference: stored[reference["path"]])
    return value, states, stored


def test_bookkeeping_positive_keeps_performance_false(fixture_data):
    receipt = audit.validate(fixture_data[0])
    assert receipt["verified"] is True
    assert receipt["independent_performance_audit_verified"] is False
    assert receipt["all_terminal_raws_received_and_hashed"] is False
    assert receipt["exact_tokens_all_calls"] == 12


@pytest.mark.parametrize("artifact,key,value", [("results", "pipeline_complete", False), ("results", "five_confirmations_verified", False),
    ("results", "independent_performance_audit_verified", True), ("final_reconciliation", "technical_errors_found", True),
    ("final_reconciliation", "invocation_unknown", True), ("confirmations", "confirmation_repetitions", 3),
    ("bootstrap", "passed", False), ("bootstrap", "native_child_returncode", 1), ("private", "verified", False),
    ("review", "actual_arm_release_received", False)])
def test_required_terminal_proof(fixture_data, artifact, key, value):
    fixture_data[1][artifact][key] = value
    with pytest.raises(audit.Refusal):
        audit.validate(fixture_data[0])


def test_new_call_requires_private_audit(fixture_data):
    final = fixture_data[1]["final_reconciliation"]
    extra = copy.deepcopy(final["all_started_calls_reconciled"][0])
    extra["request"]["path"] = extra["request"]["path"].replace("c" * 32, "f" * 32)
    final["all_started_calls_reconciled"].append(extra)
    with pytest.raises(audit.Refusal, match="unaudited"):
        audit.validate(fixture_data[0])


def test_terminal_unknown_tokens_refused(fixture_data):
    fixture_data[1]["results"]["costs"]["unknown_usage_calls"] = 1
    with pytest.raises(audit.Refusal, match="unresolved"):
        audit.validate(fixture_data[0])


def test_actual_primary_payload_disagreement_refused(fixture_data):
    fixture_data[2]["status"]["response"]["structuredContent"]["exit_code"] = "1:0"
    with pytest.raises(audit.Refusal, match="disagree"):
        audit.validate(fixture_data[0])


def test_missing_scp_receipt_refused(fixture_data):
    fixture_data[2]["confirmations-raw"]["response"]["structuredContent"]["verifie"] = False
    fixture_data[2]["confirmations-raw"]["response"]["content"][0]["text"] = json.dumps(
        fixture_data[2]["confirmations-raw"]["response"]["structuredContent"])
    with pytest.raises(audit.Refusal, match="SCP"):
        audit.validate(fixture_data[0])


def test_local_evidence_changed_refused(tmp_path):
    path = tmp_path / "proof.json"
    path.write_text('{"value": 1}', encoding="utf8")
    reference = audit.local_ref(path)
    path.write_text('{"value": 2}', encoding="utf8")
    with pytest.raises(audit.Refusal, match="changed"):
        audit.checked(reference)


def test_duplicate_json_key_refused():
    with pytest.raises(audit.Refusal, match="Duplicate"):
        audit.parse(b'{"verified": false, "verified": true}')


def test_mother_claim_without_call_refused(fixture_data):
    fixture_data[1]["results"]["mother"]["synthesis"] = {"status": "started_without_final_response", "model_calls": 1}
    with pytest.raises(audit.Refusal, match="Mother"):
        audit.validate(fixture_data[0])


def test_source_tree_seal_stable_and_outside(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.bin").write_bytes(b"preserved")
    receipt = seal_closed_tree.seal(source, tmp_path / "seal")
    assert receipt["tree_stability_verified"] is True
    assert receipt["source_files_modified"] is False
    assert (source / "data.bin").read_bytes() == b"preserved"
    with pytest.raises(ValueError):
        seal_closed_tree.seal(source, source / "bad")
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        seal_closed_tree.seal(source, outside / ".." / "source" / "bad-lexical")
    assert not (source / "bad-lexical").exists()


def test_source_tree_seal_links_refused(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "outside"
    target.write_bytes(b"target")
    try:
        (source / "link").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="Symlink"):
        seal_closed_tree.seal(source, tmp_path / "seal")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "p/../escape", "p\\escape", "other/data", "p//escape", "p/./escape"])
def test_virtual_tar_unsafe_names_refused(tmp_path, name):
    archive = tmp_path / "data.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo(name)
        member.size = 1
        stream.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        inspect_archive.inspect(archive, audit.sha(archive.read_bytes()), "/gpfs/scratch/test", "p")


def test_virtual_tar_file_directory_collision_refused(tmp_path):
    archive = tmp_path / "data.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for name in ("p/a/b", "p/a"):
            member = tarfile.TarInfo(name)
            member.size = 1
            stream.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="collision"):
        inspect_archive.inspect(archive, audit.sha(archive.read_bytes()), "/gpfs/scratch/test", "p")
