"""Neutral tests only; no fabricated Q report is consumed as a real qualification."""
from __future__ import annotations

import json

import pytest

import q_upstream as upstream


def spec_file(tmp_path, value, *, changes=None):
    evidence = tmp_path / "NEUTRAL-upstream.json"
    raw = json.dumps(value).encode()
    evidence.write_bytes(raw)
    spec = {"schema": "hpc-forest-matrix15-Q-upstream-static-inputs-v1", "qualification_job_id": "755488",
            "files": [{"role": "NEUTRAL-Q-data-not-a-qualification", "reference": {
                "path": str(evidence), "sha256": upstream.sha(raw)}, "arm_path": "/NEUTRAL/Q/report.json"}]}
    if changes:
        changes(spec)
    path = tmp_path / "NEUTRAL-inputs.json"
    path.write_text(json.dumps(spec), encoding="utf8")
    return path, evidence


def test_neutral_Q_aggregate_is_read_as_bytes_without_promoting_its_flags(tmp_path):
    path, _ = spec_file(tmp_path, {"schema": "hpc-forest-matrix15-baseline-qualification-result-v1",
                                 "qualification_complete": False, "native_authorization": False})
    rows = upstream.read_spec(path)
    assert len(rows) == 1 and "verified" not in rows[0]
    assert json.loads(rows[0]["raw"])["qualification_complete"] is False


def test_explicit_null_native_placeholder_is_not_a_downstream_dependency(tmp_path):
    path, _ = spec_file(tmp_path, {"schema": "NEUTRAL-Q", "native_plan_ref": None})
    assert len(upstream.read_spec(path)) == 1


@pytest.mark.parametrize("schema", sorted(upstream.NATIVE_DOWNSTREAM_SCHEMAS))
def test_native_downstream_products_are_refused_as_upstream_aliases(tmp_path, schema):
    path, _ = spec_file(tmp_path, {"schema": schema})
    with pytest.raises(ValueError, match="upstream alias"):
        upstream.read_spec(path)


@pytest.mark.parametrize("field", ["native_plan_ref", "native_plan_sha256", "native_authorization_ref"])
def test_nested_native_dependencies_refused(tmp_path, field):
    path, _ = spec_file(tmp_path, {"schema": "NEUTRAL-Q", "evidence": [{field: "NEUTRAL"}]})
    with pytest.raises(ValueError, match="downstream native"):
        upstream.read_spec(path)


@pytest.mark.parametrize("change", ["sha", "arm_relative", "arm_traversal", "duplicate", "job", "extra"])
def test_changed_sha_unsafe_paths_duplicate_job_and_extra_fields_refused(tmp_path, change):
    def mutate(spec):
        row = spec["files"][0]
        if change == "sha":
            row["reference"]["sha256"] = "f" * 64
        elif change == "arm_relative":
            row["arm_path"] = "relative/Q.json"
        elif change == "arm_traversal":
            row["arm_path"] = "/NEUTRAL/../escape.json"
        elif change == "duplicate":
            spec["files"].append(row)
        elif change == "job":
            spec["qualification_job_id"] = "999"
        else:
            row["native_plan_sha256"] = "f" * 64
    path, _ = spec_file(tmp_path, {"schema": "NEUTRAL-Q"}, changes=mutate)
    with pytest.raises(ValueError):
        upstream.read_spec(path)


def test_changed_actual_file_rejected(tmp_path):
    path, evidence = spec_file(tmp_path, {"schema": "NEUTRAL-Q"})
    evidence.write_bytes(b"NEUTRAL changed")
    with pytest.raises(ValueError, match="bytes changed"):
        upstream.read_spec(path)
