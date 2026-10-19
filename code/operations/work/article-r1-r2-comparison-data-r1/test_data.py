import csv
import json
import math
import statistics

import build_data as build
import pytest


@pytest.fixture(scope="module")
def dataset():
    return build.build("2026-10-19T11:50:17+00:00")


def test_all_historical_rows_preserved_and_missing_r2_is_not_zero(dataset):
    assert len(dataset["cells"]) == 60
    assert sum(cell["r1_confirmed"] for cell in dataset["cells"]) == 60
    zero_gains = [cell for cell in dataset["cells"] if cell["r1_gain_fraction"] == 0]
    assert len(zero_gains) == 11
    assert all(cell["r1_baseline_retained"] and cell["r1_speedup"] == 1 for cell in zero_gains)
    missing = [cell for cell in dataset["cells"] if not cell["r2_initial_batch_received"]]
    assert len(missing) == 59
    assert all(cell[key] is None for cell in missing for key in ("r2_initial_reference_seconds", "r2_initial_candidate_seconds",
               "r2_source_final_reference_seconds", "r2_source_final_candidate_seconds", "r2_known_exact_tokens"))


def test_no_causal_or_independent_performance_promotion(dataset):
    assert not any(cell["scientifically_admitted_pair"] or cell["r2_scientifically_admitted_gain"] for cell in dataset["cells"])
    assert dataset["coverage"]["scientifically_admitted_pairs"] == 0
    assert dataset["matched_cell"]["causal_R1_R2_comparison_admitted"] is False
    assert dataset["matched_cell"]["equivalent_realized_search_effort"] is False
    assert dataset["matched_cell"]["r2_confirmation_stream_review"]["independent_performance_audit_verified"] is False
    assert dataset["matched_cell"]["timeline"]["budget_or_chronology_reset"] is False


def test_exact_historical_cohort_and_distinct_realized_effort(dataset):
    matched = dataset["matched_cell"]
    assert matched["r1_job_id"] == "748259"
    assert matched["r2_job_id"] == "755562"
    assert matched["accounting"]["r1_known_exact_tokens"] == 261707
    assert matched["accounting"]["r1_native_calls"] == 10
    assert matched["accounting"]["r2_known_exact_tokens"] == 32765
    assert matched["accounting"]["r2_delivered_exact_calls"] == 2
    assert matched["same_declared_checker_contract"] is True
    assert matched["same_common_budget_limits"] is True
    assert matched["compute_node_equal"] is False
    assert matched["controller_implementation_equal"] is False


def test_samples_stages_and_within_run_normalization(dataset):
    assert sum(group["n"] for group in dataset["series"]) == 26
    assert [group["n"] for group in dataset["series"]] == [5, 5, 3, 3, 5, 5]
    for group in dataset["series"]:
        assert group["mean_seconds"] == statistics.mean(group["samples_seconds"])
        assert group["sample_sd_seconds"] == statistics.stdev(group["samples_seconds"])
        assert math.isclose(group["normalized_mean"], group["mean_seconds"] / group["reference_mean_seconds"])
        assert group["normalized_samples"] == [number / group["reference_mean_seconds"] for number in group["samples_seconds"]]


def test_csv_roundtrip_and_manifest_excludes_self(tmp_path, dataset):
    output = tmp_path / "public"
    build.write_outputs(dataset, output)
    manifest = json.loads((output / "FILES.sha256.json").read_text())
    assert set(manifest) == {"comparison.json", "matrix15-comparison.csv", "timing-samples.csv"}
    for name, ref in manifest.items():
        raw = (output / name).read_bytes()
        assert len(raw) == ref["bytes"]
        assert build.sha(raw) == ref["sha256"]
    with (output / "matrix15-comparison.csv").open(newline="", encoding="utf8") as stream:
        cells = list(csv.DictReader(stream))
    assert len(cells) == 60
    assert sum(row["r2_initial_reference_seconds"] == "" for row in cells) == 59
    assert sum(row["r1_speedup"] == "1.0" for row in cells) == 11
    for path in output.iterdir():
        raw = path.read_bytes()
        assert b"/gpfs/" not in raw and b"C:\\" not in raw and b'"argv"' not in raw
