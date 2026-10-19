"""Verify the dated r4 supplement without running models or candidate code."""
from collections import Counter
import csv
from html.parser import HTMLParser
import hashlib
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .received import HEX, ReceivedError, keys, load, need

SUBDIR = Path("evidence/received-2026-10-19-r4")
CUTOFF = "2026-10-19T08:40:00Z"
MODELS = {"gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra"}
FIELDS = [
    "subject_id", "model", "effort", "seed", "r1_status",
    "r1_reference_seconds", "r1_candidate_seconds", "r1_gain_fraction", "r1_speedup",
    "r1_known_exact_tokens", "r1_archived_unmetered_native_invocations",
    "r1_received_reconciled_unmetered_calls", "r2_status", "r2_received",
    "r2_reference_seconds", "r2_candidate_seconds", "r2_gain_fraction", "r2_speedup",
    "paired_results_available", "causal_claim", "historical_timings_reused_as_new",
]


def number(value):
    try:
        result = float(value)
    except (ValueError, TypeError) as error:
        raise ReceivedError("Missing or invalid measured number") from error
    need(math.isfinite(result), "Nonfinite measured number")
    return result


def same(value, expected):
    need(math.isclose(number(value), number(expected), rel_tol=1e-10, abs_tol=1e-12),
         "R1 historical value or arithmetic differs")


