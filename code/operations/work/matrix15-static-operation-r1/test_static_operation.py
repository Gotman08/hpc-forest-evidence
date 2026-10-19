"""Static real-byte/neutral-mutation tests; no model, allocation, CLI or candidate."""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil

import pytest
from hpc_forest import matrix15_contract as contract
from hpc_forest import native_matrix15 as native
from hpc_forest.core import InfrastructureError, digest, file_digest

import produce_static as producer

OUT = producer.OUTPUT
SHARED = OUT / "shared-windows"
STATIC = json.loads((OUT / "STATICS.json").read_bytes())
ALIASES = json.loads((SHARED / "artifact-aliases.json").read_bytes())
PLAN = json.loads((SHARED / "plan-60-v2.json").read_bytes())
PROJECTION = json.loads((SHARED / "preparation-196.json").read_bytes())


def test_real_plan_has_sixty_max_cells_and_keeps_all_downstream_receipts_null():
    native.validate_aliases(ALIASES, producer.NATIVE_ZIP_SHA)
    validated = contract.validate_plan(PLAN)
    assert len(validated["cells"]) == len({cell["session_id"] for cell in validated["cells"]}) == 60
    assert all(cell["effort"] == "max" and cell["subject_id"] != "2020-primes" for cell in validated["cells"])
    assert all(row["qualification_ref"] is row["reception_ref"] is None for row in validated["subject_bindings"].values())
    native.validate_alias_dependencies(ALIASES, STATIC["artifacts"]["plan"], STATIC["artifacts"]["artifact_aliases"], [])


def test_projection_is_explicit_and_exact_original_records_and_assets():
    upstream = native.read_json(SHARED / "evidence/original-preparation.json")
    receipt = native.read_json(OUT / "PROJECTION-PREPARATION-196.json")
    assert file_digest(SHARED / "evidence/original-preparation.json") == producer.ORIGINAL_PREP_SHA
    assert PROJECTION["schema"] == "hpc-forest-matrix15-preparation-static-projection-v1"
    assert len(PROJECTION["files"]) == 196
    assert set(PROJECTION["records"]) == set(contract.SUBJECTS)
    assert all(PROJECTION["records"][subject] == upstream["records"][subject] for subject in contract.SUBJECTS)
    assert all(upstream["files"][name] == checksum for name, checksum in PROJECTION["files"].items())
    assert set(receipt["excluded_original_files"]) == set(upstream["files"]) - set(PROJECTION["files"])
    assert receipt["actual_Q_cold_audit"] is None
    assert receipt["new_or_independently_requalified_content_claimed"] is False
    assert not any("reference-build" in name or "calibration-build" in name for name in PROJECTION["files"])
    for subject, row in PLAN["subject_bindings"].items():
        assert row["preparation_sha256"] == digest(upstream["records"][subject])


@pytest.mark.parametrize("subject", contract.SUBJECTS)
def test_every_official_source_validation_directory_is_locally_byte_exact(subject):
    for role, canonical in (("official", PLAN["subject_bindings"][subject]["official_preparation_path"]),
                            ("source", PROJECTION["records"][subject]["prepared"]["source"]),
                            ("validation", PROJECTION["records"][subject]["prepared"]["validation"])):
        root, files = native.directory_artifact(canonical, subject_id=subject, role=role,
            preparation_manifest=PROJECTION, preparation_manifest_sha256=STATIC["artifacts"]["preparation_manifest"]["sha256"],
            aliases=ALIASES, platform="windows", verify=True)
        assert root.is_dir() and files


@pytest.mark.parametrize("mutation", ["asset_changed", "extra_member", "old_binary_imported", "missing_asset"])
def test_projection_directory_refuses_changed_extra_missing_or_old_build_members(tmp_path, mutation):
    subject = "2020-quicksort"
    temporary = tmp_path / "NEUTRAL-official-copy"
    shutil.copytree(SHARED / "prepared" / subject, temporary)
    aliases = copy.deepcopy(ALIASES)
    entry = next(entry for entry in aliases["entries"] if entry.get("subject_id") == subject and entry.get("role") == "official")
    entry["windows_path"] = str(temporary)
    if mutation == "asset_changed":
        (temporary / "source/Makefile").write_bytes(b"NEUTRAL changed asset; never executed")
    elif mutation == "extra_member":
        (temporary / "validation/NEUTRAL-extra.data").write_bytes(b"NEUTRAL extra")
    elif mutation == "old_binary_imported":
        (temporary / "reference-build").mkdir()
        (temporary / "reference-build/solution").write_bytes(b"NEUTRAL surrogate; no executable content")
    else:
        (temporary / "validation/contract.json").unlink()
    with pytest.raises(InfrastructureError):
        native.directory_artifact(PLAN["subject_bindings"][subject]["official_preparation_path"],
            subject_id=subject, role="official", preparation_manifest=PROJECTION,
            preparation_manifest_sha256=STATIC["artifacts"]["preparation_manifest"]["sha256"],
            aliases=aliases, platform="windows", verify=True)


