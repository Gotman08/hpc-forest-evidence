"""Project and verify received numerical evidence using only the standard library.

The build command reads local archives; it never imports or executes their code.
The verifier needs only this repository and checks schemas, hashes and arithmetic.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

SUBDIR = Path("evidence/received-2026-10-19")
TOKEN = re.compile(r"[A-Za-z0-9_.:+-]{1,160}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
CPU_FIELDS = "batch job_id case_key program_key cores repeat wall_seconds cpu_seconds mean_used_cores stdout_sha256".split()
CONFIRM_FIELDS = "cohort subject model effort arm job_id campaign_id reference_seconds chosen_seconds gain_percent speedup reference_sd chosen_sd baseline_retained nodes known_exact_tokens native_calls unmetered_calls".split()
COMPARE_FIELDS = "batch job_id campaign_id model effort arm subject case_name phase input_sha256 size cores chosen_program_key reference_program_key chosen_seconds chosen_sd reference_seconds reference_sd seconds_saved gain_fraction speedup_vs_reference scaling_speedup scaling_efficiency mean_used_cores baseline_retained".split()
EVAL_FIELDS = "id epoch phase binary_sha256 commit correct mean_seconds score status times tree_hash".split()
BEST_FIELDS = "commit epoch evaluation_digest experiment_id improvement_fraction is_baseline mean_seconds protocol_id reference_seconds".split()
MISSION_FIELDS = "id parent_id depth epoch ordinal role tree_id trial_id base_commit source_commits".split()
CALL_FIELDS = "subject model effort kind role state status technical native_invocation_observed native_cli_invocation_observed usage_measured exact_total input_tokens output_tokens cached_input_tokens reasoning_output_tokens budget_charge_for_unmetered delivery_verified late_originally_absent_from_archive backend_model_identity_independently_attested".split()
USAGE_FIELDS = "input_tokens cached_input_tokens cache_write_input_tokens output_tokens reasoning_output_tokens".split()
BUDGET_FIELDS = "confirmation_seconds confirmation_slots generation_seconds infrastructure_retries max_depth max_workers mission_tokens search_slots tokens wall_seconds".split()
LEGACY_COST_FIELDS = "slots tokens_used tokens_reserved unknown_usage_calls bounded_usage_calls exact_tokens_used unknown_usage_charged_tokens upper_bound_charged_tokens unknown_usage_slots upper_bound_slots reserved_tokens exact_known_tokens".split()


class ReceivedError(ValueError):
    """Evidence is malformed or differs from its declared projection."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(text):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ReceivedError("Duplicate JSON key")
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ReceivedError("Nonfinite JSON")))


def load(path):
    return parse_json(path.read_text(encoding="utf-8-sig"))


def safe(value):
    """Only identifier strings, finite numbers, booleans, null and their lists."""
    if value is None or type(value) is bool:
        return value
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ReceivedError("Nonfinite value")
        return value
    if isinstance(value, str) and (TOKEN.fullmatch(value) or value in ("", "m\u00e8re", "int\u00e9gration")):
        return value
    if isinstance(value, list):
        return [safe(x) for x in value]
    raise ReceivedError("Unapproved scalar or nested source structure")


def select(obj, fields):
    return {key: safe(obj[key]) for key in fields if key in obj}