def verify_data(root):
    root = Path(root)
    folder = root / SUBDIR
    with (folder / "matrix15.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames == FIELDS, "Unexpected matrix fields")
        rows = list(reader)
    need(len(rows) == 60, "Matrix must preserve all60registered cells")
    with (root / "evidence/received-2026-10-19/confirmations.csv").open(encoding="utf-8", newline="") as stream:
        historical = [r for r in csv.DictReader(stream)
                      if r["cohort"] in {"count", "luna", "astra", "terra", "sol"}
                      and r["effort"] == "max" and r["model"] in MODELS]
    original = {(r["subject"], r["model"]): r for r in historical}
    need(len(original) == len(historical) == 60, "Historical R1 mapping is incomplete or ambiguous")
    seen = set()
    cost_differences = []
    for row in rows:
        cell = (row["subject_id"], row["model"])
        need(cell not in seen and cell in original, "Duplicate, unknown or missing matrix cell")
        seen.add(cell)
        need(row["effort"] == "max" and row["seed"] == "23" and row["r1_status"] == "confirmed",
             "R1/MAX/seed identity differs")
        need(row["r2_status"] == "not_launched_in_registered_snapshot", "Unverified R2status promoted")
        for field in ("r2_received", "paired_results_available", "causal_claim", "historical_timings_reused_as_new"):
            need(row[field] == "false", "Unreceived result promoted or historical timing reused")
        for field in ("r2_reference_seconds", "r2_candidate_seconds", "r2_gain_fraction", "r2_speedup"):
            need(row[field] == "", "R2NA must remain missing, never numeric zero")
        before = original[cell]
        same(row["r1_reference_seconds"], before["reference_seconds"])
        same(row["r1_candidate_seconds"], before["chosen_seconds"])
        same(row["r1_gain_fraction"], number(before["gain_percent"]) / 100)
        same(row["r1_speedup"], before["speedup"])
        ref_seconds, candidate = number(row["r1_reference_seconds"]), number(row["r1_candidate_seconds"])
        need(ref_seconds > 0 and candidate > 0, "Nonpositive historical timing")
        same(row["r1_gain_fraction"], 1 - candidate / ref_seconds)
        same(row["r1_speedup"], ref_seconds / candidate)
        for current, old in (("r1_known_exact_tokens", "known_exact_tokens"),
                             ("r1_received_reconciled_unmetered_calls", "unmetered_calls")):
            need(row[current] == before[old], "Historical cost or unknown cost changed")
        archived = row["r1_archived_unmetered_native_invocations"]
        need(archived.isdecimal(), "Invalid archived unknown-consumption counter")
        if archived != row["r1_received_reconciled_unmetered_calls"]:
            cost_differences.append({
                "subject_id":row["subject_id"], "model":row["model"],
                "archived_unmetered_native_invocations":int(archived),
                "received_reconciled_unmetered_calls":int(row["r1_received_reconciled_unmetered_calls"]),
            })
    need(seen == set(original), "Matrix lost a historical cell")
    need(set(Counter(r["model"] for r in rows).values()) == {15}, "Missing model coverage")
    need(set(Counter(r["subject_id"] for r in rows).values()) == {4}, "Missing subject coverage")
    zero_gains = sum(number(row["r1_gain_fraction"]) == 0 for row in rows)
    need(zero_gains == 11, "Measured R1zeros changed")
    operations = load(folder / "operational-status.json")
    keys(operations, [
        "schema", "technical_snapshot_utc", "historical_aggregates_changed", "new_scientific_gain_admitted",
        "attempts", "ascii_validation", "attempt4_at_cutoff", "primes_outside_matrix15",
        "sol_external_supplement", "current_process_or_queue_observation_claimed",
    ])
    need(operations["schema"] == "hpc-forest-received-r4-operational-projection-v1"
         and operations["technical_snapshot_utc"] == CUTOFF, "Invalid operational snapshot")
    for field in ("historical_aggregates_changed", "new_scientific_gain_admitted",
                  "current_process_or_queue_observation_claimed"):
        need(operations[field] is False, "Operational history promoted to a new scientific or live claim")
    need(operations["primes_outside_matrix15"] is True, "Primes incorrectly joined to15subjects")
    need(operations["sol_external_supplement"] == "../received-2026-10-19/sol-r2h.json",
         "Sol supplement provenance differs")
    attempts = operations["attempts"]
    need(type(attempts) is list and len(attempts) == 2, "Missing admission history")
    expected_jobs = [
        {"gpt-6-astra": "755409", "gpt-5.6-terra": "755410", "gpt-6-luna": "755408"},
        {"gpt-6-astra": "755433", "gpt-5.6-terra": "755434", "gpt-6-luna": "755435"},
    ]
    common_fields = [
        "attempt", "jobs", "terminal_state", "native_invocations", "worker_starts", "known_exact_tokens",
        "scientific_timing_samples", "preserved_files", "preservation_kind",
        "authorization_files_present", "authorization_ready_files_present",
    ]
    for index, attempt in enumerate(attempts):
        extra = [] if index == 0 else ["terminal_utc", "authorization_files_corrupted", "allocation_ready_files_present"]
        keys(attempt, common_fields + extra)
        need(type(attempt["attempt"]) is int and attempt["attempt"] == index + 2, "Admission order changed")
        need(attempt["jobs"] == expected_jobs[index] and attempt["terminal_state"] == "FAILED", "Terminal identity changed")
        for field in ("native_invocations", "worker_starts", "known_exact_tokens", "scientific_timing_samples"):
            need(type(attempt[field]) is int and attempt[field] == 0, "Failed admission promoted to a model result")
        need(attempt["authorization_ready_files_present"] is False, "Unverified authorization-ready claimed")
    a2, a3 = attempts
    need(a2["preserved_files"] == 21 and a2["preservation_kind"] == "partial"
         and a2["authorization_files_present"] is False, "A2partial preservation differs")
    need(a3["preserved_files"] == 78 and a3["preservation_kind"] == "complete_admission_directories"
         and a3["authorization_files_present"] is True and a3["authorization_files_corrupted"] is True
         and a3["allocation_ready_files_present"] is True, "A3corrupt AUTH or allocation marker history lost")
    need(a3["terminal_utc"] == {
        "gpt-6-astra": "2026-10-19T08:15:44Z", "gpt-5.6-terra": "2026-10-19T08:15:46Z",
        "gpt-6-luna": "2026-10-19T08:15:51Z",
    }, "A3terminal dates changed")
    ascii_validation = operations["ascii_validation"]
    keys(ascii_validation, ["scope", "decoded_hash_entries_verified", "utf8_lengths_verified",
        "remote_operations", "native_calls", "successful_remote_transport_proved", "old_remote_authorizations_repaired"])
    need(ascii_validation["scope"] == "local_only" and ascii_validation["decoded_hash_entries_verified"] == 23
         and ascii_validation["utf8_lengths_verified"] is True, "ASCII local validation scope differs")
    for field in ("remote_operations", "native_calls"):
        need(type(ascii_validation[field]) is int and ascii_validation[field] == 0, "Local test promoted to remote execution")
    for field in ("successful_remote_transport_proved", "old_remote_authorizations_repaired"):
        need(ascii_validation[field] is False, "Local validation promoted to remote success")
    a4 = operations["attempt4_at_cutoff"]
    keys(a4, ["local_preparation_only", "jobs_prepared", "jobs_submitted", "transport_passes", "worker_starts", "native_calls"])
    need(a4["local_preparation_only"] is True, "A4preparation scope differs")
    for field in set(a4) - {"local_preparation_only"}:
        need(type(a4[field]) is int and a4[field] == 0, "Prepared A4 promoted to execution")
    summary = {
        "matrix_cells": 60, "subjects": 15, "models": 4, "r1_confirmed": 60, "r1_zero_gains": zero_gains,
        "r2_received": 0, "r2_NA": 60, "complete_scientific_pairs": 0, "A2_preserved_files": 21,
        "A3_preserved_files": 78, "A3_corrupted_authorizations": 3,
        "local_decoded_hash_entries_verified": 23, "new_scientific_gains": 0,
        "r1_cost_scope_differences":len(cost_differences),
    }
    need(load(folder / "summary.json") == summary, "R4summary differs")
    provenance = load(folder / "provenance.json")
    keys(provenance, ["schema", "technical_snapshot_utc", "historical_scientific_cutoff_utc",
        "original_sources", "projection", "r2_numeric_empty_means", "historical_projection_unchanged", "expected",
        "cost_counter_scopes"])
    need(provenance["schema"] == "hpc-forest-received-r4-public-provenance-v1"
         and provenance["technical_snapshot_utc"] == CUTOFF
         and provenance["historical_scientific_cutoff_utc"] == "2026-10-18T05:03:23.898140+00:00",
         "Scientific or technical cutoff changed")
    need(provenance["expected"] == summary and provenance["r2_numeric_empty_means"] == "NA_not_measured"
         and provenance["historical_projection_unchanged"] == "../received-2026-10-19",
         "Missing-data or historical provenance differs")
    need(len(provenance["original_sources"]) == 10, "Missing original source fingerprints")
    scopes = provenance["cost_counter_scopes"]
    keys(scopes, ["r1_archived_unmetered_native_invocations",
                  "r1_received_reconciled_unmetered_calls", "differences", "interpretation"])
    need(scopes["differences"] == cost_differences == [
        {"subject_id":"2023-count","model":"gpt-6-astra","archived_unmetered_native_invocations":0,"received_reconciled_unmetered_calls":1},
        {"subject_id":"2023-count","model":"gpt-5.6-terra","archived_unmetered_native_invocations":1,"received_reconciled_unmetered_calls":2},
        {"subject_id":"2023-npbonacci","model":"gpt-5.6-terra","archived_unmetered_native_invocations":1,"received_reconciled_unmetered_calls":2},
    ], "Archived and reconciled cost scopes were conflated")
    names = set()
    for source in provenance["original_sources"]:
        keys(source, ["name", "sha256", "bytes"])
        need(re.fullmatch(r"[a-z0-9-]+", source["name"]) and source["name"] not in names,
             "Unsafe or duplicate source identifier")
        need(HEX.fullmatch(source["sha256"]) and type(source["bytes"]) is int and source["bytes"] > 0,
             "Invalid original fingerprint")
        names.add(source["name"])
    for path in folder.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            need(not re.search(r"(?:[A-Za-z]:[\\/]|/scratch|/home/|Bearer\s|sk-[A-Za-z0-9]{16})", text, re.I),
                 "Private path or credential pattern in public supplement")
    return summary


class HTMLReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append((tag, name, value))


def verify_article(root):
    folder = Path(root) / "docs/article"
    provenance = load(folder / "provenance.json")
    need(provenance["edition"] == "2026-10-19-r4" and provenance["technical_snapshot_utc"] == CUTOFF,
         "Article edition or cutoff differs")
    need(provenance["historical_data_cutoff_utc"] == "2026-10-18T05:03:23.898140+00:00"
         and provenance["article_pages"] == 19 and provenance["appendix_pages"] == 308,
         "Article historical scope differs")
    need(provenance["new_scientific_gain_admitted"] is False and provenance["all327pages_machine_rendered_and_checked"] is True,
         "Article verification scope differs")
    need(provenance["actual_changed_pages_visually_reviewed"] == {
        "ARTICLE": [1,18,19], "ANNEXES-TECHNIQUES": [305,306]}, "Visual review scope differs")
    files = provenance["files"]
    names = set()
    for item in files:
        keys(item, ["path", "bytes", "sha256"])
        relative = Path(item["path"])
        need(not relative.is_absolute() and ".." not in relative.parts and ":" not in item["path"]
             and "\\" not in item["path"] and item["path"] not in names, "Unsafe article artifact")
        path = folder / relative
        need(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(folder.resolve()), "Missing article artifact")
        raw = path.read_bytes()
        need(len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"], "Reviewed article bytes changed")
        names.add(item["path"])
    docs = {name + "." + extension for name in ("ARTICLE", "ANNEXES-TECHNIQUES") for extension in ("pdf", "html", "md")}
    need(len(files) == 281 and docs.issubset(names) and sum(name.endswith(".png") for name in names) == 275,
         "Incomplete six-document and275figure article")
    expected_pdfs = {
        "ARTICLE.pdf": "8a688dbf70446d769a60f0c88e53f83039808c4f8270f9526de0150b645a7459",
        "ANNEXES-TECHNIQUES.pdf": "0c0980d69b9e677b387d49222956e118e1b25d5f5c80d40966ed95ef891f2295",
    }
    for name, expected in expected_pdfs.items():
        need(hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected, "Published PDF differs from the reviewed r4")
    previous = provenance["previous_edition"]
    need(previous["edition"] == "2026-10-19-r3" and previous["git_commit"] == "a8d327d1594bc97de87378d160842da51d5e8473"
         and previous["provenance"] == "history/r3-provenance.json", "Previous edition lineage differs")
    need(hashlib.sha256((folder / previous["provenance"]).read_bytes()).hexdigest() == previous["sha256"],
         "Historical r3provenance changed")
    for name in ("ARTICLE.html", "ANNEXES-TECHNIQUES.html"):
        parser = HTMLReferences()
        parser.feed((folder / name).read_text(encoding="utf-8"))
        for tag, attr, raw in parser.references:
            parts = urlsplit(raw)
            if parts.scheme in {"http", "https", "mailto"}:
                need(tag == "a" and attr == "href", "External HTML rendering dependency")
                continue
            if parts.scheme == "data":
                continue
            need(not parts.scheme and not parts.netloc, "Unexpected HTML reference")
            if parts.path:
                target = (folder / unquote(parts.path)).resolve()
                need(target.is_relative_to(folder.resolve()) and target.is_file(), "Broken local HTML artifact reference")
    return len(files)


def verify(root):
    summary = verify_data(root)
    verify_article(root)
    return summary