def test_real_native_runtime_is_127_parent_files_and_sol_pilot_is_rehashed_through_static_aliases():
    artifacts = STATIC["artifacts"]
    source = native.artifact(artifacts["source_zip"], aliases=ALIASES)
    runtime = native.artifact(artifacts["runtime_manifest"], aliases=ALIASES)
    assert file_digest(source) == producer.NATIVE_ZIP_SHA
    assert len(native.read_json(runtime)) == 127
    native.verify_runtime(source, runtime)
    pilot = native.verify_primes_release(native.artifact(artifacts["primes_release"], aliases=ALIASES),
        read_ref=lambda ref: native.artifact(ref, aliases=ALIASES))
    assert pilot["model"] == "gpt-6.1-sol" and pilot["exact_known_native_calls"] == 3


def test_drafts_are_explicitly_unadmitted_and_host_static_refs_agree():
    windows = native.read_json(OUT / "STATIC-ARTIFACTS-WINDOWS.json")
    arm = native.read_json(OUT / "STATIC-ARTIFACTS-ARM.json")
    assert set(windows) == set(arm) == set(STATIC["artifacts"])
    assert all(windows[key]["sha256"] == arm[key]["sha256"] for key in windows)
    assert arm["plan"]["path"] == producer.SHARED_ARM + "/plan-60-v2.json"
    for host in ("ARM", "WINDOWS"):
        draft = native.read_json(OUT / ("AUTHORIZATION-DRAFT-" + host + ".json"))
        assert set(draft) == native.AUTHORIZATION_FIELDS
        assert draft["verified"] is False and draft["job_id"] is None and draft["expires_at"] is None
        assert draft["model"] == "gpt-6-luna" and draft["subject_id"] == "2020-quicksort" and draft["effort"] == "max"
        assert any(ref is None for ref in draft["artifacts"].values())
        with pytest.raises(InfrastructureError):
            native.validate_receipt(OUT / ("AUTHORIZATION-DRAFT-" + host + ".json"), {contract.SCOPE})


def test_plan_or_table_or_final_proofs_cannot_enter_upstream_aliases():
    for forbidden in (STATIC["artifacts"]["plan"], STATIC["artifacts"]["artifact_aliases"]):
        aliases = copy.deepcopy(ALIASES)
        aliases["entries"].append({"kind": "file", "canonical_path": forbidden["path"],
            "windows_path": forbidden["path"], "arm_path": "/NEUTRAL/downstream.json", "sha256": forbidden["sha256"]})
        with pytest.raises(InfrastructureError):
            native.validate_alias_dependencies(aliases, STATIC["artifacts"]["plan"], STATIC["artifacts"]["artifact_aliases"], [])


def test_native_harness_bytes_remain_distinct_from_Q_but_json_equal():
    native_harness = SHARED / "harness-mixed.json"
    q_harness = producer.QPACKAGE / "harness-mixed.json"
    assert file_digest(native_harness) == contract.HARNESS_SHA256
    assert native_harness.read_bytes() != q_harness.read_bytes()
    assert json.loads(native_harness.read_bytes()) == json.loads(q_harness.read_bytes())


@pytest.mark.parametrize("subject", contract.SUBJECTS)
def test_each_actual_subject_config_passes_unchanged_scientific_runner_guard(subject):
    spec = importlib.util.spec_from_file_location("NEUTRAL_static_runner", producer.PARENT / "examples/marathon22/forest_matrix15.py")
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    cell = next(row for row in PLAN["cells"] if row["subject_id"] == subject and row["model"] == "gpt-6-luna")
    row = PLAN["subject_bindings"][subject]
    binding = {**cell, "scope_id": contract.SCOPE, "job_id": "999", "remote_root": "/NEUTRAL/not-a-real-allocation",
        "source_zip_sha256": producer.NATIVE_ZIP_SHA, "plan_sha256": STATIC["artifacts"]["plan"]["sha256"],
        "preparation_manifest_sha256": STATIC["artifacts"]["preparation_manifest"]["sha256"],
        "r1_contract_sha256": row["r1_contract_ref"]["sha256"]}
    result = runner.settings_for_cell(row["config"], PROJECTION["records"][subject]["prepared"],
        native.read_json(SHARED / "harness-mixed.json"), binding, "/NEUTRAL/mailbox", "NEUTRAL-target",
        STATIC["artifacts"]["runtime_manifest"]["sha256"])
    assert result["codex"]["model"] == "gpt-6-luna" and result["codex"]["reasoning_effort"] == "max"
    assert result["codex"]["session_id"] == cell["session_id"]
    assert result["protocol"] == row["config"]["protocol"]
    assert result["budget"]["wall_seconds"] == 1800
    assert result["budget"]["generation_admission"]["minimum_episode_seconds"] == 600.0
