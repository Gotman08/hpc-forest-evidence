"""Recalculate public timing observations with the Python standard library."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("kernel-A", "kernel-B", "system-A", "system-B")
SUBJECTS = ("2022-bucketsort", "2022-knn", "2022-nbody", "2022-sum")
CORES = (1, 2, 4, 8, 16)


class EvidenceError(ValueError):
    """Incomplete, contradictory or malformed evidence cannot support a result."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(text):
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError(f"Nonfinite value: {value}")))
    except (ValueError, TypeError) as error:
        raise EvidenceError(str(error)) from error


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _number(value, *, positive=False):
    return type(value) in {int, float} and math.isfinite(value) and (value > 0 if positive else value >= 0)


def controller(rows):
    groups, identities, traces = defaultdict(list), set(), {}
    expected_keys = {"variant", "phase", "trials", "seed", "repetition", "trace_sha256",
                     "wall_ns", "cpu_ns", "cycles_wall_ns", "cycles_cpu_ns"}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == expected_keys, "Controller row fields differ")
        variant, n, seed, rep = (row[k] for k in ("variant", "trials", "seed", "repetition"))
        _require(isinstance(variant, str) and variant in VARIANTS, "Unknown controller variant")
        _require(type(n) is int and n in (8, 32), "Wrong cycle count")
        _require(type(seed) is int and seed in (23, 29, 31), "Wrong seed")
        _require(type(rep) is int and rep in range(-1, 5), "Wrong repetition")
        _require(row["phase"] == ("warmup" if rep == -1 else "measurement"), "Warmup phase mismatch")
        identity = (variant, n, seed, rep)
        _require(identity not in identities, "Duplicate controller series")
        identities.add(identity)
        _require(_digest(row["trace_sha256"]), "Invalid trace digest")
        trace_key = n, seed
        _require(traces.setdefault(trace_key, row["trace_sha256"]) == row["trace_sha256"], "Unmatched traces")
        for counter in ("wall", "cpu"):
            samples, total = row[f"cycles_{counter}_ns"], row[f"{counter}_ns"]
            _require(isinstance(samples, list) and len(samples) == n, "Missing cycle samples")
            _require(all(type(v) is int and v > 0 for v in samples), "Nonpositive/noninteger cycle time")
            _require(type(total) is int and total == sum(samples), "Cycle sum mismatch")
        if rep >= 0:
            groups[variant, n].append(row)
    expected = set(itertools.product(VARIANTS, (8, 32), (23, 29, 31), range(-1, 5)))
    _require(identities == expected, "Incomplete controller design")
    summary = []
    for (variant, n), items in sorted(groups.items()):
        means = [item["wall_ns"] / n / 1e6 for item in items]
        summary.append({"variant": variant, "cycles_per_series": n, "series": len(items),
                        "wall_ms_mean": statistics.mean(means), "wall_ms_stdev": statistics.stdev(means),
                        "cpu_ms_mean": statistics.mean(item["cpu_ns"] / n / 1e6 for item in items)})
    lookup = {(row["variant"], row["cycles_per_series"]): row for row in summary}
    comparisons = []
    for n in (8, 32):
        for before, after in (("kernel-A", "kernel-B"), ("system-A", "system-B")):
            left, right = [lookup[name, n]["wall_ms_mean"] for name in (before, after)]
            comparisons.append({"reference": before, "candidate": after, "cycles_per_series": n,
                                "time_reduction_percent": 100 * (1 - right / left),
                                "reference_over_candidate": left / right, "saved_ms_per_cycle": left - right})
    return {"scope": "fixed_trace_controller_overhead", "series": len(rows), "warmup_series": 24,
            "measured_series": 120, "measured_cycles": 2400,
            "model_searches": 0, "program_quality_gain_demonstrated": False,
            "summary": summary, "comparisons": comparisons}