def campaign_id(root):
    return "campaign-" + digest(root.encode("utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def summary_cost(rows):
    return {"observations": len(rows),
            "known_exact_tokens": sum(r["exact_total"] for r in rows if r.get("exact_total") is not None),
            "unknown_exact_total": sum(r.get("exact_total") is None for r in rows),
            "states": dict(sorted(collections.Counter(r.get("state", "unspecified") for r in rows).items()))}


def build(root, historical, article, reprise, r2g):
    """Explicit allowlist projection of the frozen received files."""
    out = root / SUBDIR
    if out.exists():
        raise ReceivedError("Preserve existing projection; use a new empty destination")
    out.mkdir(parents=True)
    sources = []

    def source(path, name=None):
        raw = path.read_bytes()
        label = name or path.name
        item = {"name": label, "sha256": digest(raw), "bytes": len(raw)}
        if item not in sources:
            sources.append(item)
        return item

    index = load(historical / "index-campagnes.json")
    source(historical / "index-campagnes.json")
    indexed = {r["root"]: r for r in index}
    campaigns = [{"campaign_id": campaign_id(r["root"]),
                  "campaign_root_sha256": digest(r["root"].encode("utf-8")),
                  **select(r, ["registry_sha256", "model", "effort", "subject"])} for r in index]
    write_json(out / "campaigns.json", campaigns)
    batches = []
    for row in load(historical / "cpu-lots.json"):
        batches.append({**select(row, ["batch", "job_id", "campaigns", "points", "samples", "files_previously_verified", "archive_sha256", "plan_sha256", "audit_sha256"]),
                        "resources": {**select(row["resources"], ["physical_cpu_count", "affinity", "memory_gib", "gpus", "architecture"]),
                                      "topology": [select(t, ["cpu", "package", "core"]) for t in row["resources"].get("topology", [])]}})
    source(historical / "cpu-lots.json")
    write_json(out / "cpu-batches.json", batches)
    cpu_campaigns = []
    for row in load(historical / "cpu-campagnes.json"):
        cpu_campaigns.append({"campaign_id": campaign_id(row["campaign_root"]),
            **select(row, ["batch", "job_id", "subject", "audit_sha256", "effort", "registry_sha256", "contract_sha256", "model", "chosen_is_unchanged_baseline", "static_scan_is_not_runtime_proof", "official_contest_compliance_certified"]),
            "best_confirmed": select(row["best_confirmed"], BEST_FIELDS)})
    source(historical / "cpu-campagnes.json")
    write_json(out / "cpu-campaigns.json", cpu_campaigns)
    legacy_rows = []
    for row in load(historical / "historique-preserve.json")["rows"]:
        legacy_rows.append({**select(row, ["job_id", "problem", "model", "summary_sha256", "complete_as_recorded"]),
                            "summary_path_sha256": digest(row["summary_path"].encode()),
                            "costs_as_recorded": None if row["costs"] is None else select(row["costs"], LEGACY_COST_FIELDS),
                            "best_confirmed_as_recorded": select(row.get("best_confirmed_as_recorded") or {}, BEST_FIELDS)})
    source(historical / "historique-preserve.json")
    write_json(out / "historical-summaries.json", legacy_rows)
    for original, target, fields in [
        ("cpu-mesures-brutes.csv", "cpu-timings.csv", CPU_FIELDS),
        ("confirmations.csv", "confirmations.csv", CONFIRM_FIELDS),
        ("cpu-comparaisons.csv", "cpu-comparisons.csv", COMPARE_FIELDS),
    ]:
        path = historical / original
        source(path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            expected = ["campaign_root" if f == "campaign_id" else f for f in fields]
            if reader.fieldnames != expected:
                raise ReceivedError("Unexpected source CSV schema")
            with (out / target).open("w", encoding="utf-8", newline="") as dest:
                writer = csv.DictWriter(dest, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                for row in reader:
                    if "campaign_root" in row:
                        row["campaign_id"] = campaign_id(row.pop("campaign_root"))
                    writer.writerow(row)

    raw_registers = load(historical / "registres-recalcules.json")
    source(historical / "registres-recalcules.json")
    with (out / "registers.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in raw_registers:
            config, contract = row["config"], row["contract"]
            metadata = indexed[row["campaign_root"]]
            record = {"campaign_id": campaign_id(row["campaign_root"]),
                      **select(row, ["registry_sha256", "reference_samples", "chosen_samples", "reference_stdev", "chosen_stdev", "gain_fraction", "speedup"]),
                      **select(metadata, ["model", "effort", "subject"]),
                      "best_confirmed": select(row["best_confirmed"], BEST_FIELDS),
                      "confirmations": [select(e, EVAL_FIELDS) for e in row["confirmations"]],
                      "trials": [],
                      "contract": {"content_sha256": digest(canonical(contract)),
                                   **select(contract, ["language", "case_timeout_seconds"]),
                                   "search_cases": len(contract.get("search", [])),
                                   "confirmation_cases": len(contract.get("confirmation", []))},
                      "settings": {**select(config, ["seed", "minimum_gain"]),
                                   "budget": select(config.get("budget", {}), BUDGET_FIELDS),
                                   "protocol": select(config.get("protocol", {}), ["confirmation_repetitions", "repetitions", "timeout_seconds", "warmups", "build_timeout_seconds"]),
                                   "compiler": select(config.get("compiler", {}), ["flavor", "sha256"])},
                      "tree_roots": [select(t, ["id", "role", "checkpoint_sha256", "treequest_version"]) for t in row["tree_roots"]]}
            for trial in row["trials"]:
                record["trials"].append({**select(trial, ["id", "role", "state"]),
                                         "mission": select(trial.get("mission", {}), MISSION_FIELDS),
                                         "result": select(trial.get("result") or {}, EVAL_FIELDS)})
            handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n")

    cost_exports = []
    for path in sorted(historical.glob("couts-*.json")):
        original = load(path)
        source(path)
        observations = []
        for i, row in enumerate(original["native_calls"]):
            call = {"observation": i, **select(row, CALL_FIELDS)}
            # These are opaque local join keys, not transport/session identifiers.
            for field in ["session_id", "nonce", "campaign", "mission_id"]:
                if row.get(field) is not None:
                    call[field + "_sha256"] = digest(str(row[field]).encode("utf-8"))
            for field in ["request_sha256", "response_sha256", "request_file_sha256", "response_file_sha256"]:
                if row.get(field):
                    call[field] = safe(row[field])
            if "usage_subdivisions" in row:
                call["usage_subdivisions"] = select(row["usage_subdivisions"] or {}, USAGE_FIELDS)
            # Null means unmeasured; absence never turns into measured zero.
            call.setdefault("exact_total", None)
            observations.append(call)
        cost_exports.append({"source": path.name, "total_exact_consumption_available": original.get("total_exact_consumption_available"),
                             "summary": summary_cost(observations), "calls": observations})
    write_json(out / "cost-observations.json", cost_exports)

    native_path = article / "preuves/AUDIT-NATIF-FINAL-SOL.json"
    release_path = article / "preuves/LIBERATION-SCIENTIFIQUE-SOL.json"
    external_path = article / "preuves/AUDIT-EXTERNE-PAIRE-GELEE.json"
    failures_path = article / "preuves/CLOTURE-TROIS-ALLOCATIONS-SANS-NATIF.json"
    technical_path = article / "preuves/SUIVI-TECHNIQUE.json"
    pair_path = reprise / "remesure-Sol-r1/reception-froide-r1/restauration-privee/run/measurement/RESULT-EXTERNAL-FROZEN-PAIR.json"
    for p in [native_path, release_path, external_path, failures_path, technical_path, pair_path]:
        source(p)
    native, external, technical, pair = map(load, [native_path, external_path, technical_path, pair_path])
    reconciliation = native["transport_cost_reconciliation"]
    sol_calls = [{"nonce_sha256": digest(r["nonce"].encode()),
                  **select(r, ["mother", "exact_tokens", "known_model_negative"])} for r in reconciliation["nonce_records"]]
    supplement = {"schema": 1, "model": "gpt-6.1-sol", "effort": "max",
                  "search_job_id": native["job_id"], "remeasurement_job_id": external["job_id"],
                  "calls": sol_calls, "known_exact_tokens": reconciliation["exact_known_tokens"],
                  "unknown_native_invocations": reconciliation["unknown_native_invocations"],
                  "source_native_audit_verified": native["verified"],
                  "independent_evaluator_implementation": external["independent_evaluator_implementation"],
                  "source_external_execution_audit_verified": external["verified"],
                  "unique_certified_inputs": external["unique_certified_inputs"],
                  "reference": select(pair["confirmations"]["reference"], EVAL_FIELDS),
                  "winner": select(pair["confirmations"]["winner"], EVAL_FIELDS),
                  "reported_reference_seconds": pair["reference_seconds"],
                  "reported_winner_seconds": pair["frozen_winner_seconds"],
                  "reported_reduction_fraction": pair["observed_reduction_fraction"],
                  "reported_speedup": pair["observed_speedup"],
                  "historical_aggregates_include_this_supplement": False,
                  "zero_start_allocations": []}
    remaining = technical["remaining_three_allocations"]
    for model, job in remaining["job_ids"].items():
        supplement["zero_start_allocations"].append({"model": model, "job_id": job,
            **select(remaining, ["terminal_state", "phase", "native_invocations", "known_exact_tokens", "unknown_usage_calls", "native_research_started", "performance_gain_claimed"])})
    write_json(out / "sol-r2h.json", supplement)
    source(r2g)
    closure = load(r2g)
    source(article / "ARTICLE.md")
    operations = {"schema": 1,
                  "r2g": {**select(technical["r2g"], ["closed_partial", "reconciled_invocations", "known_exact_tokens", "metered_invocations", "unmetered_invocations"]),
                          **select(closure, ["verified_metadata_only", "all_started_calls_delivered_and_reconciled", "pipeline_complete", "native_research_admitted", "independent_performance_verified", "five_confirmations_verified", "global_scientific_or_performance_admission"])},
                  "r3_r4b": {"article_status": "blocked_technical", "native_scientific_result_admitted": False},
                  "r5": {"article_status": "not_started", "learned_program_gain_admitted": False},
                  "matrix15": select(technical["matrix15"], ["planned_cells", "models", "subjects", "started_cells", "primes_is_extra_subject"])}
    write_json(out / "operational-status.json", operations)
    audit_path = historical.parent / "audit-calculs.json"
    source(audit_path)
    audit = load(audit_path)
    provenance = {"schema": 1, "scientific_cutoff_utc": audit["completed_utc"],
                  "technical_snapshot_utc": technical["observed_utc"],
                  "sources": sources,
                  "expected": {"campaigns": 209, "registers": 209, "confirmations": 193,
                               "native_cohorts": 14, "deepseek_rows": 6, "cpu_samples": 11575,
                               "cpu_points": 2315, "cpu_comparisons": 1830, "cost_exports": 11,
                               "trials": sum(len(r["trials"]) for r in raw_registers),
                               "cpu_batches": 10, "cpu_campaigns": 58, "historical_summaries": 42}}
    write_json(out / "provenance.json", provenance)
    calculated = compute(out)
    write_json(out / "summary.json", calculated)
    # The source builder is read-only with respect to all received material.
    return calculated


def need(condition, message):
    if not condition:
        raise ReceivedError(message)


def keys(obj, allowed, required=()):
    need(isinstance(obj, dict) and set(obj) <= set(allowed) and set(required) <= set(obj), "Unapproved or missing field")


def number(value, nonnegative=False):
    need(type(value) in (int, float) and math.isfinite(value), "Expected finite numeric value")
    need(not nonnegative or value >= 0, "Negative timing or count")
    return value


def close(a, b):
    need(math.isclose(number(a), number(b), rel_tol=2e-10, abs_tol=1e-12), "Arithmetic mismatch")


def validate_selected(obj, allowed):
    keys(obj, allowed)
    for field, value in obj.items():
        safe(value)
        if field.endswith("sha256") and value is not None:
            need(isinstance(value, str) and HEX.fullmatch(value), "Invalid selected fingerprint")


def csv_rows(path, fields):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        need(reader.fieldnames == fields, "CSV field inventory mismatch")
        rows = list(reader)
    for row in rows:
        need(None not in row and all(v is not None for v in row.values()), "Malformed CSV row")
        for value in row.values():
            if value:
                safe(value)
        integer_fields = {"batch", "cores", "repeat", "size", "nodes", "known_exact_tokens", "native_calls", "unmetered_calls"}
        float_fields = {"wall_seconds", "cpu_seconds", "mean_used_cores", "reference_seconds", "chosen_seconds", "gain_percent", "speedup", "reference_sd", "chosen_sd", "seconds_saved", "gain_fraction", "speedup_vs_reference", "scaling_speedup", "scaling_efficiency"}
        for field, value in row.items():
            if field in integer_fields:
                need((field == "native_calls" and value == "") or re.fullmatch(r"\d+", value) is not None, "Invalid CSV integer")
            if field in float_fields:
                try:
                    number(float(value))
                except ValueError as exc:
                    raise ReceivedError("Invalid CSV number") from exc
            if field == "baseline_retained":
                need(value in ["True", "False"], "Invalid CSV boolean")
            if field in ["stdout_sha256", "input_sha256"]:
                need(HEX.fullmatch(value), "Invalid CSV digest")
    return rows


def evaluation(row):
    validate_selected(row, EVAL_FIELDS)
    if "correct" in row:
        need(row["correct"] is None or type(row["correct"]) is bool, "Invalid correctness flag")
    for field in ["mean_seconds", "score"]:
        if row.get(field) is not None:
            number(row[field], field == "mean_seconds")
    for field in ["id", "phase", "status", "commit", "tree_hash"]:
        if field in row:
            need(row[field] is None or isinstance(row[field], str), "Invalid evaluation identifier")
    if "epoch" in row:
        need(type(row["epoch"]) is int and row["epoch"] >= 0, "Invalid evaluation epoch")
    times = row.get("times", [])
    need(isinstance(times, list), "Invalid timing samples")
    for sample in times:
        number(sample, True)
    if times:
        close(statistics.mean(times), row.get("mean_seconds"))


def compute(out):
    campaigns = load(out / "campaigns.json")
    ids = set()
    for c in campaigns:
        keys(c, ["campaign_id", "campaign_root_sha256", "registry_sha256", "model", "effort", "subject"], ["campaign_id", "campaign_root_sha256", "registry_sha256"])
        for value in c.values():
            if value is not None:
                safe(value)
        need(HEX.fullmatch(c["campaign_root_sha256"]) and HEX.fullmatch(c["registry_sha256"]), "Malformed campaign fingerprint")
        need(c["campaign_id"] == "campaign-" + c["campaign_root_sha256"] and c["campaign_id"] not in ids, "Duplicate or invalid campaign ID")
        ids.add(c["campaign_id"])
    confirmations = csv_rows(out / "confirmations.csv", CONFIRM_FIELDS)
    cohort_counts = collections.Counter()
    for row in confirmations:
        need(row["campaign_id"] in ids, "Unknown confirmation campaign")
        a, b = float(row["reference_seconds"]), float(row["chosen_seconds"])
        need(a > 0 and b > 0, "Nonpositive confirmation timing")
        close(float(row["gain_percent"]), 100 * (1 - b / a))
        close(float(row["speedup"]), a / b)
        cohort_counts[row["cohort"]] += 1
    samples = csv_rows(out / "cpu-timings.csv", CPU_FIELDS)
    groups = collections.defaultdict(list)
    for row in samples:
        for f in ["wall_seconds", "cpu_seconds", "mean_used_cores"]:
            number(float(row[f]), True)
        need(int(row["cores"]) in [1, 2, 4, 8, 16], "Invalid core count")
        need(int(row["repeat"]) in range(5), "Invalid repetition")
        need(HEX.fullmatch(row["stdout_sha256"]), "Malformed output digest")
        close(float(row["mean_used_cores"]), float(row["cpu_seconds"]) / float(row["wall_seconds"]))
        groups[(row["batch"], row["case_key"], row["program_key"], row["cores"])].append(row)
    for rows in groups.values():
        need(len(rows) == 5 and len({r["repeat"] for r in rows}) == 5, "Missing or duplicate CPU repetition")
    comparisons = csv_rows(out / "cpu-comparisons.csv", COMPARE_FIELDS)
    for row in comparisons:
        need(row["campaign_id"] in ids, "Unknown CPU campaign")
        a, b = float(row["reference_seconds"]), float(row["chosen_seconds"])
        close(float(row["seconds_saved"]), a - b)
        close(float(row["gain_fraction"]), 1 - b / a)
        close(float(row["speedup_vs_reference"]), a / b)
        one_core = groups.get((row["batch"], row["subject"] + ":" + row["input_sha256"], row["chosen_program_key"], "1"))
        need(one_core is not None, "Core-scaling comparison lacks its one-core raw group")
        close(float(row["scaling_speedup"]), statistics.mean(float(g["wall_seconds"]) for g in one_core) / b)
        close(float(row["scaling_efficiency"]), float(row["scaling_speedup"]) / int(row["cores"]))
        for prefix in ["reference", "chosen"]:
            program = row[prefix + "_program_key"]
            group = groups.get((row["batch"], row["subject"] + ":" + row["input_sha256"], program, row["cores"]))
            need(group is not None, "Comparison lacks raw timing group")
            times = [float(g["wall_seconds"]) for g in group]
            close(float(row[prefix + "_seconds"]), statistics.mean(times))
            close(float(row[prefix + "_sd"]), statistics.stdev(times))
    batches = load(out / "cpu-batches.json")
    for batch in batches:
        keys(batch, ["batch", "job_id", "campaigns", "points", "samples", "files_previously_verified", "archive_sha256", "plan_sha256", "audit_sha256", "resources"])
        for key, value in batch.items():
            if key != "resources":
                safe(value)
        resources = batch["resources"]
        keys(resources, ["physical_cpu_count", "affinity", "memory_gib", "gpus", "architecture", "topology"])
        for key, value in resources.items():
            if key == "topology":
                for t in value:
                    validate_selected(t, ["cpu", "package", "core"])
            else:
                safe(value)
        number(batch["batch"], True)
        need(batch["samples"] == sum(r["batch"] == str(batch["batch"]) for r in samples), "CPU batch sample count mismatch")
        need(batch["points"] == sum(k[0] == str(batch["batch"]) for k in groups), "CPU batch point count mismatch")
    need(sum(b["samples"] for b in batches) == len(samples), "CPU batch inventory incomplete")
    cpu_campaigns = load(out / "cpu-campaigns.json")
    for c in cpu_campaigns:
        keys(c, ["campaign_id", "batch", "job_id", "subject", "audit_sha256", "effort", "registry_sha256", "contract_sha256", "model", "chosen_is_unchanged_baseline", "static_scan_is_not_runtime_proof", "official_contest_compliance_certified", "best_confirmed"])
        need(c["campaign_id"] in ids, "Unknown CPU campaign metadata")
        validate_selected({k: v for k, v in c.items() if k != "best_confirmed"}, ["campaign_id", "batch", "job_id", "subject", "audit_sha256", "effort", "registry_sha256", "contract_sha256", "model", "chosen_is_unchanged_baseline", "static_scan_is_not_runtime_proof", "official_contest_compliance_certified"])
        validate_selected(c["best_confirmed"], BEST_FIELDS)
    for batch in batches:
        need(batch["campaigns"] == sum(c["batch"] == batch["batch"] for c in cpu_campaigns), "CPU campaign batch count mismatch")
    historical = load(out / "historical-summaries.json")
    for r in historical:
        keys(r, ["job_id", "problem", "model", "summary_sha256", "complete_as_recorded", "summary_path_sha256", "costs_as_recorded", "best_confirmed_as_recorded"])
        validate_selected({k: v for k, v in r.items() if k not in ["costs_as_recorded", "best_confirmed_as_recorded"]}, ["job_id", "problem", "model", "summary_sha256", "complete_as_recorded", "summary_path_sha256"])
        if r["costs_as_recorded"] is not None:
            validate_selected(r["costs_as_recorded"], LEGACY_COST_FIELDS)
        validate_selected(r["best_confirmed_as_recorded"], BEST_FIELDS)
    registers = []
    with (out / "registers.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            registers.append(parse_json(line))
    trial_states, result_states = collections.Counter(), collections.Counter()
    all_register_ids = set()
    for row in registers:
        keys(row, ["campaign_id", "registry_sha256", "reference_samples", "chosen_samples", "reference_stdev", "chosen_stdev", "gain_fraction", "speedup", "model", "effort", "subject", "best_confirmed", "confirmations", "trials", "contract", "settings", "tree_roots"], ["campaign_id", "reference_samples", "chosen_samples", "trials", "confirmations", "best_confirmed"])
        need(row["campaign_id"] in ids and row["campaign_id"] not in all_register_ids, "Unknown or duplicate registry")
        all_register_ids.add(row["campaign_id"])
        validate_selected(row["best_confirmed"], BEST_FIELDS)
        a, b = statistics.mean(row["reference_samples"]), statistics.mean(row["chosen_samples"])
        close(a, row["best_confirmed"]["reference_seconds"])
        close(b, row["best_confirmed"]["mean_seconds"])
        close(row["gain_fraction"], 1 - b / a)
        close(row["speedup"], a / b)
        if len(row["reference_samples"]) > 1:
            close(row["reference_stdev"], statistics.stdev(row["reference_samples"]))
        if len(row["chosen_samples"]) > 1:
            close(row["chosen_stdev"], statistics.stdev(row["chosen_samples"]))
        for e in row["confirmations"]:
            evaluation(e)
        for trial in row["trials"]:
            keys(trial, ["id", "role", "state", "mission", "result"], ["state", "mission", "result"])
            validate_selected({k: v for k, v in trial.items() if k not in ["mission", "result"]}, ["id", "role", "state"])
            validate_selected(trial["mission"], MISSION_FIELDS)
            evaluation(trial["result"])
            trial_states[trial["state"]] += 1
            result_states[trial["result"].get("status", "unspecified")] += 1
        validate_selected(row["contract"], ["content_sha256", "language", "case_timeout_seconds", "search_cases", "confirmation_cases"])
        keys(row["settings"], ["seed", "minimum_gain", "budget", "protocol", "compiler"])
        for k in ["seed", "minimum_gain"]:
            if k in row["settings"]:
                safe(row["settings"][k])
        validate_selected(row["settings"]["protocol"], ["confirmation_repetitions", "repetitions", "timeout_seconds", "warmups", "build_timeout_seconds"])
        validate_selected(row["settings"]["compiler"], ["flavor", "sha256"])
        keys(row["settings"]["budget"], BUDGET_FIELDS)
        for value in row["settings"]["budget"].values():
            need(value is None or type(value) in (int, float, bool), "Non-numeric budget")
            safe(value)
        for t in row["tree_roots"]:
            validate_selected(t, ["id", "role", "checkpoint_sha256", "treequest_version"])
        for key in ["campaign_id", "registry_sha256", "model", "effort", "subject"]:
            if key in row:
                safe(row[key])
    need(all_register_ids == ids, "Registry inventory incomplete")
    costs = load(out / "cost-observations.json")
    cost_summary = {}
    for export in costs:
        keys(export, ["source", "total_exact_consumption_available", "summary", "calls"], ["source", "summary", "calls"])
        safe(export["source"])
        need(export["source"] not in cost_summary, "Duplicate cost source")
        for i, call in enumerate(export["calls"]):
            keys(call, CALL_FIELDS + ["observation", "session_id_sha256", "nonce_sha256", "campaign_sha256", "mission_id_sha256", "request_sha256", "response_sha256", "request_file_sha256", "response_file_sha256", "usage_subdivisions"], ["observation", "exact_total"])
            need(call["observation"] == i, "Cost observation sequence mismatch")
            for field, value in call.items():
                if field == "usage_subdivisions":
                    validate_selected(value, USAGE_FIELDS)
                else:
                    safe(value)
                    if field.endswith("sha256"):
                        need(HEX.fullmatch(value), "Invalid call fingerprint")
            for field in ["exact_total", "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "budget_charge_for_unmetered"]:
                if call.get(field) is not None:
                    need(type(call[field]) is int and call[field] >= 0, "Invalid token count")
            if all(call.get(k) is not None for k in ["exact_total", "input_tokens", "output_tokens"]):
                need(call["exact_total"] == call["input_tokens"] + call["output_tokens"], "Token sum mismatch")
        calculated = summary_cost(export["calls"])
        need(export["total_exact_consumption_available"] is None or type(export["total_exact_consumption_available"]) is bool, "Invalid exact-consumption flag")
        need(calculated == export["summary"], "Cost summary mismatch")
        cost_summary[export["source"]] = calculated
    sol = load(out / "sol-r2h.json")
    keys(sol, ["schema", "model", "effort", "search_job_id", "remeasurement_job_id", "calls", "known_exact_tokens", "unknown_native_invocations", "source_native_audit_verified", "independent_evaluator_implementation", "source_external_execution_audit_verified", "unique_certified_inputs", "reference", "winner", "reported_reference_seconds", "reported_winner_seconds", "reported_reduction_fraction", "reported_speedup", "historical_aggregates_include_this_supplement", "zero_start_allocations"])
    for call in sol["calls"]:
        validate_selected(call, ["nonce_sha256", "mother", "exact_tokens", "known_model_negative"])
    need(len(sol["calls"]) == 3 and sum(c["exact_tokens"] for c in sol["calls"]) == sol["known_exact_tokens"] == 59037, "Sol call reconciliation mismatch")
    need(sol["unknown_native_invocations"] == 0 and sol["unique_certified_inputs"] == 12, "Sol domain mismatch")
    need(sol["independent_evaluator_implementation"] is False and sol["historical_aggregates_include_this_supplement"] is False, "Sol scope overclaim")
    for role in ["reference", "winner"]:
        evaluation(sol[role])
        need(len(sol[role]["times"]) == 5, "Sol paired sample count mismatch")
    close(sol["reported_reference_seconds"], statistics.mean(sol["reference"]["times"]))
    close(sol["reported_winner_seconds"], statistics.mean(sol["winner"]["times"]))
    close(sol["reported_reduction_fraction"], 1 - sol["reported_winner_seconds"] / sol["reported_reference_seconds"])
    close(sol["reported_speedup"], sol["reported_reference_seconds"] / sol["reported_winner_seconds"])
    need(len(sol["zero_start_allocations"]) == 3, "Zero-start incident count mismatch")
    for r in sol["zero_start_allocations"]:
        validate_selected(r, ["model", "job_id", "terminal_state", "phase", "native_invocations", "known_exact_tokens", "unknown_usage_calls", "native_research_started", "performance_gain_claimed"])
        need(r["native_invocations"] == r["known_exact_tokens"] == r["unknown_usage_calls"] == 0 and r["native_research_started"] is False and r["performance_gain_claimed"] is False, "Zero-start scope mismatch")
    operations = load(out / "operational-status.json")
    keys(operations, ["schema", "r2g", "r3_r4b", "r5", "matrix15"])
    validate_selected(operations["r2g"], ["closed_partial", "reconciled_invocations", "known_exact_tokens", "metered_invocations", "unmetered_invocations", "verified_metadata_only", "all_started_calls_delivered_and_reconciled", "pipeline_complete", "native_research_admitted", "independent_performance_verified", "five_confirmations_verified", "global_scientific_or_performance_admission"])
    r2g = operations["r2g"]
    need(r2g["reconciled_invocations"] == r2g["metered_invocations"] + r2g["unmetered_invocations"] == 10 and r2g["known_exact_tokens"] == 146676, "R2g known cost mismatch")
    need(r2g["native_research_admitted"] is False and r2g["five_confirmations_verified"] is False and r2g["pipeline_complete"] is False, "R2g scope overclaim")
    validate_selected(operations["r3_r4b"], ["article_status", "native_scientific_result_admitted"])
    validate_selected(operations["r5"], ["article_status", "learned_program_gain_admitted"])
    validate_selected(operations["matrix15"], ["planned_cells", "models", "subjects", "started_cells", "primes_is_extra_subject"])
    return {"campaigns": len(campaigns), "registers": len(registers), "confirmations": len(confirmations),
            "cohorts": dict(sorted(cohort_counts.items())), "native_cohorts": len(cohort_counts) - 1,
            "deepseek_rows": cohort_counts["deepseek"], "cpu_samples": len(samples), "cpu_points": len(groups),
            "cpu_comparisons": len(comparisons), "trials": sum(trial_states.values()),
            "trial_states": dict(sorted(trial_states.items())), "trial_result_states": dict(sorted(result_states.items())),
            "cost_exports": len(costs), "cost_source_summaries": cost_summary,
            "sol_r2h_calls": 3, "sol_r2h_known_exact_tokens": 59037, "sol_r2h_pairs": 5,
            "zero_start_allocations": 3, "cpu_batches": len(batches), "cpu_campaigns": len(cpu_campaigns),
            "historical_summaries": len(historical)}


def verify(root):
    """Validate every published row and recompute the complete numerical summary."""
    out = Path(root) / SUBDIR
    provenance = load(out / "provenance.json")
    keys(provenance, ["schema", "scientific_cutoff_utc", "technical_snapshot_utc", "sources", "expected"], ["schema", "sources", "expected"])
    need(provenance["schema"] == 1, "Unsupported received schema")
    names = set()
    for src in provenance["sources"]:
        keys(src, ["name", "sha256", "bytes"], ["name", "sha256", "bytes"])
        safe(src["name"])
        need(src["name"] not in names and HEX.fullmatch(src["sha256"]) and type(src["bytes"]) is int and src["bytes"] > 0, "Invalid source provenance")
        names.add(src["name"])
    calculated = compute(out)
    need(calculated == load(out / "summary.json"), "Published received summary differs")
    for key, value in provenance["expected"].items():
        need(calculated.get(key) == value, "Expected received inventory differs")
    # Inspect only the public projection, including unexpected files, for local identities.
    for path in out.rglob("*"):
        if path.is_file():
            need(path.stat().st_size < 50 * 1024 * 1024 and not path.is_symlink(), "Oversized or linked evidence")
            text = path.read_text(encoding="utf-8")
            need(not re.search(r"(?:[A-Za-z]:[\\/]|/scratch|/home/|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|Bearer\s|sk-[A-Za-z0-9]{16})", text, re.I), "Private path or credential pattern")
    return calculated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--historical", type=Path)
    parser.add_argument("--article", type=Path)
    parser.add_argument("--reprise", type=Path)
    parser.add_argument("--r2g", type=Path)
    args = parser.parse_args()
    if args.build:
        need(all([args.historical, args.article, args.reprise, args.r2g]), "All explicit source paths are required")
        build(args.root, args.historical, args.article, args.reprise, args.r2g)
    print(json.dumps(verify(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
