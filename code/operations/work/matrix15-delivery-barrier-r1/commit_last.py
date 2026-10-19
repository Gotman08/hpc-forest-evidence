"""Explicit transfer decorator prototype; importing it performs no action.

Composition, after a separately reviewed admission: projection(barrier(transport)).
The barrier sees final projected wire files. It supplies no admission or launcher.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

CELL_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id",
               "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
PROJECTION_FIELDS = {"schema", "kind", "record_without_private_argv", "argv_public", "private_record_sha256",
                     "private_argv_sha256", "private_skill_override_sha256", "task_cli_policy_sha256",
                     "private_skill_path_count", "private_review_required", "private_argv_verified",
                     "projection_is_executable", "raw_record_exported"}
KINDS = {"response.json": ("response", "responses", "response.json"),
         "response-ready.json": ("ready", "responses", "ready.json"),
         "invocation.json.arm-projection.json": ("invocation", "logs", "invocation.json"),
         "codex.jsonl.json.arm-projection.json": ("process", "logs", "codex.jsonl.json"),
         "delivered.json": ("delivered", "logs", "delivered.json"),
         "codex.jsonl": ("other", "logs", "codex.jsonl")}


class BarrierError(ValueError):
    """Fail closed; this decorator never retries a failed or repeated upload."""


def need(condition, message):
    if not condition:
        raise BarrierError(message)


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def remote_path(value):
    need(isinstance(value, str) and value.startswith("/") and "\\" not in value and "\0" not in value
         and str(PurePosixPath(value)) == value and all(p not in {"", ".", ".."} for p in value.split("/")[1:]),
         "Exact ordinary POSIX destination required")
    return value


def snapshot(value):
    path = Path(value)
    need(path.is_absolute() and ".." not in path.parts and all(
        not p.is_symlink() and not getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents))
        and path.is_file(), "Ordinary absolute local file required; links refused")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    need((before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino),
         "Local source changed while hashing")
    return {"path": str(path.resolve()), "sha256": digest.hexdigest(), "bytes": after.st_size}


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "Duplicate JSON key")
        value[key] = item
    return value


def no_constant(_value):
    raise BarrierError("Nonfinite JSON")


def object_file(ref):
    need(ref["bytes"] <= 16 * 1024 * 1024, "Bounded metadata JSON required")
    raw = Path(ref["path"]).read_bytes()
    need(len(raw) == ref["bytes"] and hashlib.sha256(raw).hexdigest() == ref["sha256"], "Metadata changed")
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=no_constant)
    need(isinstance(value, dict), "Metadata JSON object required")
    return value


class CommitLastTransfers:
    """Defer READY until response, both wire projections and delivery are verified.

    No remote atomic no-overwrite/no-follow guarantee is added. The caller must
    establish a fresh exclusively owned remote channel/nonce before integration.
    """

    def __init__(self, transfer, channel, binding, *, policy_sha256):
        need(isinstance(binding, dict) and set(binding) == CELL_FIELDS
             and all(isinstance(v, str) and v and "\0" not in v for v in binding.values()), "Exact expected twelve-field binding required")
        need(re.fullmatch(r"[0-9a-f]{32}", binding["session_id"]) is not None
             and re.fullmatch(r"[0-9]+", binding["job_id"]) is not None and binding["effort"] == "max"
             and all(sha(binding[k]) for k in ("source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"))
             and sha(policy_sha256), "Expected binding/policy identity malformed")
        root = remote_path(binding["remote_root"])
        need(remote_path(channel) == root + "/results-" + binding["job_id"] + "/mailbox", "Channel differs from expected cell/job")
        need(callable(getattr(transfer, "upload", None)), "Explicit verified transfer required")
        self.transfer, self.channel = transfer, channel
        self.binding, self.policy_sha256 = copy.deepcopy(binding), policy_sha256
        self._lock, self._events = asyncio.Lock(), []
        self._seen, self._committed, self._items, self._pending = set(), set(), {}, None
        self._nonce, self._failed = None, False

    def __getattr__(self, name):
        return getattr(self.transfer, name)

    @property
    def events(self):
        return copy.deepcopy(self._events)

    @property
    def pending(self):
        return copy.deepcopy(self._pending)

    def _event(self, kind, **values):
        self._events.append({"order": len(self._events) + 1, "kind": kind, **copy.deepcopy(values)})

    def _identity(self, path, remote):
        remote_path(remote)
        if path.name == "worker-ready.json":
            need(remote == self.channel + "/worker-ready.json", "Worker readiness destination differs")
            return "other", None
        need(path.name in KINDS, "Unrecognized wire filename; no raw metadata bypass")
        kind, directory, suffix = KINDS[path.name]
        nonce = path.parent.name
        need(re.fullmatch(r"[0-9a-f]{32}", nonce) is not None
             and remote == self.channel + "/" + directory + "/" + nonce + "." + suffix,
             "Nonce or exact destination differs")
        need(nonce not in self._committed and self._nonce in {None, nonce}, "Only one active, never replayed nonce permitted")
        self._nonce = nonce
        return kind, nonce

    def _projection(self, value, kind):
        need(set(value) == PROJECTION_FIELDS and value["schema"] == "hpc-forest-r2e-private-cli-metadata-projection-v1"
             and value["kind"] == kind and value["task_cli_policy_sha256"] == self.policy_sha256
             and value["private_review_required"] is True
             and all(value[k] is False for k in ("private_argv_verified", "projection_is_executable", "raw_record_exported"))
             and all(sha(value[k]) for k in ("private_record_sha256", "private_argv_sha256", "private_skill_override_sha256"))
             and type(value["private_skill_path_count"]) is int and 0 < value["private_skill_path_count"] <= 512
             and isinstance(value["record_without_private_argv"], dict) and "argv" not in value["record_without_private_argv"]
             and isinstance(value["argv_public"], list) and value["argv_public"]
             and all(isinstance(v, str) and v and "\0" not in v for v in value["argv_public"]), "Exact non-executable projection required")

    def _prerequisites(self, delivered):
        need(self._pending is not None and set(self._items) == {"response", "invocation", "process"}, "Pending READY and all three verified prerequisites required")
        for ref in [self._pending["local"], *(item["local"] for item in self._items.values())]:
            need(snapshot(ref["path"]) == ref, "Verified prerequisite changed before commit")
        response = object_file(self._items["response"]["local"])
        ready = object_file(self._pending["local"])
        invocation = object_file(self._items["invocation"]["local"])
        process = object_file(self._items["process"]["local"])
        self._projection(invocation, "invocation")
        self._projection(process, "process")
        for record in (response, invocation["record_without_private_argv"], process["record_without_private_argv"], delivered):
            need(record.get("nonce", self._nonce) == self._nonce
                 and all(key not in record or record[key] == value for key, value in self.binding.items()),
                 "Metadata nonce or optional cell identity contradicts expected binding")
        need(response.get("nonce") == self._nonce and response.get("session_id") == self.binding["session_id"]
             and response.get("model") == self.binding["model"] and response.get("reasoning_effort") == self.binding["effort"]
             and sha(response.get("request_sha256")), "Response identity differs")
        expected_response = self._items["response"]["local"]
        need(set(ready) == {"sha256", "bytes"} and ready["sha256"] == expected_response["sha256"]
             and type(ready["bytes"]) is int and ready["bytes"] == expected_response["bytes"], "READY does not describe actual response bytes")
        record = invocation["record_without_private_argv"]
        need(record.get("request_sha256") == response["request_sha256"] and record.get("model") == self.binding["model"]
             and record.get("reasoning_effort") == self.binding["effort"] and record.get("source_execution_allowed") is False,
             "Invocation differs from response and expected cell")
        need(all(invocation[k] == process[k] for k in ("argv_public", "private_argv_sha256", "private_skill_override_sha256",
             "task_cli_policy_sha256", "private_skill_path_count")), "Process projection belongs to another invocation")
        need(all(delivered.get(k) == v for k, v in self.binding.items())
             and delivered.get("nonce", self._nonce) == self._nonce
             and delivered.get("request_sha256") == response["request_sha256"]
             and delivered.get("response_sha256") == expected_response["sha256"], "Delivered digest or expected cell binding differs")

    async def _real(self, local, remote, kind):
        self._event("transfer-attempt", artifact=kind, local=local, remote=remote)
        payload = await self.transfer.upload(Path(local["path"]), remote)
        self._event("transfer-returned", artifact=kind, local=local, remote=remote, receipt=payload)
        need(isinstance(payload, dict) and payload.get("ok") is True and payload.get("verifie") is True
             and payload.get("transport") == "scp" and payload.get("sent") == local["path"] and payload.get("to") == remote
             and type(payload.get("bytes")) is int and payload["bytes"] == local["bytes"]
             and all(payload.get(k) == local["sha256"] for k in ("remote_sha256", "empreinte_locale", "empreinte_distante"))
             and "verified" not in payload and "deferred" not in payload, "Exact verified RomeoFiles flat payload required")
        need(snapshot(local["path"]) == local, "Local source changed during transfer")
        result = {"deferred": False, "verified": True, "local": local, "remote": remote, "receipt": copy.deepcopy(payload)}
        self._event("transfer-verified", artifact=kind, **result)
        return result

    async def upload(self, local, remote):
        async with self._lock:
            need(not self._failed, "Barrier failed; retry forbidden")
            try:
                path = Path(local)
                kind, nonce = self._identity(path, remote)
                need(remote not in self._seen, "Repeated destination forbidden; never overwrite in this instance")
                self._seen.add(remote)
                source = snapshot(path)
                if kind == "ready":
                    need(self._pending is None and "response" in self._items, "Only one READY pending after verified response")
                    ready = object_file(source)
                    response = self._items["response"]["local"]
                    need(set(ready) == {"sha256", "bytes"} and ready["sha256"] == response["sha256"]
                         and type(ready["bytes"]) is int and ready["bytes"] == response["bytes"], "READY payload differs from response")
                    self._pending = {"nonce": nonce, "local": source, "remote": remote}
                    result = {"deferred": True, "verified": False, "pending": self.pending}
                    self._event("deferred", artifact="ready", **result)
                    return result
                if kind == "delivered":
                    delivered = object_file(source)
                    self._prerequisites(delivered)
                result = await self._real(source, remote, kind)
                if kind in {"response", "invocation", "process"}:
                    self._items[kind] = copy.deepcopy(result)
                if kind == "delivered":
                    self._prerequisites(delivered)
                    need(snapshot(source["path"]) == source, "Delivered source changed before READY")
                    result["ready_commit"] = await self._real(self._pending["local"], self._pending["remote"], "ready")
                    self._committed.add(nonce)
                    self._pending, self._items, self._nonce = None, {}, None
                return result
            except BaseException as exc:
                self._failed = True
                self._event("failure", exception_type=type(exc).__name__, ready_publication_may_be_unknown=
                            bool(self._events and self._events[-1].get("artifact") == "ready" and self._events[-1]["kind"] in {"transfer-attempt", "transfer-returned"}))
                raise