def scaling(rows):
    _require(isinstance(rows, list), "Expected CPU sample list")
    groups, identities, binaries, inputs = defaultdict(list), set(), {}, {}
    expected_keys = {"subject", "input_sha256", "program", "binary_sha256", "cores", "repeat",
                     "seconds", "cpu_seconds", "matches_oracle", "returncode"}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == expected_keys, "CPU row fields differ")
        subject, program, cores, repeat = (row[k] for k in ("subject", "program", "cores", "repeat"))
        _require(isinstance(subject, str) and subject in SUBJECTS, "Unknown CPU subject")
        _require(isinstance(program, str) and program in ("reference", "selected"), "Unknown program")
        _require(type(cores) is int and cores in CORES, "Wrong physical core count")
        _require(type(repeat) is int and repeat in range(1, 6), "Wrong CPU repetition")
        identity = subject, program, cores, repeat
        _require(identity not in identities, "Duplicate CPU sample")
        identities.add(identity)
        _require(_digest(row["input_sha256"]) and _digest(row["binary_sha256"]), "Invalid artifact digest")
        _require(inputs.setdefault(subject, row["input_sha256"]) == row["input_sha256"], "Input changed within subject")
        key = subject, program
        _require(binaries.setdefault(key, row["binary_sha256"]) == row["binary_sha256"], "Executable changed across cores")
        _require(_number(row["seconds"], positive=True) and _number(row["cpu_seconds"]), "Invalid CPU time")
        _require(row["matches_oracle"] is True and type(row["returncode"]) is int and row["returncode"] == 0,
                 "Invalid output/run cannot support this accepted dataset")
        groups[subject, program, cores].append(row)
    expected = set(itertools.product(SUBJECTS, ("reference", "selected"), CORES, range(1, 6)))
    _require(identities == expected, "Incomplete CPU design")
    summary = []
    for (subject, program, cores), items in sorted(groups.items()):
        times = [item["seconds"] for item in items]
        summary.append({"subject": subject, "program": program, "cores": cores, "samples": len(times),
                        "mean_seconds": statistics.mean(times), "stdev_seconds": statistics.stdev(times),
                        "median_seconds": statistics.median(times),
                        "mean_cpu_to_wall": statistics.mean(item["cpu_seconds"] / item["seconds"] for item in items)})
    lookup = {(row["subject"], row["program"], row["cores"]): row for row in summary}
    comparisons = []
    for subject in SUBJECTS:
        single = lookup[subject, "selected", 1]["mean_seconds"]
        for cores in CORES:
            selected = lookup[subject, "selected", cores]["mean_seconds"]
            reference = lookup[subject, "reference", cores]["mean_seconds"]
            comparisons.append({"subject": subject, "cores": cores,
                                "own_core_speedup": single / selected, "own_core_efficiency": single / selected / cores,
                                "reference_over_selected": reference / selected,
                                "time_reduction_vs_reference_percent": 100 * (1 - selected / reference)})
    return {"scope": "four_largest_cases_one_allocation", "samples": len(rows), "configurations": len(groups),
            "independent_optimization_searches_in_this_measurement": 0, "summary": summary, "comparisons": comparisons}


def compute(root=ROOT):
    rows = [load_json(line) for line in (root / "evidence/controller/timings.jsonl").read_text(encoding="utf-8").splitlines()]
    cpu = load_json((root / "evidence/cpu-scaling/timings.json").read_text(encoding="utf-8"))
    return {"schema": 1, "controller": controller(rows), "cpu_scaling": scaling(cpu)}


def compare(actual, expected, location="result"):
    """Compare arithmetic across Python versions without accepting changed structure."""
    if type(actual) in {int, float} and type(expected) in {int, float}:
        _require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15), f"Recalculation differs: {location}")
    elif isinstance(actual, dict) and isinstance(expected, dict):
        _require(actual.keys() == expected.keys(), f"Keys differ: {location}")
        for key in actual:
            compare(actual[key], expected[key], f"{location}.{key}")
    elif isinstance(actual, list) and isinstance(expected, list):
        _require(len(actual) == len(expected), f"Length differs: {location}")
        for i, (left, right) in enumerate(zip(actual, expected, strict=True)):
            compare(left, right, f"{location}[{i}]")
    else:
        _require(type(actual) is type(expected) and actual == expected, f"Value differs: {location}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with published results.json")
    args = parser.parse_args()
    result = compute()
    if args.check:
        compare(result, load_json((ROOT / "evidence/results.json").read_text(encoding="utf-8")))
        print("All published results agree with the raw timing records.")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
