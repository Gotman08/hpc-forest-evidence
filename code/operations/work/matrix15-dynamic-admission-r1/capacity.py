"""Private Windows capacity producer. Importing this module never collects processes.

Only ``exclusive_capacity`` with no injected collector can produce verified admissions.
Its context must enclose final local admission and launch: the global lock stays held
until the caller exits, and the persistent reservation survives that exit.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

CELL_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
               "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
EXTERNAL_EVIDENCE_FIELDS = {"reservation_producer_review", "source_only_received_closure", "source_only_absence",
                            "other_owned_worker_reconciliation", "local_projection_producer_review"}
EVIDENCE_SCHEMAS = {
    "reservation_producer_review": "hpc-forest-matrix15-reservation-producer-review-v1",
    "local_projection_producer_review": "hpc-forest-matrix15-local-projection-producer-review-v1",
    "source_only_received_closure": "hpc-forest-matrix15-source-only-received-closure-v1",
    "source_only_absence": "hpc-forest-matrix15-source-only-absence-v1",
    "other_owned_worker_reconciliation": "hpc-forest-matrix15-other-owned-worker-reconciliation-v1"}
EVIDENCE_ROLE_FIELDS = {
    "reservation_producer_review": {"decision", "reviewed_capacity_producer_sha256", "exclusive_lock_reviewed",
                                    "pending_capacity_accounting_reviewed", "maximum_native_workers_total", "evidence_refs"},
    "local_projection_producer_review": {"decision", "reviewed_capacity_producer_sha256", "private_census_export_excluded",
                                         "current_census_binding_reviewed", "fixture_promotion_excluded", "evidence_refs"},
    "source_only_received_closure": {"source_only_received", "source_only_closed", "source_only_may_resume",
                                     "closed_source_only_session_ids", "evidence_refs"},
    "source_only_absence": {"observed_at", "private_full_census_sha256", "source_only_active_workers",
                            "all_native_workers_known", "source_only_received_closure_sha256"},
    "other_owned_worker_reconciliation": {"observed_at", "private_full_census_sha256", "other_native_workers_count",
                                          "all_native_workers_known", "launcher_python_pairs_count_as_one",
                                          "reconciled_session_ids", "owned_worker_receipts", "all_workers_owned_and_reconciled"}}
EVIDENCE_TRUE_FIELDS = {
    "reservation_producer_review": {"exclusive_lock_reviewed", "pending_capacity_accounting_reviewed"},
    "local_projection_producer_review": {"private_census_export_excluded", "current_census_binding_reviewed", "fixture_promotion_excluded"},
    "source_only_received_closure": {"source_only_received", "source_only_closed"},
    "source_only_absence": {"all_native_workers_known"},
    "other_owned_worker_reconciliation": {"all_native_workers_known", "launcher_python_pairs_count_as_one",
                                          "all_workers_owned_and_reconciled"}}
PROCESS_FIELDS = {"ProcessId", "ParentProcessId", "ExecutablePath", "CommandLine", "CreationDate"}
SOURCE_ONLY_SIGNATURES = ("source-only", "source_only", "sourceonly")
WORKER_MODULES = ("codex_worker", "matrix15_worker", "r2max_worker")
LAUNCHER_SIGNATURES = ("native-launcher", "native_launcher", "launch-native", "launch_native")
SHA = re.compile(r"[a-f0-9]{64}\Z")
SESSION = re.compile(r"[a-f0-9]{32}\Z")


class CapacityError(ValueError):
    """Fail-closed capacity refusal; no admission is implied."""


def need(condition, message):
    if not condition:
        raise CapacityError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)


def no_redirects(path):
    """Reject symlinks, junctions and other reparse redirects at every ancestor."""
    path = Path(path).absolute()
    for candidate in (path, *path.parents):
        need(not candidate.is_symlink() and not candidate.is_junction(), "Symlink/junction path refused")
        if candidate.exists():
            attributes = getattr(candidate.stat(follow_symlinks=False), "st_file_attributes", 0)
            need(not attributes & 0x400, "Reparse-point path refused")
    return path


def reference(path):
    path = no_redirects(path).resolve(strict=True)
    need(path.is_file() and not path.is_symlink(), "Evidence must be a regular file")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked_ref(value):
    need(isinstance(value, dict) and set(value) == {"path", "sha256"}
         and isinstance(value["path"], str) and isinstance(value["sha256"], str)
         and SHA.fullmatch(value["sha256"]), "Exact hash-bound evidence reference required")
    actual = reference(value["path"])
    need(actual["sha256"] == value["sha256"], "Evidence digest changed")
    return actual


def exclusive_bytes(path, data):
    """Never replace existing proof or census bytes, including on errors."""
    path = no_redirects(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        no_redirects(path)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return reference(path)


def exclusive_json(path, value):
    return exclusive_bytes(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def validate_binding(binding):
    need(isinstance(binding, dict) and set(binding) == CELL_FIELDS, "Exact twelve-field binding required")
    need(all(isinstance(value, str) and value.strip() == value and value for value in binding.values()),
         "Nonempty string binding fields required")
    need(binding["effort"] == "max" and SESSION.fullmatch(binding["session_id"]), "MAX session binding required")
    need(all(SHA.fullmatch(binding[key]) for key in CELL_FIELDS if key.endswith("sha256")), "Invalid source binding digest")


def creation_time(value):
    need(isinstance(value, str), "Missing process creation time")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        need(instant.tzinfo is not None, "Ambiguous process creation time")
        return instant.astimezone(UTC).timestamp()
    except (ValueError, OverflowError) as exc:
        raise CapacityError("Invalid process creation time") from exc


def argument(command, name):
    # Windows command lines; accept one exact flag with quoted or bare value.
    pattern = rf'(?:^|\s){re.escape(name)}(?:=|\s+)(?:"([^"]*)"|([^\s"]+))(?=\s|$)'
    matches = list(re.finditer(pattern, command, re.IGNORECASE))
    occurrences = re.findall(rf'(?:^|\s){re.escape(name)}(?=\s|=|$)', command, re.IGNORECASE)
    need(len(matches) == len(occurrences) == 1, f"Native identity requires exactly one {name}")
    return matches[0].group(1) if matches[0].group(1) is not None else matches[0].group(2)


def classify_processes(processes, observed_at):
    """Pure private census classification; unknown native-like identities refuse.

    The full process identity is kept only in this private return value. A known
    launcher and its direct Python worker count once only when session AND channel
    agree. Other duplicate session workers are refused, never collapsed by name.
    """
    need(isinstance(processes, list) and processes, "Complete nonempty Windows census required")
    need(finite(observed_at), "Invalid census timestamp")
    pids, workers = {}, []
    for process in processes:
        need(isinstance(process, dict) and set(process) == PROCESS_FIELDS,
             "Exact full census process fields required")
        pid, parent = process["ProcessId"], process["ParentProcessId"]
        need(type(pid) is int and pid >= 0 and type(parent) is int and parent >= 0 and pid not in pids,
             "Invalid/duplicate process identity")
        pids[pid] = process
        command, executable = process["CommandLine"], process["ExecutablePath"]
        need(command is None or isinstance(command, str), "Invalid command line")
        need(executable is None or isinstance(executable, str), "Invalid executable path")
        executable_name = (executable or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
        need(command or executable_name not in {"python.exe", "pythonw.exe", "python3.exe", "pwsh.exe", "powershell.exe"},
             "Unreadable potentially-native interpreter command line")
        text = ((command or "") + " " + (executable or "")).lower()
        relevant = ("hpc_forest" in text or "hpc-forest" in text or any(word in text for word in WORKER_MODULES)
                    or any(word in text for word in LAUNCHER_SIGNATURES))
        if not relevant:
            continue
        # Source-only producers are prohibited even when their precise module is unknown.
        need(not any(marker in text for marker in SOURCE_ONLY_SIGNATURES), "Active source-only native worker")
        role = "worker" if any(re.search(rf'(?:hpc_forest[.\\/]){name}(?:\.py)?(?:\s|"|$)', text)
                               for name in WORKER_MODULES) else None
        if role is None and any(marker in text for marker in LAUNCHER_SIGNATURES):
            role = "launcher"
        need(role is not None, "Unknown native-like hpc_forest process")
        need(command and executable and process["CreationDate"], "Incomplete native process full identity")
        need(0 <= creation_time(process["CreationDate"]) <= observed_at, "Future/invalid native creation time")
        session, channel = argument(command, "--session-id"), argument(command, "--channel")
        need(SESSION.fullmatch(session) and channel.startswith("/") and "/mailbox" in channel,
             "Native session/channel identity invalid")
        workers.append({**process, "role": role, "session_id": session, "channel": channel})
    paired = set()
    groups = []
    for worker in workers:
        if worker["role"] != "worker":
            continue
        launchers = [item for item in workers if item["role"] == "launcher" and item["ProcessId"] == worker["ParentProcessId"]]
        group = [worker]
        if launchers:
            launcher = launchers[0]
            need((launcher["session_id"], launcher["channel"]) == (worker["session_id"], worker["channel"]),
                 "Launcher/Python identity contradiction")
            need(creation_time(launcher["CreationDate"]) <= creation_time(worker["CreationDate"]),
                 "Launcher PID was created after worker; parent identity is reused or inconsistent")
            need(launcher["ProcessId"] not in paired, "Ambiguous multiple workers under native launcher")
            paired.add(launcher["ProcessId"])
            group.append(launcher)
        groups.append(group)
    groups.extend([[item] for item in workers if item["role"] == "launcher" and item["ProcessId"] not in paired])
    sessions = [group[0]["session_id"] for group in groups]
    need(len(set(sessions)) == len(sessions), "Duplicate active native session")
    return {"all_native_workers_known": True, "launcher_python_pairs_count_as_one": True,
            "source_only_active_workers": 0, "native_workers_count": len(groups), "session_ids": sessions,
            "private_native_groups": groups, "observed_at": observed_at}


def collect_windows():
    """Real collection, deliberately invoked only by the explicit admission context."""
    need(os.name == "nt", "Production census requires Windows")
    script = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); @((Get-CimInstance Win32_Process) | ForEach-Object { [ordered]@{ProcessId=[int]$_.ProcessId;ParentProcessId=[int]$_.ParentProcessId;ExecutablePath=$_.ExecutablePath;CommandLine=$_.CommandLine;CreationDate=if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {$null}} }) | ConvertTo-Json -Depth 4 -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            check=True, capture_output=True, timeout=90)
    # Raw stdout remains private. No printing of foreign command lines or stderr.
    need(result.stdout and not result.stderr.strip(), "Windows process census incomplete")
    return result.stdout


def evidence_checked(refs, binding, census_sha, *, fixture, analysis):
    need(isinstance(refs, dict) and set(refs) == EXTERNAL_EVIDENCE_FIELDS, "Five external evidence references required")
    checked, values = {}, {}
    producer_sha = reference(__file__)["sha256"]
    for name, ref in refs.items():
        actual = checked_ref(ref)
        value = read_json(actual["path"])
        fields = CELL_FIELDS | EVIDENCE_ROLE_FIELDS[name] | {"schema", "verified"}
        need(isinstance(value, dict) and set(value) == fields and value.get("schema") == EVIDENCE_SCHEMAS[name],
             "Exact role-specific evidence schema and full twelve-field binding required")
        need(value["verified"] is (False if fixture else True),
             "Evidence verdict is missing or not of the current origin")
        for key in CELL_FIELDS:
            need(value[key] == binding[key], "Evidence belongs to another cell/source/session")
        need(all(value[key] is True for key in EVIDENCE_TRUE_FIELDS[name]), "Evidence business verdict refuses admission")
        if name.endswith("producer_review"):
            need(value["decision"] == "accept" and value["reviewed_capacity_producer_sha256"] == producer_sha,
                 "Review must accept this exact capacity producer")
        if "evidence_refs" in EVIDENCE_ROLE_FIELDS[name]:
            primary = value["evidence_refs"]
            need(isinstance(primary, list) and primary, "Nonempty primary review/received-closure evidence required")
            primary_hashes = []
            for ref in primary:
                primary_ref = checked_ref(ref)
                primary_text = Path(primary_ref["path"]).read_text(encoding="utf-8-sig")
                need(primary_text.strip(), "Primary review/closure report must be readable and nonempty")
                try:
                    primary_value = json.loads(primary_text, object_pairs_hook=unique_object)
                except json.JSONDecodeError:
                    primary_value = None  # Independent human reviews can be plain UTF-8 text.
                if not fixture and isinstance(primary_value, dict):
                    need(primary_value.get("verified") is not False
                         and not any(primary_value.get(key) is True for key in ("fixture", "test_only", "neutral")),
                         "Fixture/failed primary report cannot authorize production")
                primary_hashes.append(primary_ref["sha256"])
            need(len(primary_hashes) == len(set(primary_hashes)), "Duplicate primary review/closure evidence")
        if name == "reservation_producer_review":
            need(type(value["maximum_native_workers_total"]) is int and value["maximum_native_workers_total"] == 4,
                 "Reservation review must preserve cap4")
        if name in {"source_only_absence", "other_owned_worker_reconciliation"}:
            need(value.get("private_full_census_sha256") == census_sha, "Evidence must bind this exact fresh private census")
            need(finite(value["observed_at"]) and value["observed_at"] == analysis["observed_at"], "Evidence census timestamp mismatch")
        checked[name] = actual["sha256"]
        values[name] = value
    closure = values["source_only_received_closure"]
    sessions = closure["closed_source_only_session_ids"]
    need(closure["source_only_may_resume"] is False and isinstance(sessions, list) and sessions
         and all(isinstance(session, str) and SESSION.fullmatch(session) for session in sessions)
         and len(sessions) == len(set(sessions)) and binding["session_id"] not in sessions
         and not (set(sessions) & set(analysis["session_ids"])), "Source-only closure missing or contradicted by census")
    absence = values["source_only_absence"]
    need(type(absence["source_only_active_workers"]) is int and absence["source_only_active_workers"] == 0
         and absence["source_only_active_workers"] == analysis["source_only_active_workers"]
         and absence["source_only_received_closure_sha256"] == checked["source_only_received_closure"],
         "Absence must reference this exact closed source-only state")
    reconciliation = values["other_owned_worker_reconciliation"]
    need(type(reconciliation["other_native_workers_count"]) is int
         and reconciliation["other_native_workers_count"] == analysis["native_workers_count"]
         and reconciliation["reconciled_session_ids"] == analysis["session_ids"], "Reconciliation must match every current native session")
    receipts = reconciliation["owned_worker_receipts"]
    need(isinstance(receipts, list) and len(receipts) == len(analysis["private_native_groups"]),
         "One ownership receipt per native group required")
    for ref, group in zip(receipts, analysis["private_native_groups"], strict=True):
        receipt = read_json(checked_ref(ref)["path"])
        need(isinstance(receipt, dict) and set(receipt) == {"schema", "verified", "ownership_established", "session_id", "channel", "processes"}
             and receipt["schema"] == "hpc-forest-native-owned-worker-identity-v1"
             and receipt["verified"] is (not fixture) and receipt["ownership_established"] is True
             and receipt["session_id"] == group[0]["session_id"] and receipt["channel"] == group[0]["channel"]
             and receipt["processes"] == [{key: process[key] for key in PROCESS_FIELDS} for process in group],
             "Owned worker receipt must match exact current PID/parent/executable/command/creation identity")
    return checked


def pending_reservations(registry_root, binding, analysis, *, fixture):
    """Pending reservations never expire implicitly; reconcile them explicitly."""
    pending = set()
    for path in sorted(registry_root.glob("*.reservation.json")):
        need(not path.is_symlink(), "Symlink reservation refused")
        value = read_json(path)
        need(isinstance(value, dict) and value.get("schema") == "hpc-forest-matrix15-single-slot-reservation-v1",
             "Unknown global registry entry")
        validate_binding({key: value.get(key) for key in CELL_FIELDS})
        need(type(value.get("consumed")) is bool and type(value.get("verified")) is bool,
             "Invalid global reservation state")
        need(value["verified"] is (not fixture), "Mixed production/fixture reservation registry")
        need(value["session_id"] != binding["session_id"], "Session already owns a reservation; no replay")
        if not value["consumed"]:
            need(value["session_id"] not in pending, "Duplicate pending native session")
            pending.add(value["session_id"])
    return pending - set(analysis["session_ids"])


@contextmanager
def exclusive_capacity(lock_path, registry_root, binding, output, now=None, *, evidence_factory, collector=None):
    """Reserve one slot, yielding private/local refs while retaining the O_EXCL lock.

    ``evidence_factory(census_ref, analysis)`` runs under that lock and must return
    the five external refs in EXTERNAL_EVIDENCE_FIELDS. Injected collectors are
    fixtures forever: all output verdicts and external proofs must be False.
    Raw census is saved under registry_root/private, never in output/projection.
    Paths in returned refs are absolute local paths for the caller to transport.
    """
    validate_binding(binding)
    fixture = collector is not None
    need(now is None or finite(now), "Invalid current time")
    if not fixture and now is not None:
        need(0 <= time.time() - now < 600, "Production current time must be fresh and nonfuture")
    lock_path, registry_root, output = (no_redirects(path) for path in (lock_path, registry_root, output))
    need(lock_path.parent.is_dir() and registry_root.is_dir() and output.is_dir(), "Explicit existing private/output roots required")
    need(not any(path.is_symlink() for path in (lock_path, registry_root, output)), "Symlink root refused")
    registry_root, output = registry_root.resolve(), output.resolve()
    need(not output.is_relative_to(registry_root) and not registry_root.is_relative_to(output),
         "Private registry and exported output trees must be disjoint")
    names = ("slot-reservation.json", "owned-lane-projection.json", "worker-lane-admission.json")
    need(not any((output / name).exists() for name in names), "Admission output collision; never overwrite")
    token = (uuid.uuid4().hex + "\n").encode()
    exclusive_bytes(lock_path, token)
    lock_identity = lock_path.stat().st_dev, lock_path.stat().st_ino

    def check_lock():
        need(not lock_path.is_symlink() and lock_path.is_file(), "Global capacity lock disappeared or changed")
        stat = lock_path.stat()
        need((stat.st_dev, stat.st_ino) == lock_identity and lock_path.read_bytes() == token,
             "Global capacity lock ownership changed; preserve lock")

    try:
        observed_at = time.time() if not fixture or now is None else now
        raw = (collect_windows if collector is None else collector)()
        need(isinstance(raw, bytes) and raw, "Census must preserve raw stdout bytes")
        instant = time.time() if not fixture or now is None else now
        need(finite(instant) and 0 <= instant - observed_at < 600, "Stale/future census")
        reservation_id = uuid.uuid4().hex
        private = registry_root / "private"
        no_redirects(private)
        private.mkdir(exist_ok=True)
        no_redirects(private)
        need(private.resolve(strict=True).parent == registry_root
             and not private.resolve(strict=True).is_relative_to(output), "Private census escaped registry or entered output")
        census_ref = exclusive_bytes(private / (reservation_id + ".census.json"), raw)
        processes = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
        analysis = classify_processes(processes, observed_at)
        need(binding["session_id"] not in analysis["session_ids"], "New cell session already active")
        pending = pending_reservations(registry_root, binding, analysis, fixture=fixture)
        count = analysis["native_workers_count"] + len(pending)
        need(count < 4, "No global native slot under cap4 including pending reservations")
        evidence = evidence_checked(evidence_factory(census_ref, analysis), binding, census_ref["sha256"], fixture=fixture, analysis=analysis)
        check_lock()
        current = time.time() if not fixture or now is None else now
        need(finite(current) and 0 <= current - observed_at < 600, "Capacity proofs became stale")
        cache = registry_root / (reservation_id + ".cache")
        cache.mkdir()  # exclusive new cache identity, never reuse another session's directory
        no_redirects(cache)
        verified = not fixture
        reservation = {**binding, "schema": "hpc-forest-matrix15-single-slot-reservation-v1", "verified": verified,
            "reservation_id": reservation_id, "exclusive_global_lock_held_at_census": True,
            "all_native_workers_known": True, "launcher_python_pairs_count_as_one": True,
            "observed_at": observed_at, "active_native_workers_before_start": count,
            "maximum_native_workers_total": 4, "one_cell_only": True, "one_submission_only": True,
            "consumed": False, "private_full_census_sha256": census_ref["sha256"]}
        # Persist the pending slot first. Any subsequent failure remains fail-closed.
        registry_ref = exclusive_json(registry_root / (reservation_id + ".reservation.json"), reservation)
        reservation_ref = exclusive_json(output / names[0], reservation)
        evidence.update(private_full_census=census_ref["sha256"], global_slot_reservation=reservation_ref["sha256"])
        projection = {**binding, "schema": "hpc-forest-matrix15-owned-lane-projection-v1", "verified": verified,
            "other_native_workers_count": count, "active_native_workers_before_start": count,
            "maximum_native_workers_total": 4, "observed_at": observed_at,
            "observation_origin": "parent-private-Windows-census", "windows_census_observed_by_arm": False,
            "full_census_exported": False, "foreign_configuration_or_credentials_exported": False,
            "evidence_sha256": evidence, "all_native_workers_known": True,
            "launcher_python_pairs_count_as_one": True, "source_only_active_workers": 0}
        projection_ref = exclusive_json(output / names[1], projection)
        lane = {**binding, "schema": "hpc-forest-matrix15-worker-lane-admission-v1", "verified": verified,
            "maximum_native_workers_total": 4, "active_native_workers_before_start": count,
            "full_census_locally_verified": verified, "new_cache_registry_root": True,
            "native_calls_started": 0, "observed_at": observed_at, "private_full_census_sha256": census_ref["sha256"],
            "minimal_owned_observations": projection_ref, "slot_reservation": reservation_ref}
        lane_ref = exclusive_json(output / names[2], lane)
        check_lock()
        yield {"lane": lane_ref, "projection": projection_ref, "reservation": reservation_ref,
               "private_census": census_ref, "registry_reservation": registry_ref, "new_cache_root": str(cache.resolve()),
               "verified": verified, "pending_sessions_count": len(pending)}
    finally:
        check_lock()
        lock_path.unlink()
