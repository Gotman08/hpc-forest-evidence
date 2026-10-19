"""Closed projection for R2 private-case feedback; raw logs stay in audit files."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

STATUSES = frozenset({"pending", "valid", "development_valid", "build_failed", "incorrect",
                      "runtime_failed", "duplicate", "rejected", "infrastructure_failed",
                      "budget_exhausted", "failed", "completed"})
CODES = frozenset({"compilation_failed", "execution_failed", "execution_timeout",
                   "output_size_or_missing", "output_mismatch", "check_passed",
                   "unavailable_diagnostic", "infrastructure_error"})
CASE = re.compile(r"(?:search|confirmation|benchmark)-case-[1-8]\Z")


def public_outcome(value):
    """Only typed metrics and enumerated status, with no text or filesystem path."""
    result = {"status": value.get("status") if value.get("status") in STATUSES else "failed"}
    if type(value.get("correct")) is bool:
        result["correct"] = value["correct"]
    for key in ("score", "mean_seconds"):
        if key not in value:
            continue
        number = value.get(key)
        if number is None:
            result[key] = None
        elif type(number) in (int, float) and math.isfinite(number) and number >= 0:
            result[key] = number
    return result


def public_diagnostic(value):
    """Treat every byte from a process as untrusted, even valid JSON."""
    if not isinstance(value, dict):
        return {"status": "failed", "code": "unavailable_diagnostic"}
    diagnostic = value.get("diagnostic", value)
    if not isinstance(diagnostic, dict):
        return {"status": "failed", "code": "unavailable_diagnostic"}
    code = diagnostic.get("code")
    if code not in CODES:
        code = "check_passed" if value.get("correct") is True else "unavailable_diagnostic"
    result = {"status": "completed" if value.get("correct") is True else "failed", "code": code}
    case = diagnostic.get("case", diagnostic.get("field", value.get("case")))
    if isinstance(case, str) and CASE.fullmatch(case):
        result["case"] = case
    # Return codes are useful and bounded; arbitrary compiler/checker strings are not.
    returncode = diagnostic.get("returncode")
    if type(returncode) is int and -255 <= returncode <= 255:
        result["returncode"] = returncode
    return result


def diagnostic_logs(root: Path, outcome: dict):
    result = []
    for name in outcome.get("logs", [])[:2]:
        path = Path(name)
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            continue
        try:
            with path.open("rb") as stream:
                raw = stream.read(65537)
            value = json.loads(raw) if len(raw) <= 65536 else None
        except (ValueError, OSError):
            value = None
        result.append(public_diagnostic(value))
    return result
