"""Closed upstream-Q static references only; no native plan or admission producer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

NATIVE_DOWNSTREAM_SCHEMAS = {
    "hpc-forest-matrix15-native-max-plan-v1", "hpc-forest-matrix15-native-max-plan-v2",
    "hpc-forest-matrix15-subject-qualification-v1", "hpc-forest-matrix15-subject-reception-v1",
    "hpc-forest-matrix15-subject-reception-audit-v1", "hpc-forest-matrix15-authorization-v1",
    "hpc-forest-matrix15-native-static-package-v1",
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, "Duplicate upstream-Q JSON key")
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError("Nonfinite upstream-Q JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def assert_upstream_json(value):
    """Reject native final products; the real Q plan and raw Q report remain upstream."""
    if isinstance(value, dict):
        need(value.get("schema") not in NATIVE_DOWNSTREAM_SCHEMAS,
             "A native plan/final qualification/reception/admission cannot be an upstream alias")
        need(not any(value.get(key) is not None for key in ("native_plan_ref", "native_plan_sha256", "native_authorization_ref")),
             "Upstream-Q data must not depend on the downstream native plan/admission")
        for item in value.values():
            assert_upstream_json(item)
    elif isinstance(value, list):
        for item in value:
            assert_upstream_json(item)


def read_spec(path):
    """Return exact real local bytes and declared ARM paths; never assert qualification success."""
    path = Path(path)
    spec = read_json(path.read_bytes())
    need(type(spec) is dict and set(spec) == {"schema", "qualification_job_id", "files"}
         and spec["schema"] == "hpc-forest-matrix15-Q-upstream-static-inputs-v1"
         and spec["qualification_job_id"] == "755488", "Exact real Q755488 upstream file list required")
    rows = spec["files"]
    need(type(rows) is list and 1 <= len(rows) <= 256, "Bounded nonempty upstream-Q file list required")
    result, windows_seen, arm_seen = [], set(), set()
    for row in rows:
        need(type(row) is dict and set(row) == {"role", "reference", "arm_path"}
             and isinstance(row["role"], str) and bool(row["role"]), "Closed upstream-Q file record required")
        ref = row["reference"]
        need(type(ref) is dict and set(ref) == {"path", "sha256"}
             and isinstance(ref["path"], str) and isinstance(ref["sha256"], str)
             and len(ref["sha256"]) == 64 and all(c in "0123456789abcdef" for c in ref["sha256"]),
             "Real upstream-Q path/SHA reference required")
        local = Path(ref["path"])
        need(local.is_absolute() and local.is_file() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
             for p in (local, *local.parents)), "Physical absolute upstream-Q input required")
        raw = local.read_bytes()
        need(sha(raw) == ref["sha256"], "Upstream-Q artifact bytes changed")
        arm = PurePosixPath(row["arm_path"]) if isinstance(row["arm_path"], str) else None
        need(arm is not None and arm.is_absolute() and arm.as_posix() == row["arm_path"]
             and ".." not in arm.parts and "\\" not in row["arm_path"]
             and not any(c in row["arm_path"] for c in ("\0", "\r", "\n")),
             "Explicit canonical absolute ARM upstream path required")
        identity = str(local.resolve()).casefold()
        need(identity not in windows_seen and row["arm_path"] not in arm_seen, "Duplicate/ambiguous upstream-Q path")
        windows_seen.add(identity)
        arm_seen.add(row["arm_path"])
        if local.suffix.lower() == ".json":
            assert_upstream_json(read_json(raw))
        result.append({**row, "raw": raw})
    return result
