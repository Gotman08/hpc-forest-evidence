"""Keep the initial native batch reproducible and its public claims bounded."""
import copy
import json
import statistics
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.native_first import validate, verify
from tools.recompute import EvidenceError, load_json

ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT / "evidence/native-first-batch-2026-10-19/first-batch.json"


def objects(value, path=()):
    """Visit every public object, including objects nested in arrays."""
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from objects(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from objects(item, path + (index,))


def at(value, path):
    for part in path:
        value = value[part]
    return value


class NativeFirstTests(unittest.TestCase):
    def setUp(self):
        self.value = load_json(PROJECTION.read_text(encoding="utf-8"))

    def reject_change(self, path, bad):
        value = copy.deepcopy(self.value)
        at(value, path[:-1])[path[-1]] = bad
        with self.assertRaises(EvidenceError):
            validate(value)

    def test_validate_and_verify_recalculate_the_initial_batch(self):
        summary = validate(self.value)
        self.assertEqual(verify(ROOT), summary)
        self.assertEqual(summary["cell"], self.value["cell"])
        for key, expected in (("candidate_samples", 3), ("reference_samples", 3),
                              ("delivered_calls", 2), ("registry_slots", 3),
                              ("exact_tokens_used", 32765)):
            with self.subTest(key=key):
                self.assertEqual(summary[key], expected)
        candidate = statistics.mean(self.value["initial_search"]["samples_seconds"])
        reference = statistics.mean(self.value["contemporary_reference"]["samples_seconds"])
        self.assertEqual(summary["recorded_search_score"], 0.5338473950146169)
        self.assertAlmostEqual(summary["initial_mean_ratio"], reference / candidate, places=14)
        self.assertAlmostEqual(summary["initial_runtime_reduction_fraction"],
                               1 - candidate / reference, places=14)

    def test_reject_extra_and_missing_fields_in_every_public_object(self):
        for path, original in objects(self.value):
            with self.subTest(path=path, mutation="extra"):
                value = copy.deepcopy(self.value)
                at(value, path)["private_unpublished_field"] = "not public evidence"
                with self.assertRaises(EvidenceError):
                    validate(value)
            for key in original:
                with self.subTest(path=path, missing=key):
                    value = copy.deepcopy(self.value)
                    del at(value, path)[key]
                    with self.assertRaises(EvidenceError):
                        validate(value)

    def test_reject_missing_nonpositive_nonfinite_and_non_numeric_samples(self):
        for section in ("initial_search", "contemporary_reference"):
            path = (section, "samples_seconds")
            times = at(self.value, path)
            for bad in ([], times[:-1], times + times[:1], tuple(times), None, "timings"):
                with self.subTest(section=section, samples=bad):
                    self.reject_change(path, bad)
            for bad in (0, -1, True, False, float("nan"), float("inf"),
                        -float("inf"), "0.061", None):
                for index in range(3):
                    with self.subTest(section=section, index=index, sample=bad):
                        self.reject_change(path + (index,), bad)

    def test_reject_changed_or_malformed_timing_arithmetic(self):
        for section in ("initial_search", "contemporary_reference"):
            for key in ("mean_seconds", "sample_stdev_seconds"):
                original = self.value[section][key]
                for bad in (original + 0.001, 0, -1, True, str(original),
                            float("nan"), float("inf")):
                    with self.subTest(section=section, key=key, value=bad):
                        self.reject_change((section, key), bad)
        for key in ("initial_mean_ratio", "initial_runtime_reduction_fraction"):
            original = self.value["comparison"][key]
            for bad in (original + 0.001, 0, -1, True, str(original),
                        float("nan"), float("inf")):
                with self.subTest(key=key, value=bad):
                    self.reject_change(("comparison", key), bad)

    def test_recorded_search_score_is_preserved_and_never_renamed_speedup(self):
        for bad in (1.1452202332567816, 0.12680550783127864, 0, True,
                    "0.5338473950146169", float("nan"), float("inf")):
            with self.subTest(value=bad):
                self.reject_change(("initial_search", "recorded_search_score"), bad)
        value = copy.deepcopy(self.value)
        value["initial_search"]["speedup"] = value["initial_search"].pop("recorded_search_score")
        with self.assertRaises(EvidenceError):
            validate(value)

    def test_reject_changed_cell_allocation_schema_scope_and_cutoffs(self):
        changes = {
            ("schema",): "hpc-forest-public-native-first-batch-v2",
            ("scope",): "complete_campaign",
            ("source_cutoff_utc",): "2026-10-19T11:11:42.348000+00:00",
            ("audit_cutoff_utc",): "2026-10-19T11:09:31.683709+00:00",
            ("cell", "subject_id"): "2020-tropical",
            ("cell", "model"): "gpt-6-sol",
            ("cell", "effort"): "high",
            ("cell", "seed"): 29,
            ("cell", "job_id"): "755563",
            ("allocation", "architecture"): "x86_64",
        }
        for path, bad in changes.items():
            with self.subTest(path=path):
                self.reject_change(path, bad)
        for key, original in self.value["allocation"].items():
            if type(original) is int:
                for bad in (original + 1, float(original), bool(original)):
                    with self.subTest(allocation=key, value=bad):
                        self.reject_change(("allocation", key), bad)
        for bad in (True, 23.0, "23"):
            with self.subTest(seed=bad):
                self.reject_change(("cell", "seed"), bad)

    def test_reject_malformed_all_provenance_digests_and_protocol(self):
        for path, obj in objects(self.value):
            for key, original in obj.items():
                if key.endswith("sha256") or key == "protocol_id":
                    digests = enumerate(original) if isinstance(original, list) else [(None, original)]
                    for index, _ in digests:
                        digest_path = path + (key,) + (() if index is None else (index,))
                        for bad in ("", "a" * 63, "a" * 65, "g" * 64, "A" * 64, 123, None):
                            with self.subTest(path=digest_path, value=bad):
                                self.reject_change(digest_path, bad)
        streams = self.value["contemporary_reference"]["sample_stream_sha256"]
        for bad in (streams[:-1], streams + streams[:1], None):
            with self.subTest(streams=bad):
                self.reject_change(("contemporary_reference", "sample_stream_sha256"), bad)

    def test_exactly_two_ordered_delivered_calls_and_three_registry_slots(self):
        calls = self.value["model_accounting"]["calls"]
        for bad in (calls[:-1], calls + [copy.deepcopy(calls[1])],
                    list(reversed(calls)), [copy.deepcopy(calls[0]), copy.deepcopy(calls[0])],
                    None, {}):
            with self.subTest(calls=bad):
                self.reject_change(("model_accounting", "calls"), bad)
        for index, expected in enumerate((15629, 17136)):
            for bad in (expected + 1, float(expected), True, "15629"):
                with self.subTest(index=index, tokens=bad):
                    self.reject_change(("model_accounting", "calls", index, "exact_tokens"), bad)
            self.reject_change(("model_accounting", "calls", index, "role"), "third_request")
        for key, expected in (("delivered_calls", 2), ("registry_slots", 3),
                              ("tokens_used", 32765), ("exact_tokens_used", 32765),
                              ("tokens_reserved", 0), ("unknown_usage_calls", 0),
                              ("bounded_usage_calls", 0)):
            for bad in (expected + 1, float(expected), bool(expected), str(expected)):
                with self.subTest(key=key, value=bad):
                    self.reject_change(("model_accounting", key), bad)
        self.reject_change(("model_accounting", "delivered_calls"), 3)

    def test_all_claim_and_authorization_flags_are_exact_booleans(self):
        for path, obj in objects(self.value):
            for key, original in obj.items():
                if type(original) is bool:
                    for bad in (not original, int(original), str(original).lower(), None):
                        with self.subTest(path=path + (key,), value=bad):
                            self.reject_change(path + (key,), bad)

    def test_audit_observation_limits_remain_explicit(self):
        for path, bad in {
            ("initial_search", "status"): "final_confirmed",
            ("audit", "observation_mode"): "case-v2",
            ("audit", "candidate_command_streams"): 7,
            ("audit", "reference_command_streams"): 7,
            ("audit", "external_shell", "program"): "/bin/bash",
            ("audit", "external_shell", "sha256"): "a" * 64,
            ("audit", "external_shell", "bytes"): 1366953,
            ("audit", "external_shell", "copy_job_id"): "755598",
            ("audit", "external_shell", "copy_node"): "romeo-a058",
            ("audit", "external_shell", "model_calls"): 1,
        }.items():
            with self.subTest(path=path):
                self.reject_change(path, bad)
        for key in ("candidate_command_streams", "reference_command_streams"):
            for bad in (6.0, True, "6"):
                with self.subTest(key=key, value=bad):
                    self.reject_change(("audit", key), bad)
        for key in ("bytes", "model_calls"):
            original = self.value["audit"]["external_shell"][key]
            for bad in (float(original), bool(original)):
                with self.subTest(shell=key, value=bad):
                    self.reject_change(("audit", "external_shell", key), bad)

    def test_preserve_existing_deadlines_and_no_new_requests_or_cell_launches(self):
        for key in ("existing_search_deadline", "existing_campaign_deadline"):
            original = self.value["paused_snapshot"][key]
            for bad in (original + 0.5, original - 0.5, True, str(original), float("inf")):
                with self.subTest(key=key, value=bad):
                    self.reject_change(("paused_snapshot", key), bad)
        for key in ("new_requests_created", "other_cell_launches_claimed"):
            for bad in (1, 0.0, False, "0"):
                with self.subTest(key=key, value=bad):
                    self.reject_change(("paused_snapshot", key), bad)

    def test_pre_admission_failure_and_diagnostic_are_zero_model_events(self):
        for key, bad in (("failed_job", "755551"), ("failed_job_terminal_state", "COMPLETED"),
                         ("diagnostic_job", "755550"), ("diagnostic_state", "FAILED"),
                         ("diagnostic_exit_code", "1:0")):
            with self.subTest(key=key):
                self.reject_change(("pre_admission_incident", key), bad)
        for bad in (1, 0.0, False, "0"):
            with self.subTest(calls=bad):
                self.reject_change(("pre_admission_incident", "native_model_calls"), bad)

    def test_release_receipt_authorization_links_and_chronology(self):
        for key in ("receipt_sha256", "release_sha256", "private_cli_audit_sha256",
                    "private_review_receipt_sha256"):
            with self.subTest(key=key):
                self.reject_change(("release_acceptance", key), "a" * 64)
        for bad in (1, 0.0, False, "0"):
            with self.subTest(replays=bad):
                self.reject_change(("release_acceptance", "replayed_claims"), bad)
        for bad in (self.value["audit_cutoff_utc"], "2026-10-19T11:13:04.369662+00:00",
                    "2026-10-19T11:15:04.369662+00:00", "invalid", None):
            with self.subTest(observed=bad):
                self.reject_change(("release_acceptance", "observed_utc"), bad)
        for release_key, provenance_key in (("private_cli_audit_sha256", "private_audit_digest_sha256"),
                                             ("private_review_receipt_sha256", "private_audit_sha256")):
            with self.subTest(provenance=provenance_key):
                value = copy.deepcopy(self.value)
                value["provenance"][provenance_key] = "a" * 64
                with self.assertRaises(EvidenceError):
                    validate(value)
                self.assertEqual(self.value["release_acceptance"][release_key],
                                 self.value["provenance"][provenance_key])

    def test_loader_rejects_duplicate_keys_and_nonfinite_json(self):
        raw = PROJECTION.read_text(encoding="utf-8")
        duplicate = raw.replace('"scope":', '"scope": "initial_search_batch_only", "scope":', 1)
        for text in (duplicate, raw.replace("0.06142141669988632", "NaN", 1),
                     raw.replace("0.06142141669988632", "Infinity", 1)):
            with self.subTest(text=text[:80]):
                with self.assertRaises(EvidenceError):
                    load_json(text)
        self.assertEqual(load_json(json.dumps(self.value)), self.value)

    def test_verify_uses_the_strict_json_loader(self):
        raw = PROJECTION.read_text(encoding="utf-8")
        duplicate = raw.replace('"scope":', '"scope": "initial_search_batch_only", "scope":', 1)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            projection = root / PROJECTION.relative_to(ROOT)
            projection.parent.mkdir(parents=True)
            for text in (duplicate, raw.replace("0.06142141669988632", "NaN", 1),
                         raw.replace("0.06142141669988632", "Infinity", 1)):
                with self.subTest(text=text[:80]):
                    projection.write_text(text, encoding="utf-8")
                    with self.assertRaises(EvidenceError):
                        verify(root)


if __name__ == "__main__":
    unittest.main()
