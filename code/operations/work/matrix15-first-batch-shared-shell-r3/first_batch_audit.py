"""Cold, fail-closed Matrix15 private first-batch audit. No CLI/model/transport execution.

Only locally received ordinary files are read. The output is a proposal for root
review; this program has no upload, authorization install, or worker capability.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import math
import os
import re
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from subprocess import list2cmdline

ZIP_SHA = "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
RUNTIME_SHA = "91684ae8d3d0457d81d049bf6e096c02601fdbdc67fc762fdf697bdc23c35f2b"
INPUT_SCHEMA = "hpc-forest-matrix15-first-batch-cold-audit-input-v2"
HASH = re.compile(r"[a-f0-9]{64}")
NONCE = re.compile(r"[a-f0-9]{32}")
PRIVATE_FIELDS = {"invocation_sha256", "process_sha256", "argv_sha256",
                  "skill_override_sha256", "task_cli_policy_sha256"}
CACHE_FILES = {"downloaded-request.json", "request.json", "generation-claimed.json",
               "response.json", "response-ready.json", "delivered.json", "invocation.json",
               "codex.jsonl.json", "cli-diagnostics.json", "codex.jsonl", "instructions.txt",
               "output-schema.json"}


class Refusal(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Refusal(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate JSON member")
        result[key] = value
    return result


def parse(raw):
    need(len(raw) <= 8 * 1024 * 1024, "JSON evidence exceeds cold-reader bound")
    return json.loads(raw.decode("utf8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refusal("Nonfinite JSON")))


def ordinary(path):
    path = Path(path)
    need(path.is_absolute() and path.is_file() and ".." not in path.parts,
         "Exact absolute ordinary local file required")
    need(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                 for p in (path, *path.parents)), "Linked local evidence is forbidden")
    need(path.stat().st_size <= 512 * 1024 * 1024, "Evidence file exceeds cold-reader bound")
    return path


def local_ref(path):
    path = ordinary(path)
    before = path.stat()
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checksum.update(block)
    after = path.stat()
    need(before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns,
         "Local evidence changed while streaming its digest")
    return {"path": str(path), "sha256": checksum.hexdigest(), "bytes": after.st_size}


def checked_local(ref):
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256", "bytes"}
         and isinstance(ref["path"], str) and HASH.fullmatch(str(ref["sha256"]))
         and type(ref["bytes"]) is int and ref["bytes"] >= 0, "Exact sized local reference required")
    path = ordinary(ref["path"])
    need(local_ref(path) == ref, "Local evidence bytes or digest changed")
    return path


def ref2(ref):
    return {key: ref[key] for key in ("path", "sha256")}


def remote_ref(ref):
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}
         and isinstance(ref["path"], str) and HASH.fullmatch(str(ref["sha256"])),
         "Exact original ARM reference required")
    path = PurePosixPath(ref["path"])
    need(path.is_absolute() and ".." not in path.parts and path.as_posix() == ref["path"]
         and "\\" not in ref["path"] and not any(c in ref["path"] for c in "\0\n\r"),
         "Original canonical ARM path required")
    return ref


def response_value(raw):
    """Read only a saved raw MCP result, optionally in the root observation wrapper."""
    def positive(value):
        need(isinstance(value, dict) and value.get("error") is None and value.get("isError") is not True
             and value.get("verified") is not False
             and not any(value.get(k) is True for k in
                         ("neutral", "synthetic", "fixture", "prepared_only", "test_only", "prepared"))
             and value.get("evidence_origin") not in {"prepared", "neutral", "synthetic", "fixture"},
             "Prepared/neutral/negative/error transfer result refused")
    positive(raw)
    if raw.get("schema") == "hpc-forest-primary-tool-observation-v1":
        need(raw.get("tool") == "mcp__romeo__download_from_romeo", "Wrong transfer observation tool")
        raw = raw["response"]
        positive(raw)
    need(raw.get("isError") is not True, "Transfer tool returned an error")
    value = raw.get("structuredContent")
    texts = [parse(item["text"].encode("utf8")) for item in raw.get("content", [])
             if item.get("type") == "text"]
    if value is None:
        need(len(texts) == 1, "Saved transfer lacks one structured response")
        value = texts[0]
    need(all(text == value for text in texts), "MCP transfer text/structured data disagree")
    need(isinstance(value, dict), "Malformed raw transfer result")
    positive(value)
    return value


BINDING_FIELDS = {"scope_id", "cell_key", "subject_id", "model", "effort", "session_id", "job_id", "remote_root", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256", "r1_contract_sha256"}
EXTERNAL_SHELL_SHA = "7e3a3f9d6715ccab40ba328d2220f59f70133ac164ac491a07c5cff2dc035753"
EXTERNAL_SHELL_BYTES = 1366952
EXTERNAL_COPY_ROOT = "/gpfs/scratch/nimarano/hpc-forest-external-shell-20261019-root-01"
# This immutable export proves binary contents, not a later cell's execution.
# Current execution/command-stream bindings are still checked independently.
EXTERNAL_CONTENT_BINDING = {
    "scope_id": "hpc-forest-matrix15-native-max-r2",
    "cell_key": "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23",
    "subject_id": "2020-quicksort", "model": "gpt-6-luna", "effort": "max",
    "session_id": "9a681c2826854a4b885e94c5e6243f0a", "job_id": "755562",
    "remote_root": "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-r2-9a681c2826854a4b885e94c5e6243f0a",
    "source_zip_sha256": ZIP_SHA,
    "plan_sha256": "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f",
    "preparation_manifest_sha256": "d60b93312c34319386cc7057fd77248df38282ee717ee63ca80ad911cf5e7313",
    "r1_contract_sha256": "c2fa077535e04b8d3f65ca4e4705ba178b55de6513aa4d1f071374bf9a776a16",
}
EXTERNAL_EXPORTER = {"job_id": "755597", "node": "romeo-a057", "architecture": "aarch64", "model_calls": 0}


class Evidence:
    """Exact refs; one historical, manifest-bound /bin/sh byte-copy is supported."""
    def __init__(self, received, local):
        self.map, self.inventory = {}, []
        self.received_keys, self.external_program_copies = set(), []
        need(isinstance(received, list) and 0 < len(received) <= 5000, "Bounded received inventory required")
        need(isinstance(local, list) and len(local) <= 1000, "Bounded local inventory required")
        for item in received:
            need(set(item) == {"remote_ref", "local_ref", "transfer_receipt"}, "Exact received evidence fields required")
            original = remote_ref(item["remote_ref"])
            path = checked_local(item["local_ref"])
            raw = parse(checked_local(item["transfer_receipt"]).read_bytes())
            transfer = response_value(raw)
            size, checksum = item["local_ref"]["bytes"], item["local_ref"]["sha256"]
            need(original["sha256"] == checksum and transfer.get("ok") is True and transfer.get("transport") == "scp"
                 and transfer.get("verifie") is True and transfer.get("downloaded") == original["path"]
                 and transfer.get("to") == str(path) and transfer.get("bytes") == size
                 and all(transfer.get(k) == checksum for k in
                         ("remote_sha256", "empreinte_locale", "empreinte_distante")),
                 "Actual verified download receipt differs from received bytes or original ARM ref")
            if raw.get("schema") == "hpc-forest-primary-tool-observation-v1":
                allowed = {"remote_path": original["path"], "local_path": str(path), "verify": True}
                need(raw.get("arguments") in (allowed, {**allowed, "recursive": False}),
                     "Primary transfer arguments differ")
            self.add(original, path)
            self.received_keys.add((original["path"], original["sha256"]))
            self.inventory.append(item)
        for item in local:
            self.add(ref2(item), checked_local(item))
            self.inventory.append({"local_ref": item})

    def external_copies(self, packets, binding):
        need(isinstance(packets, list) and len(packets) <= 1, "Only one explicit external shell copy is supported")
        need(not self.external_program_copies, "External program copy already installed")
        for packet in packets:
            need(isinstance(packet, dict) and set(packet) == {"manifest_ref", "copy_ref"}, "Exact external copy packet required")
            for ref in packet.values():
                remote_ref(ref)
                need((ref["path"], ref["sha256"]) in self.received_keys, "External manifest/copy must have actual original-path SCP receipts")
            need(packet["manifest_ref"]["path"] == EXTERNAL_COPY_ROOT + "/manifest.json"
                 and packet["copy_ref"]["path"] == EXTERNAL_COPY_ROOT + "/bin-sh", "Unreviewed external export root/path")
            manifest = self.read(packet["manifest_ref"])
            need(set(manifest) == {"schema", "binding", "source_ref", "copy_ref", "exporter"}
                 and manifest.get("schema") == "hpc-forest-matrix15-external-program-copy-v1"
                 and isinstance(binding, dict) and set(binding) == BINDING_FIELDS
                 and manifest.get("binding") == EXTERNAL_CONTENT_BINDING,
                 "External copy historical content binding differs")
            source, copy = manifest["source_ref"], manifest["copy_ref"]
            expected = {"path": "/bin/sh", "sha256": EXTERNAL_SHELL_SHA, "bytes": EXTERNAL_SHELL_BYTES}
            need(source == expected and copy == {**expected, "path": EXTERNAL_COPY_ROOT + "/bin-sh"}
                 and ref2(copy) == packet["copy_ref"], "External source/copy digest, bytes or identity differs")
            exporter = manifest["exporter"]
            need(isinstance(exporter, dict) and exporter == EXTERNAL_EXPORTER
                 and type(exporter["model_calls"]) is int and exporter["job_id"] != binding["job_id"],
                 "External exporter differs from the historical zero-model ARM job")
            copied_path = self.resolve(copy)
            self.add(ref2(source), copied_path)
            self.external_program_copies.append({**packet, "manifest": manifest, "local_copy": local_ref(copied_path)})

    def add(self, ref, path):
        key = (ref["path"], ref["sha256"])
        need(key not in self.map and all(existing[0] != key[0] for existing in self.map),
             "Duplicate or inconsistent exact evidence reference")
        self.map[key] = path

    def resolve(self, ref):
        need(isinstance(ref, dict) and set(ref) in ({"path", "sha256"}, {"path", "sha256", "bytes"}),
             "Resolver accepts only exact refs")
        need(HASH.fullmatch(str(ref.get("sha256", ""))), "Invalid evidence digest")
        key = (ref.get("path"), ref["sha256"])
        need(key in self.map, "Unreceived/unlisted exact reference: " + str(ref.get("path")))
        path = ordinary(self.map[key])
        need(local_ref(path)["sha256"] == ref["sha256"], "Evidence changed during cold audit")
        if "bytes" in ref:
            need(type(ref["bytes"]) is int and ref["bytes"] == path.stat().st_size, "Evidence sized ref differs")
        return path

    def read(self, ref):
        value = parse(self.resolve(ref).read_bytes())
        need(isinstance(value, dict), "Object evidence required")
        return value

    def recheck(self):
        for path, checksum in self.map:
            self.resolve({"path": path, "sha256": checksum})
        for item in self.inventory:
            for key in ("local_ref", "transfer_receipt"):
                if key in item:
                    checked_local(item[key])


def sealed_source(source):
    """Verify pinned ZIP, complete inventory and every imported source before importing."""
    need(set(source) == {"project_root", "source_zip", "runtime_manifest"}, "Exact source binding required")
    archive = checked_local(source["source_zip"])
    manifest = checked_local(source["runtime_manifest"])
    need(source["source_zip"]["sha256"] == ZIP_SHA and source["runtime_manifest"]["sha256"] == RUNTIME_SHA,
         "Only sealed native source127 is supported")
    inventory = parse(manifest.read_bytes())
    need(isinstance(inventory, dict) and len(inventory) == 127, "Complete sealed source127 inventory required")
    root = Path(source["project_root"])
    need(root.is_absolute() and root.is_dir() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
         for p in (root, *root.parents)), "Ordinary absolute sealed source directory required")
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        need(len(infos) == 127 and len({i.filename for i in infos}) == 127
             and {i.filename for i in infos} == {"HPC-Forest/" + name for name in inventory},
             "Source archive membership differs")
        for info in infos:
            relative = info.filename.removeprefix("HPC-Forest/")
            name = PurePosixPath(relative)
            need(not info.is_dir() and not name.is_absolute() and ".." not in name.parts
                 and info.file_size < 8 * 1024 * 1024 and ((info.external_attr >> 16) & 0o170000) != 0o120000,
                 "Unsafe source ZIP member")
            need(HASH.fullmatch(str(inventory[relative])) and sha(package.read(info)) == inventory[relative]
                 and sha(ordinary(root.joinpath(*name.parts)).read_bytes()) == inventory[relative],
                 "Sealed source127 file differs: " + info.filename)
    # Extra importable Python modules would let a mutated tree cross the hash gate.
    expected_python = {name for name in inventory if name.startswith("src/") and name.endswith(".py")}
    need({p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py")} == expected_python,
         "Unexpected unsealed importable Python source")
    for name, module in tuple(sys.modules.items()):
        if name == "hpc_forest" or name.startswith("hpc_forest."):
            need(Path(getattr(module, "__file__", "")).resolve().is_relative_to((root / "src").resolve()),
                 "Another hpc_forest module is already loaded")
    sys.dont_write_bytecode = True

    class SourceOnlyLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            path = ordinary(self.path)
            relative = path.relative_to(root).as_posix()
            raw = path.read_bytes()
            need(sha(raw) == inventory[relative], "Source changed before its source-only import")
            return compile(raw, str(path), "exec", dont_inherit=True)

    class SealedFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "hpc_forest" and not fullname.startswith("hpc_forest."):
                return None
            stem = "src/" + fullname.replace(".", "/")
            package = stem + "/__init__.py"
            filename = package if package in inventory else stem + ".py"
            need(filename in inventory, "Unsealed hpc_forest import refused")
            actual = root.joinpath(*PurePosixPath(filename).parts)
            loader = SourceOnlyLoader(fullname, str(actual))
            return importlib.util.spec_from_file_location(fullname, actual, loader=loader,
                submodule_search_locations=[str(actual.parent)] if filename == package else None)

    # Cached bytecode is preserved and never loaded. Hash-checked text is compiled
    # directly, even if pytest or an earlier operator created __pycache__ files.
    sys.meta_path.insert(0, SealedFinder())
    modules = tuple(importlib.import_module("hpc_forest." + name) for name in
                    ("codex_process", "native_matrix15", "matrix15_first_batch"))
    for module in modules:
        need(Path(module.__file__).resolve().is_relative_to((root / "src").resolve()), "Imported validator origin differs")
    return modules


def expected_argv(client, executable, model, policy, directory):
    """Pure rendering of the verified source127 command_for, without its writes/which."""
    directory = Path(directory)
    argv = [executable, "exec", "--ignore-user-config", "--strict-config", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
            "--model", model, "--output-schema", str(directory / "output-schema.json"),
            "--output-last-message", str(directory / "agent-result.json"), "-C", str(directory)]
    overrides = {"model_reasoning_effort": "max", "model_instructions_file": str(directory / "instructions.txt"),
                 "model_context_window": 65536, "project_doc_max_bytes": 0, "skills.max_context_tokens": 1,
                 "skills.config": [{"path": p, "enabled": False} for p in policy["skill_candidate_directories"]],
                 "skills.include_instructions": False, "skills.bundled.enabled": False, "approval_policy": "never",
                 "forced_login_method": "chatgpt", "web_search": "disabled", "features.skip_host_skill_discovery": False,
                 **{"features." + k: v for k, v in client.TASK_CLI_FEATURES.items() if k != "skip_host_skill_discovery"}}
    for key, value in overrides.items():
        argv.extend(["--config", key + "=" + client.toml_override_value(value)])
    argv.append("-")
    need(len(list2cmdline(argv).encode("utf-16-le")) // 2 + 1 <= 32767, "Private argv exceeds Windows bound")
    return argv


@contextlib.contextmanager
def explicit_resolver(native, batch, evidence):
    previous = native.artifact, batch.artifact
    native.artifact = batch.artifact = evidence.resolve
    try:
        yield
    finally:
        native.artifact, batch.artifact = previous


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def paused_snapshot(snapshot, snapshot_ref, first, authorization, binding, now):
    identity = {**binding, "protocol_id": first.get("protocol_id")}
    fields = {"schema", *identity, "first_batch_completed", "first_start_receipt", "evaluation_snapshot",
              "first_start_public_verified", "existing_campaign_deadline", "existing_search_deadline",
              "budget_or_chronology_reset", "new_requests_created", "private_cli_argv_verified_on_ARM",
              "waiting_for_external_root_audit"}
    need(set(snapshot) == fields and snapshot.get("schema") == "hpc-forest-matrix15-first-batch-paused-v1"
         and all(snapshot.get(k) == v for k, v in identity.items()) and snapshot.get("first_batch_completed") is True
         and snapshot.get("first_start_public_verified") is True and snapshot.get("budget_or_chronology_reset") is False
         and type(snapshot.get("new_requests_created")) is int and snapshot["new_requests_created"] == 0
         and snapshot.get("private_cli_argv_verified_on_ARM") is False
         and snapshot.get("waiting_for_external_root_audit") is True, "Exact unchanged paused first-batch snapshot required")
    output = binding["remote_root"] + "/results-" + binding["job_id"]
    need(snapshot_ref["path"] == output + "/premier-batch-en-attente.json"
         and snapshot["first_start_receipt"]["path"] == output + "/premier-demarrage-verifie.json"
         and snapshot["evaluation_snapshot"]["path"] == output + "/premiere-evaluation-reelle.json"
         and snapshot["evaluation_snapshot"] == first.get("evaluation_snapshot"), "First-batch original ARM paths differ")
    need(finite(authorization.get("expires_at")) and finite(snapshot["existing_campaign_deadline"])
         and finite(snapshot["existing_search_deadline"])
         and snapshot["existing_search_deadline"] == min(snapshot["existing_campaign_deadline"] - 120,
                                                       authorization["expires_at"])
         and now < snapshot["existing_search_deadline"] and now < authorization["expires_at"],
         "Original campaign/search/auth deadline is inconsistent or expired")
    return identity, output


def audit_calls(first, authorization, binding, cache_root, private_nonces, policy_ref, evidence, client):
    cli = evidence.read(authorization["artifacts"]["cli_identity"])
    need(all(cli.get(k) == v for k, v in binding.items()) and cli.get("source_execution_allowed") is False,
         "CLI identity belongs to another cell")
    policy_path = checked_local(policy_ref)
    need(cli.get("task_cli_policy_sha256") == policy_ref["sha256"], "CLI and policy digest differ")
    policy = client.load_task_cli_policy(policy_path, policy_ref["sha256"], binding, cli["executable_sha256"])
    from hpc_forest.native_matrix15 import CLI_FILES
    need(set(cli.get("files", {})) == set(CLI_FILES), "All four CLI binary pins required")
    for name, checksum in CLI_FILES.items():
        need(cli["files"][name].get("sha256") == checksum, "CLI executable pin differs")
        evidence.resolve(cli["files"][name])
    need(cli.get("executable_sha256") == CLI_FILES["codex.exe"]
         and cli["files"]["codex.exe"]["path"] == cli.get("executable_path"), "Exact CLI path required")
    cache = Path(cache_root)
    need(cache.is_absolute() and cache.is_dir() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
         for p in (cache, *cache.parents)), "Exact ordinary private cache directory required")
    need(parse(ordinary(cache / "CELL-BINDING.json").read_bytes()) == binding, "Private cache binding differs")
    need(not (cache / "cli-technical-hold.json").exists(), "Private technical hold blocks release")
    need(all(p.parent.parent == cache and NONCE.fullmatch(p.parent.name) for p in cache.rglob("generation-claimed.json")),
         "Generation claim outside a named direct nonce directory")
    on_disk = {p.name for p in cache.iterdir() if p.is_dir() and NONCE.fullmatch(p.name)}
    need(isinstance(private_nonces, dict) and set(private_nonces) == on_disk,
         "Private inventory omits or adds a nonce directory")
    calls = first.get("all_started_calls_reconciled")
    need(isinstance(calls, list) and 0 < len(calls) <= 32, "Actual bounded first-batch calls required")
    bindings, inventory, inspected = {}, {}, []
    old_policy, old_model, old_effort = client.CLI_POLICY, client.MODEL, client.EFFORT
    client.CLI_POLICY, client.MODEL, client.EFFORT = policy, binding["model"], "max"
    try:
        for call in calls:
            request = evidence.read(call["request"])
            nonce = request.get("nonce", "")
            need(NONCE.fullmatch(nonce) and nonce not in bindings and nonce in private_nonces, "Unique completed known nonce required")
            files = private_nonces[nonce]
            need(CACHE_FILES <= set(files) <= CACHE_FILES | {"agent-result.json"}, "Exact complete private episode files required")
            for name, ref in files.items():
                path = checked_local(ref)
                need(path == cache / nonce / name, "Private file is outside the exact owned nonce cache")
                inventory[nonce + "/" + name] = {"sha256": ref["sha256"], "bytes": ref["bytes"]}
            private = call.get("private_cli_records", {})
            need(set(private) == PRIVATE_FIELDS and all(HASH.fullmatch(str(v)) for v in private.values())
                 and call.get("private_cli_review_required") is True and call.get("private_cli_argv_verified") is False,
                 "Pending private CLI digest bindings required")
            need(checked_local(files["downloaded-request.json"]).read_bytes() == evidence.resolve(call["request"]).read_bytes()
                 and parse(checked_local(files["request.json"]).read_bytes()) == request,
                 "Private and received request differ (request.json is the original Windows JSON reserialization)")
            claim = parse(checked_local(files["generation-claimed.json"]).read_bytes())
            need(set(claim) == {"request_sha256", "claimed_at"} and claim["request_sha256"] == call["request"]["sha256"]
                 and finite(claim["claimed_at"]), "Exact owned no-replay generation claim required")
            for private_name, call_name in (("response.json", "response"), ("response-ready.json", "ready"),
                                            ("delivered.json", "delivered"), ("codex.jsonl", "error_and_usage_log")):
                need(checked_local(files[private_name]).read_bytes() == evidence.resolve(call[call_name]).read_bytes(),
                     "Private and received raw delivery/log differ")
            records = {}
            expected = expected_argv(client, cli["executable_path"], binding["model"], policy, cache / nonce)
            for kind, filename in (("invocation", "invocation.json"), ("process", "codex.jsonl.json")):
                raw_ref = files[filename]
                record = parse(checked_local(raw_ref).read_bytes())
                need(raw_ref["sha256"] == private[kind + "_sha256"] and record.get("argv") == expected,
                     "Private argv differs from exact source127 constructor/policy")
                projection = client.cli_metadata_projection(checked_local(raw_ref), policy_ref["sha256"], kind)
                need(projection == evidence.read(call[kind]), "Public projection differs from actual private bytes")
                client.check_cli_metadata_projection(projection, kind, cli, binding["model"])
                need(private["argv_sha256"] == projection["private_argv_sha256"]
                     and private["skill_override_sha256"] == projection["private_skill_override_sha256"]
                     and private["task_cli_policy_sha256"] == policy_ref["sha256"], "Named private projection hashes differ")
                records[kind] = record
            invocation, process = records["invocation"], records["process"]
            need(set(invocation) == {"argv", "model", "reasoning_effort", "request_sha256", "hosted_inference", "source_execution_allowed"}
                 and invocation.get("hosted_inference") is True
                 and set(process) == {"argv", "returncode", "seconds", "timed_out", "log"}
                 and process.get("log") == str(cache / nonce / "codex.jsonl")
                 and finite(process.get("seconds")) and process["seconds"] >= 0, "Private invocation/process source layout differs")
            response, ready, delivered = (evidence.read(call[k]) for k in ("response", "ready", "delivered"))
            request_sha, response_sha = call["request"]["sha256"], call["response"]["sha256"]
            identity = {"model": binding["model"], "reasoning_effort": "max", "session_id": binding["session_id"]}
            need(all(request.get(k) == v and response.get(k) == v for k, v in identity.items())
                 and request.get("kind") == "source-proposal" and isinstance(request.get("mission_id"), str)
                 and bool(request["mission_id"]) and request.get("meta_role") in {None, "mother-preparation", "mother-synthesis"}
                 and response.get("nonce") == nonce and response.get("request_sha256") == request_sha
                 and response.get("infrastructure_error") is False and ready == {"sha256": response_sha, "bytes": files["response.json"]["bytes"]}
                 and delivered.get("request_sha256") == request_sha and delivered.get("response_sha256") == response_sha
                 and all(delivered.get(k) == v for k, v in binding.items())
                 and type(process.get("returncode")) is int and process["returncode"] == 0 and process.get("timed_out") is False
                 and invocation.get("request_sha256") == request_sha and invocation.get("model") == binding["model"]
                 and invocation.get("reasoning_effort") == "max" and invocation.get("source_execution_allowed") is False,
                 "Incomplete failed or foreign normal/private call")
            need([m.get("role") for m in request.get("messages", [])] == ["system", "user"]
                 and checked_local(files["instructions.txt"]).read_text(encoding="utf8") == request["messages"][0]["content"]
                 and parse(checked_local(files["output-schema.json"]).read_bytes()) == client.wire_schema(request["schema"]),
                 "Private instructions/schema differ from exact request")
            if response.get("error") is None:
                need("agent-result.json" in files and parse(checked_local(files["agent-result.json"]).read_bytes()) == response.get("data"),
                     "Successful delivered structured result differs from private CLI output")
            diagnostics = client.diagnostics_from_events(checked_local(files["codex.jsonl"]))
            usage, tools = client.usage_from_events(checked_local(files["codex.jsonl"]))
            need(diagnostics == parse(checked_local(files["cli-diagnostics.json"]).read_bytes())
                 and diagnostics["clean"] is True, "Strict CLI diagnostics are not clean")
            usage["cli_diagnostics_sha256"] = files["cli-diagnostics.json"]["sha256"]
            usage["cli_diagnostic_count"] = len(diagnostics["findings"])
            need(not tools and usage == response.get("usage") and usage.get("token_accounting") == "exact"
                 and usage.get("llm_calls") == 1 and usage.get("usage_parse_ambiguity") is False,
                 "Unknown usage or tool call blocks release")
            need(call.get("mission_id") == request["mission_id"] and call.get("mother_call") is bool(request.get("meta_role"))
                 and call.get("mother_phase") == request.get("meta_role") and call.get("normal_delivered") is True
                 and call.get("usage_exact") is True and type(call.get("exact_tokens")) is int
                 and call["exact_tokens"] == usage["tokens"]
                 and call.get("known_model_negative") is (response.get("error") is not None), "Source public call summary differs")
            channel = binding["remote_root"] + "/results-" + binding["job_id"] + "/mailbox"
            expected_paths = {"request": channel + "/requests/" + nonce + ".request.json",
                              "response": channel + "/responses/" + nonce + ".response.json",
                              "ready": channel + "/responses/" + nonce + ".ready.json",
                              **{field: channel + "/logs/" + nonce + suffix for field, suffix in
                                 (("invocation", ".invocation.json"), ("process", ".codex.jsonl.json"),
                                  ("delivered", ".delivered.json"), ("error_and_usage_log", ".codex.jsonl"))}}
            need(all(call[k]["path"] == v for k, v in expected_paths.items()), "Call paths differ from original owned ARM mailbox")
            bindings[nonce] = {**private, "invocation_projection_sha256": call["invocation"]["sha256"],
                               "process_projection_sha256": call["process"]["sha256"]}
            inspected.append({"nonce": nonce, "mother_phase": request.get("meta_role"), "exact_tokens": usage["tokens"],
                              "known_model_negative": response.get("error") is not None})
        need(set(bindings) == set(private_nonces), "Private collection extends or omits frozen first batch")
    finally:
        client.CLI_POLICY, client.MODEL, client.EFFORT = old_policy, old_model, old_effort
    need(first.get("first_normal_delivered_call") in [c for c in calls if not c["mother_call"]], "First normal call is not an actual reconciled child")
    reconciliation = first.get("usage_and_mother_reconciliation", {})
    costs = reconciliation.get("registry_costs", {})
    total = sum(c["exact_tokens"] for c in calls)
    need(type(costs.get("exact_tokens_used")) is int and costs["exact_tokens_used"] == total
         and all(type(costs.get(k)) is int and costs[k] == 0 for k in ("unknown_usage_calls", "bounded_usage_calls"))
         and reconciliation.get("all_delivered_tokens_exact") == total
         and reconciliation.get("budget_or_chronology_reset") is False, "First-start registry token totals differ")
    mothers = reconciliation.get("mother_claims", {})
    need(set(mothers) <= {"preparation", "synthesis"}, "Unknown mother phase")
    for phase in ("preparation", "synthesis"):
        selected = [c for c in calls if c["mother_phase"] == "mother-" + phase]
        if selected or phase in mothers:
            value = mothers.get(phase, {})
            need(value.get("status") not in {None, "started_without_final_response", "interrupted_not_replayed"}
                 and type(value.get("model_calls")) is int and value["model_calls"] in {0, 1}
                 and value["model_calls"] == len(selected) == value.get("delivered_calls_reconciled"),
                 "Unresolved/missing/extra mother claim blocks release")
    return {"call_bindings": bindings, "named_private_inventory": inventory, "calls": inspected,
            "all_private_raws_received_and_hashed": True, "argv_matches_projections_and_local_policy": True,
            "cli_diagnostics_clean": True, "raw_skill_paths_exported": False,
            "task_cli_policy_sha256": policy_ref["sha256"], "exact_tokens_all_calls": total,
            "private_skill_path_count": len(policy["skill_candidate_directories"]),
            "registry_reconciliation_source": "hash-bound-source-generated-first-start-receipt",
            "independent_SQLite_snapshot_reaudited": False}


def verify_streams(records, outcome, identity, evidence, *, experiment_id):
    """Cold checks of original command-stream receipts, with explicit received refs."""
    need(isinstance(records, list) and records and isinstance(outcome.get("logs"), list)
         and len(records) == len(outcome["logs"]), "Complete received command-stream record inventory required")
    operations = []
    for record, log in zip(records, outcome["logs"], strict=True):
        proof = evidence.read({"path": record["path"], "sha256": record["sha256"], "bytes": record["bytes"]})
        need(record["path"] == log + ".command-stream.json" and record.get("verified") is True,
             "Command-stream original path differs")
        need(proof.get("schema") == "hpc-forest-matrix15-command-execution-v1" and proof.get("verified") is True
             and proof.get("mode") == "command-stream-v1" and proof.get("phase") == "search"
             and proof.get("experiment_id") == experiment_id
             and proof.get("protocol_id") == identity["protocol_id"]
             and proof.get("operator_binding", {}).get("cell_binding") == {k: v for k, v in identity.items() if k != "protocol_id"}
             and proof.get("commit") == outcome.get("commit") and proof.get("tree_hash") == outcome.get("tree_hash")
             and proof.get("source_before") == proof.get("source_after")
             and proof.get("source_before") == {"commit": outcome.get("commit"), "tree_hash": outcome.get("tree_hash"), "clean": True}
             and proof.get("never_model_input") is True and proof.get("hashing_outside_measured_interval") is True
             and proof.get("execution_semantics_changed") is False and proof.get("case_execution_records") == []
             and all(proof.get(k) is False for k in ("individual_case_provenance_verified",
                 "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified")),
             "Command-stream source/protocol/evidence level differs")
        context = evidence.read(proof["context"])
        context_fields = {"schema", "mode", "never_model_input", "operator_binding", "protocol_id", "operation",
                          "experiment_id", "epoch", "commit", "tree_hash", "phase", "argv", "worktree", "binary_path",
                          "environment_overrides", "source_before", "binary_before", "argument_files_before",
                          "stdin_layout", "inherited_environment_captured"}
        execution_fields = context_fields | {"verified", "context", "source_after", "binary_after", "argument_files_after",
                            "returncode", "timed_out", "measured_seconds", "original_process_result",
                            "hashing_outside_measured_interval", "execution_semantics_changed", "streams",
                            "case_execution_records", "individual_case_provenance_verified",
                            "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified"}
        need(set(context) == context_fields and set(proof) == execution_fields
             and context.get("schema") == "hpc-forest-matrix15-command-context-v1"
             and all(proof.get(k) == v for k, v in context.items() if k != "schema"), "Command context differs from execution receipt")
        from hpc_forest.matrix15_provenance import command_stream_policy
        command_stream_policy({"execution_provenance": context["operator_binding"], "protocol": {}})
        need(type(context["epoch"]) is int and context["epoch"] >= 1
             and all(re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", context[k]) for k in ("commit", "tree_hash"))
             and all(isinstance(context[k], str) and context[k] for k in ("worktree", "binary_path"))
             and isinstance(context["argv"], list) and context["argv"]
             and all(isinstance(a, str) for a in context["argv"])
             and isinstance(context["environment_overrides"], dict)
             and all(isinstance(k, str) and isinstance(v, str) for k, v in context["environment_overrides"].items())
             and context["stdin_layout"] == "original_run_process_DEVNULL_unchanged"
             and context["inherited_environment_captured"] is False, "Command-source context shape differs")
        process = evidence.read(proof["original_process_result"])
        need(proof["original_process_result"]["path"] == log + ".json"
             and type(proof.get("returncode")) is int and type(proof.get("timed_out")) is bool
             and finite(proof.get("measured_seconds")) and proof["measured_seconds"] >= 0
             and process == {"argv": context["argv"], "returncode": proof["returncode"],
                            "seconds": proof["measured_seconds"], "timed_out": proof["timed_out"], "log": log},
             "Original command process/timing receipt differs")
        streams = proof.get("streams", {})
        need(set(streams) == {"combined_stdout_stderr", "separate_stdout", "separate_stderr", "layout"}
             and streams.get("separate_stdout") is None and streams.get("separate_stderr") is None
             and streams.get("layout") == "original_run_process_combined_unchanged"
             and streams.get("combined_stdout_stderr", {}).get("path") == log, "Original stream layout differs")
        evidence.resolve(streams["combined_stdout_stderr"])
        for item in [*context.get("argument_files_before", []), *proof.get("argument_files_after", [])]:
            need(set(item) == {"argument_index", "argument", "path", "sha256", "bytes"}
                 and type(item["argument_index"]) is int and 0 <= item["argument_index"] < len(context["argv"])
                 and item["argument"] == context["argv"][item["argument_index"]], "Command argument file identity differs")
            evidence.resolve({k: item[k] for k in ("path", "sha256", "bytes")})
        for key in ("binary_before", "binary_after"):
            if proof.get(key) is not None:
                evidence.resolve(proof[key])
        if proof.get("operation") != "build":
            need(proof.get("binary_before") is not None and proof.get("binary_before") == proof.get("binary_after"),
                 "Nonbuild binary changed")
        need([i for i in context.get("argument_files_before", []) if i["path"] != context["binary_path"]]
             == [i for i in proof.get("argument_files_after", []) if i["path"] != context["binary_path"]],
             "Command input files changed")
        need(proof.get("operation") in {"build", "check", "benchmark"}, "Unknown command operation")
        operations.append(proof["operation"])
    need("build" in operations, "Candidate evaluation lacks its actual build command")
    return {"records": len(records), "operations": operations, "evidence_level": "command-stream-v1",
            "independent_performance_audit_verified": False, "individual_case_provenance_verified": False}


def audit(input_value, *, now=None):
    # The injected clock is a Python testing seam only. The CLI exposes no override.
    clock = time.time if now is None else lambda: now
    observed_at = clock()
    expected = {"schema", "evidence_origin", "source", "authorization", "paused_snapshot", "received",
                "local_refs", "cache_root", "private_nonces", "policy_ref", "output_directory", "external_program_copies"}
    need(set(input_value) == expected and input_value.get("schema") == INPUT_SCHEMA
         and input_value.get("evidence_origin") == "received", "Only actual received input is admissible")
    client, native, batch = sealed_source(input_value["source"])
    evidence = Evidence(input_value["received"], input_value["local_refs"])
    authorization = evidence.read(input_value["authorization"])
    with explicit_resolver(native, batch, evidence):
        need(set(authorization) == native.AUTHORIZATION_FIELDS and authorization.get("verified") is True
             and authorization.get("schema") == "hpc-forest-matrix15-authorization-v1"
             and authorization.get("old_candidates_imported") is False and authorization.get("operator_algorithm_advice") is False
             and type(authorization.get("native_calls_started_at_authorization")) is int
             and authorization["native_calls_started_at_authorization"] == 0
             and set(authorization.get("artifacts", {})) == native.ARTIFACTS
             and authorization["artifacts"]["source_zip"]["sha256"] == ZIP_SHA
             and authorization["artifacts"]["runtime_manifest"]["sha256"] == RUNTIME_SHA,
             "Exact original admitted cell authorization required")
        binding = native.cell_binding(authorization)
        evidence.external_copies(input_value["external_program_copies"], binding)
        snapshot_ref = remote_ref(input_value["paused_snapshot"])
        snapshot = evidence.read(snapshot_ref)
        first_ref = snapshot["first_start_receipt"]
        first = evidence.read(first_ref)
        identity, _output = paused_snapshot(snapshot, snapshot_ref, first, authorization, binding, observed_at)
        need(first.get("schema") == "hpc-forest-matrix15-first-start-v1" and first.get("verified") is True
             and first.get("blocking_reasons") == [] and first.get("technical_errors_found") is False
             and first.get("invocation_unknown") is False and first.get("automatic_extension") is False
             and first.get("extension_to_other_cells_allowed") is False
             and first.get("admission_artifacts") == authorization["artifacts"]
             and all(first.get(k) == v for k, v in identity.items()) and HASH.fullmatch(str(identity["protocol_id"])),
             "Actual clean cell-bound first-start receipt required")
        evaluation = evidence.read(snapshot["evaluation_snapshot"])
        outcome = evaluation.get("outcome", {})
        real = first.get("first_real_evaluation", {})
        need(evaluation.get("never_model_input") is True and all(evaluation.get(k) == v for k, v in identity.items())
             and evaluation.get("experiment_id") == real.get("experiment_id")
             and outcome.get("status") in {"valid", "incorrect", "build_failed", "runtime_failed"}
             and outcome.get("status") == real.get("status") and native.digest(outcome) == real.get("outcome_sha256")
             and real.get("candidate_negative_preserved") is (outcome["status"] != "valid"),
             "Algorithmic outcome changed or infrastructure outcome promoted")
        need(any(c.get("mission_id") == evaluation["experiment_id"]
                 or c.get("mission_id", "").startswith(evaluation["experiment_id"] + "-h")
                 for c in first.get("all_started_calls_reconciled", []) if not c.get("mother_call")),
             "Evaluation lacks its actual delivered normal child call")
        for field in ("channel_owner", "worker_identity"):
            marker = evidence.read(first[field])
            need(all(marker.get(k) == v for k, v in binding.items()), "Worker/owner binding differs")
        origin = evidence.read(first["runtime_reference_origin"])
        need(origin.get("schema") == "hpc-forest-matrix15-runtime-reference-origin-v1" and origin.get("verified") is True
             and all(origin.get(k) == v for k, v in identity.items())
             and origin.get("reference_origin_is_current_allocation") is True
             and origin.get("qualification_timings_imported") is False, "Current allocation baseline origin required")
        origin_records = origin.get("command_stream_provenance", [])
        need(isinstance(origin_records, list) and origin_records, "Actual reference commands required")
        origin_proofs = [evidence.read({k: r[k] for k in ("path", "sha256", "bytes")}) for r in origin_records]
        origin_outcome = {"commit": origin_proofs[0]["commit"], "tree_hash": origin_proofs[0]["tree_hash"],
                          "logs": [p["streams"]["combined_stdout_stderr"]["path"] for p in origin_proofs]}
        origin_review = verify_streams(origin_records, origin_outcome, identity, evidence,
                                      experiment_id=origin["experiment_id"])
        calls = audit_calls(first, authorization, binding, input_value["cache_root"], input_value["private_nonces"],
                            input_value["policy_ref"], evidence, client)
        stream_result = verify_streams(first.get("command_stream_provenance"), outcome, identity, evidence,
                                      experiment_id=evaluation["experiment_id"])
        snapshot["self_ref"] = snapshot_ref
        private = {"schema": "hpc-forest-matrix15-private-first-batch-review-v1", "verified": True,
                   **identity, "observed_at": observed_at, "authorization_sha256": input_value["authorization"]["sha256"],
                   "first_start_receipt_sha256": first_ref["sha256"], "paused_snapshot_sha256": snapshot_ref["sha256"],
                   "source_zip_sha256": ZIP_SHA, "source_runtime_manifest_sha256": RUNTIME_SHA,
                   "received_inventory": evidence.inventory, "external_program_copies": evidence.external_program_copies, "private_cache_root": input_value["cache_root"],
                   "policy_ref": input_value["policy_ref"], "private_cache_binding": local_ref(Path(input_value["cache_root"]) / "CELL-BINDING.json"),
                   **calls, "command_stream_review": stream_result,
                   "current_reference_command_stream_review": origin_review,
                   "original_evaluation_outcome": outcome, "original_search_deadline": snapshot["existing_search_deadline"],
                   "original_authorization_expiry": authorization["expires_at"], "candidate_negative_preserved": outcome["status"] != "valid",
                   "no_replay": True, "new_model_or_budget_authorized": False,
                   "release_installed": False, "independent_performance_audit_verified": False}
        evidence.recheck()
        for files in input_value["private_nonces"].values():
            for private_ref in files.values():
                checked_local(private_ref)
        checked_local(input_value["policy_ref"])
        checked_local(private["private_cache_binding"])
        cache = Path(input_value["cache_root"])
        need({p.name for p in cache.iterdir() if p.is_dir() and NONCE.fullmatch(p.name)} == set(input_value["private_nonces"])
             and not (cache / "cli-technical-hold.json").exists(), "Private claims/technical state changed during audit")
        need(clock() < snapshot["existing_search_deadline"], "Original release deadline expired during audit")
        return private, identity, first_ref, snapshot, first, authorization, evidence, (native, batch)


def write_exclusive(path, value):
    raw = encoded(value)
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(Path(path)), "sha256": sha(raw), "bytes": len(raw)}


def run(input_path, checksum, *, produce=False):
    path = ordinary(input_path)
    need(sha(path.read_bytes()) == checksum and HASH.fullmatch(checksum), "Sealed input changed")
    value = parse(path.read_bytes())
    output = Path(value["output_directory"])
    need(output.is_absolute() and ".." not in output.parts and not output.exists(), "Fresh absent absolute output directory required")
    need(output.parent.is_dir() and not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
         for p in (output.parent, *output.parent.parents)), "Ordinary output parent required")
    output.mkdir(exist_ok=False)
    if not produce:
        return write_exclusive(output / "PREPARATION.json", {"schema": "hpc-forest-matrix15-first-batch-audit-prepared-v1",
            "verified": False, "evidence_origin": value.get("evidence_origin"), "input": local_ref(path),
            "source_zip_sha256": ZIP_SHA, "source_runtime_manifest_sha256": RUNTIME_SHA,
            "production_requested": False, "release_installed": False, "native_model_calls": 0})
    try:
        private, identity, first_ref, snapshot, first, auth, evidence, modules = audit(value)
        private_ref = write_exclusive(output / "AUDIT-PRIVE.json", private)
        projection = {"schema": "hpc-forest-matrix15-private-cli-audit-digest-projection-v1", "verified": True, **identity,
            "first_start_receipt_sha256": first_ref["sha256"], "paused_snapshot_sha256": snapshot["self_ref"]["sha256"],
            "call_bindings": private["call_bindings"], "all_private_raws_received_and_hashed": True,
            "argv_matches_projections_and_local_policy": True, "cli_diagnostics_clean": True,
            "raw_skill_paths_exported": False, "private_review_receipt_sha256": private_ref["sha256"]}
        projected_ref = write_exclusive(output / "audit-cli-prive-digest.json", projection)
        arm_projection_ref = {"path": snapshot["self_ref"]["path"].rsplit("/", 1)[0] + "/audit-cli-prive-digest.json",
                              "sha256": projected_ref["sha256"]}
        # Explicit new proposal mapping, not a received/equivalent-path claim.
        evidence.add(arm_projection_ref, Path(projected_ref["path"]))
        release = {"schema": "hpc-forest-matrix15-first-batch-release-v1", "verified": True, **identity,
            "paused_snapshot": snapshot["self_ref"], "first_start_receipt": first_ref,
            "evaluation_snapshot": snapshot["evaluation_snapshot"], "private_cli_audit": arm_projection_ref,
            "no_replay": True, "new_model_or_budget_authorized": False}
        native, batch = modules
        with explicit_resolver(native, batch, evidence):
            need(batch.validate_first_batch_release(release, snapshot, first, auth) == projection,
                 "Source127 release validator returned another audit")
        evidence.recheck()
        need(sha(path.read_bytes()) == checksum, "Sealed input changed during audit")
        need(time.time() < min(snapshot["existing_search_deadline"], auth["expires_at"]),
             "Original deadline expired before writing proposed release")
        release_ref = write_exclusive(output / "autorisation-apres-premier-batch.PROPOSITION.json", release)
        return write_exclusive(output / "RECU-PROPOSITION.json", {"schema": "hpc-forest-matrix15-first-batch-proposal-receipt-v1",
            "verified": True, **identity, "input": local_ref(path), "private_audit": private_ref,
            "projection": projected_ref, "proposed_release": release_ref,
            "source127_validate_first_batch_release_passed": True, "release_installed": False,
            "upload_performed": False, "native_model_calls": 0, "no_replay": True,
            "new_model_or_budget_authorized": False, "existing_search_deadline": snapshot["existing_search_deadline"]})
    except Exception as exc:
        write_exclusive(output / "REFUS.json", {"schema": "hpc-forest-matrix15-first-batch-audit-refusal-v1",
            "verified": False, "reason": type(exc).__name__ + ": " + str(exc), "release_installed": False,
            "native_model_calls": 0, "new_model_or_budget_authorized": False, "preserved_for_review": True})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--produce-for-root-review", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.input, args.input_sha256, produce=args.produce_for_root_review)
    print(json.dumps({"receipt": result["path"], "sha256": result["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
