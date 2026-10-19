"""Pure first-batch checkpoint/release fixtures, never production admission receipts."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from hpc_forest import native_r2max
from hpc_forest.core import InfrastructureError, atomic_json

SPEC = importlib.util.spec_from_file_location(
    "NEUTRAL_r2e_first_batch_runner", Path(__file__).parents[1] / "examples/marathon22/primes_native_max.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def fixture(tmp_path, status="build_failed"):
    output = tmp_path / "NEUTRAL-results"
    output.mkdir()
    authorization = {"model": "gpt-6-astra", "effort": "max", "session_id": native_r2max.CELLS["gpt-6-astra"],
                     "job_id": "900000", "remote_root": "/scratch_p/NEUTRAL", "expires_at": 400,
                     "artifacts": {"source_zip": {"sha256": "1" * 64}, "plan": {"sha256": "2" * 64}}}
    evaluation = output / "NEUTRAL-evaluation.json"
    atomic_json(evaluation, {"experiment_id": "NEUTRAL-trial", "outcome": {"status": status}, "never_model_input": True})
    calls = []
    for char, mother in (("3", True), ("4", False)):
        request = output / ("NEUTRAL-request-" + char + ".json")
        atomic_json(request, {"nonce": char * 32, "meta_role": "mother-preparation" if mother else None})
        projection = output / ("NEUTRAL-projection-" + char + ".json")
        atomic_json(projection, {"NEUTRAL": "fixture only, not production admission"})
        calls.append({"request": runner.bound_ref(request), "invocation": runner.bound_ref(projection),
                      "process": runner.bound_ref(projection), "private_cli_review_required": True,
                      "private_cli_argv_verified": False,
                      "private_cli_records": {key: char * 64 for key in ("invocation_sha256", "process_sha256", "argv_sha256",
                                                                 "skill_override_sha256", "task_cli_policy_sha256")}})
    first = {"verified": True, "technical_errors_found": False, "invocation_unknown": False,
             "first_normal_delivered_call": calls[1], "first_real_evaluation": {"experiment_id": "NEUTRAL-trial", "status": status},
             "evaluation_snapshot": runner.bound_ref(evaluation), "all_started_calls_reconciled": calls,
             "private_cli_review_required": True, "private_cli_argv_verified": False}
    atomic_json(output / "premier-demarrage-verifie.json", first)
    snapshot = {"schema": "NEUTRAL-fixture-snapshot", "first_start_receipt": runner.bound_ref(output / "premier-demarrage-verifie.json"),
                "evaluation_snapshot": runner.bound_ref(evaluation)}
    path = output / "NEUTRAL-paused-snapshot.json"
    atomic_json(path, snapshot)
    snapshot["self_ref"] = runner.bound_ref(path)
    return output, authorization, first, snapshot


def make_release(output, authorization, first, snapshot):
    identity = native_r2max.cell_binding(authorization)
    audit = {"schema": "hpc-forest-r2e-private-cli-audit-digest-projection-v1", "verified": True, **identity,
             "first_start_receipt_sha256": snapshot["first_start_receipt"]["sha256"],
             "paused_snapshot_sha256": snapshot["self_ref"]["sha256"], "call_bindings": runner.private_call_bindings(first),
             "all_private_raws_received_and_hashed": True, "argv_matches_projections_and_local_policy": True,
             "cli_diagnostics_clean": True, "raw_skill_paths_exported": False,
             "private_review_receipt_sha256": "f" * 64}
    audit_path = output / "NEUTRAL-private-audit-digest-projection.json"
    atomic_json(audit_path, audit)
    return {"schema": "hpc-forest-r2e-first-batch-release-v1", "verified": True, **identity,
            "paused_snapshot": snapshot["self_ref"], "first_start_receipt": snapshot["first_start_receipt"],
            "evaluation_snapshot": snapshot["evaluation_snapshot"], "private_cli_audit": runner.bound_ref(audit_path),
            "no_replay": True, "new_model_or_budget_authorized": False}


@pytest.mark.parametrize("status", ["valid", "incorrect", "build_failed", "runtime_failed"])
def test_exact_audited_release_does_not_require_a_gain_or_erase_negative(tmp_path, status):
    output, authorization, first, snapshot = fixture(tmp_path, status)
    release = make_release(output, authorization, first, snapshot)
    runner.validate_first_batch_release(release, snapshot, first, authorization)
    assert first["first_real_evaluation"]["status"] == status


@pytest.mark.parametrize("field", ["model", "effort", "session_id", "job_id", "source_zip_sha256",
                                   "plan_sha256", "paused_snapshot", "first_start_receipt", "evaluation_snapshot"])
def test_any_unrelated_release_stays_closed(tmp_path, field):
    output, authorization, first, snapshot = fixture(tmp_path)
    release = make_release(output, authorization, first, snapshot)
    release[field] = "NEUTRAL-mismatch"
    with pytest.raises(InfrastructureError):
        runner.validate_first_batch_release(release, snapshot, first, authorization)


def test_no_private_actual_audit_cannot_release(tmp_path):
    output, authorization, first, snapshot = fixture(tmp_path)
    release = make_release(output, authorization, first, snapshot)
    Path(release["private_cli_audit"]["path"]).unlink()
    with pytest.raises(InfrastructureError):
        runner.validate_first_batch_release(release, snapshot, first, authorization)


def test_changed_private_call_digest_refused_even_with_new_audit_file_SHA(tmp_path):
    output, authorization, first, snapshot = fixture(tmp_path)
    release = make_release(output, authorization, first, snapshot)
    audit_path = Path(release["private_cli_audit"]["path"])
    audit = runner.read_json(audit_path)
    audit["call_bindings"]["3" * 32]["argv_sha256"] = "a" * 64
    atomic_json(audit_path, audit)
    release["private_cli_audit"] = runner.bound_ref(audit_path)
    with pytest.raises(InfrastructureError, match="Actual hash-linked"):
        runner.validate_first_batch_release(release, snapshot, first, authorization)


def controller_fixture():
    return SimpleNamespace(db=SimpleNamespace(get=lambda key: 300), config={"budget": {"confirmation_seconds": 120}},
                           run=lambda **kwargs: pytest.fail("No new batch during passive wait"))


def test_absent_release_waits_only_remaining_search_budget_and_creates_no_error_response(tmp_path):
    output, authorization, first, _ = fixture(tmp_path)
    clock = [100.0]
    sleeps = []
    def sleep(seconds):
        assert 0 <= seconds <= 2
        sleeps.append(seconds)
        clock[0] += seconds
    assert runner.wait_first_batch_release(controller_fixture(), authorization, output, first,
                                            now=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep) is False
    assert sum(sleeps) == 80 and clock[0] == 180
    expired = runner.read_json(output / "premier-batch-attente-expiree.json")
    assert expired["next_batch_started"] is False and expired["budget_or_chronology_reset"] is False
    assert expired["model_error_or_response_fabricated"] is False
    assert not list(output.glob("*.response.json"))


def test_valid_release_after_real_checkpoint_resumes_only_unchanged_remaining_budget(tmp_path):
    output, authorization, first, _ = fixture(tmp_path)
    clock = [100.0]
    def sleep(seconds):
        snapshot_path = output / "premier-batch-en-attente.json"
        snapshot = runner.read_json(snapshot_path)
        snapshot["self_ref"] = runner.bound_ref(snapshot_path)
        release = make_release(output, authorization, first, snapshot)
        atomic_json(output / "autorisation-apres-premier-batch.json", release)
        clock[0] += seconds
    assert runner.wait_first_batch_release(controller_fixture(), authorization, output, first,
                                            now=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep) is True
    assert clock[0] == 102
    accepted = runner.read_json(output / "premier-batch-release-verifiee.json")
    assert accepted["budget_or_chronology_reset"] is False and accepted["replayed_claims"] == 0


def test_invalid_release_is_retained_and_budget_still_expires(tmp_path):
    output, authorization, first, _ = fixture(tmp_path)
    atomic_json(output / "autorisation-apres-premier-batch.json", {"NEUTRAL": "not an actual release"})
    clock = [100.0]
    assert runner.wait_first_batch_release(controller_fixture(), authorization, output, first,
                                            now=lambda: clock[0], monotonic=lambda: clock[0],
                                            sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)) is False
    assert len(list(output.glob("refus-release-*.json"))) == 1
    assert runner.read_json(output / "autorisation-apres-premier-batch.json") == {"NEUTRAL": "not an actual release"}


def test_pending_or_unreconciled_first_start_cannot_release(tmp_path):
    output, authorization, first, snapshot = fixture(tmp_path)
    release = make_release(output, authorization, first, snapshot)
    changed = copy.deepcopy(first)
    changed["verified"] = False
    with pytest.raises(InfrastructureError, match="Actual normal"):
        runner.validate_first_batch_release(release, snapshot, changed, authorization)


def test_budget_is_rechecked_after_validating_a_release(tmp_path, monkeypatch):
    output, authorization, first, _ = fixture(tmp_path)
    clock = [100.0]
    original = runner.validate_first_batch_release

    def slow_validation(*args):
        result = original(*args)
        clock[0] = 181.0
        return result

    def sleep(seconds):
        path = output / "premier-batch-en-attente.json"
        snapshot = runner.read_json(path)
        snapshot["self_ref"] = runner.bound_ref(path)
        atomic_json(output / "autorisation-apres-premier-batch.json", make_release(output, authorization, first, snapshot))
        clock[0] += seconds

    monkeypatch.setattr(runner, "validate_first_batch_release", slow_validation)
    assert runner.wait_first_batch_release(controller_fixture(), authorization, output, first,
                                            now=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep) is False
    assert not (output / "premier-batch-release-verifiee.json").exists()
