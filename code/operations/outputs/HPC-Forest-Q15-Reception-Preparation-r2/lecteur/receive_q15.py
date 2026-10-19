"""Cold baseline-only Q15 reader. Received Python, shell, Git and DB code is never run.

Production CLI accepts only pinned local transport evidence. NEUTRAL fixture mode
is a Python test API and always emits verified=false, including per-subject refs.
This reader cannot produce native matrix15 admission or independent performance.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sqlite3
import stat
import statistics
import tarfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCOPE = "hpc-forest-matrix15-baseline-qualification-r1"
INPUT_SCHEMA = "hpc-forest-Q15-baseline-cold-reception-input-v1"
SUBJECTS = ("2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
            "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
            "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci")
SHA = re.compile(r"[0-9a-f]{64}\Z")
GIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_ARCHIVE = 128 * 1024**2
MAX_MEMBER = 32 * 1024**2
MAX_TOTAL = 512 * 1024**2
MAX_MEMBERS = 20000
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
REF_NAMES = ("source_preparation", "source_archive", "source_plan", "source_manifest", "output_archive",
             "archive_announcement", "archive_transfer", "announcement_transfer", "status", "efficiency")
INPUT_KEYS = {"schema", "evidence_origin", "job_id", "remote_output_root", "remote_package_root",
              "maximum_seconds", "package_directory", "reception_directory", *REF_NAMES}
CONTEXT_FIELDS = {"schema", "mode", "never_model_input", "operator_binding", "protocol_id", "operation",
                  "experiment_id", "epoch", "commit", "tree_hash", "phase", "argv", "worktree", "binary_path",
                  "environment_overrides", "source_before", "binary_before", "argument_files_before",
                  "stdin_layout", "inherited_environment_captured"}
EXEC_FIELDS = CONTEXT_FIELDS | {"verified", "context", "source_after", "binary_after", "argument_files_after",
                "returncode", "timed_out", "measured_seconds", "original_process_result", "hashing_outside_measured_interval",
                "execution_semantics_changed", "streams", "case_execution_records", "individual_case_provenance_verified",
                "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified"}
OUTCOME_FIELDS = {"status", "commit", "tree_hash", "binary_sha256", "correct", "times", "mean_seconds", "score", "reason", "logs", "cache_key"}
FUTURE_QUALIFICATION_FIELDS = ("scope_id", "subject_id", "source_zip_sha256", "plan_sha256", "preparation_manifest_sha256",
    "r1_contract_sha256", "schema", "verified", "observation_mode", "allocation", "native_model_calls",
    "r1_paired_contract_verified", "execution_semantics_changed", "independent_raw_stdout_per_candidate_verified",
    "independent_performance_audit_verified", "prepared_contract", "prepared_root", "prepared_files", "evidence_refs")


class Refusal(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Refusal(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def data(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def parse_json(raw):
    need(isinstance(raw, bytes) and len(raw) <= MAX_MEMBER, "Bounded JSON bytes required")
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, "Duplicate JSON key")
            out[key] = value
        return out
    def constant(_value):
        raise Refusal("Nonfinite JSON value")
    def finite_float(value):
        number = float(value)
        need(math.isfinite(number), "Overflowed/nonfinite JSON number")
        return number
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal("Malformed JSON") from exc
    need(type(result) is dict, "JSON object required")
    return result


def reject_simulated(value):
    """Explicit fixture/preparation markers cannot become received production proof."""
    if type(value) is dict:
        for key, item in value.items():
            need(key not in {"NEUTRAL", "synthetic", "prepared", "neutral_fixture"} or item is False or item is None,
                 "Prepared/synthetic/NEUTRAL markers cannot be promoted")
            reject_simulated(item)
    elif type(value) is list:
        for item in value:
            reject_simulated(item)


def relative(value):
    need(type(value) is str and 0 < len(value) <= 4096 and "\\" not in value and ":" not in value
         and not any(ord(c) < 32 for c in value), "Unsafe relative path")
    path = PurePosixPath(value)
    need(not path.is_absolute() and path.as_posix() == value and all(p not in {".", "..", ""} for p in path.parts), "Noncanonical relative path")
    need(all(not p.endswith((".", " ")) and p.split(".", 1)[0].upper() not in RESERVED for p in path.parts), "Unsafe Windows path")
    return path


def remote(value):
    need(type(value) is str and value.startswith("/") and "\\" not in value and ":" not in value
         and not any(ord(c) < 32 for c in value), "Canonical absolute remote root required")
    path = PurePosixPath(value)
    need(path.as_posix() == value and ".." not in path.parts and value != "/", "Noncanonical remote root")
    return path


def regular_path(value):
    path = Path(value)
    need(path.is_absolute() and not path.is_symlink() and all(not p.is_symlink() for p in path.parents), "Physical absolute local path required")
    need(path.is_file() and stat.S_ISREG(path.stat().st_mode), "Regular local file required")
    return path


def read_ref(ref):
    need(type(ref) is dict and set(ref) == {"path", "sha256", "bytes"} and type(ref["sha256"]) is str
         and SHA.fullmatch(ref["sha256"]) and type(ref["bytes"]) is int and ref["bytes"] >= 0, "Closed file reference required")
    path = regular_path(ref["path"])
    need(path.stat().st_size == ref["bytes"] and ref["bytes"] <= MAX_TOTAL, "Local reference size differs")
    raw = path.read_bytes()
    need(digest(raw) == ref["sha256"], "Local reference SHA differs")
    return path, raw


def safe_tar(raw, prefix=None):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE, "Compressed tar bound exceeded")
    if prefix is not None:
        need(relative(prefix).parts == (prefix,), "One exact tar root required")
    files, folded, parents, total = {}, set(), {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive:
                need(member.type in {tarfile.REGTYPE, tarfile.AREGTYPE} and not member.sparse, "Regular non-sparse tar member required")
                need(not archive.pax_headers, "Global PAX metadata refused")
                for key, value in member.pax_headers.items():
                    if key == "path":
                        need(value == member.name, "PAX path override differs")
                    elif key in {"mtime", "atime", "ctime"}:
                        try:
                            need(math.isfinite(float(value)), "Nonfinite PAX time")
                        except (TypeError, ValueError, OverflowError) as exc:
                            raise Refusal("Invalid PAX time") from exc
                    else:
                        raise Refusal("Unsafe PAX metadata")
                path = relative(member.name)
                if prefix is not None:
                    need(path.parts[0] == prefix and len(path.parts) > 1, "Unexpected tar root")
                    name = path.relative_to(prefix).as_posix()
                else:
                    name = path.as_posix()
                relative(name)
                lower = name.casefold()
                need(lower not in folded and lower not in parents, "Duplicate/case-colliding tar member")
                for parent in PurePosixPath(name).parents:
                    if str(parent) == ".":
                        continue
                    p = str(parent)
                    need(p.casefold() not in folded and parents.get(p.casefold(), p) == p, "File-parent/directory case collision")
                    parents[p.casefold()] = p
                folded.add(lower)
                need(len(files) < MAX_MEMBERS and 0 <= member.size <= MAX_MEMBER, "Tar file/member limit exceeded")
                total += member.size
                need(total <= MAX_TOTAL, "Tar expanded-size limit exceeded")
                stream = archive.extractfile(member)
                need(stream is not None, "Tar member is unreadable")
                content = stream.read(MAX_MEMBER + 1)
                need(len(content) == member.size, "Tar member truncated or oversized")
                files[name] = content
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise Refusal("Malformed tar archive") from exc
    need(bool(files), "Empty archive refused")
    return files


def structured(wrapper):
    need(type(wrapper) is dict and wrapper.get("isError") is False and type(wrapper.get("structuredContent")) is dict, "Raw successful MCP wrapper required")
    value = wrapper["structuredContent"]
    need(value.get("ok") is True and not value.get("isError") and not any(value.get(k) or wrapper.get(k) for k in ["error", "errors"]), "MCP operation did not succeed")
    return value


def validate_transfer(wrapper, remote_path, local_path, raw):
    value = structured(wrapper)
    remote(remote_path)
    need(value.get("verifie") is True and value.get("downloaded") == remote_path and value.get("to") == str(local_path), "Transfer identity differs")
    need(type(value.get("bytes")) is int and value["bytes"] == len(raw), "Transfer size differs")
    need(all(value.get(k) == digest(raw) for k in ["remote_sha256", "empreinte_locale", "empreinte_distante"]), "Transfer remote/local SHA differs")
    return value


def validate_scheduler(status, efficiency, job_id):
    need(type(job_id) is str and re.fullmatch(r"[1-9][0-9]*", job_id), "Concrete positive Slurm job required")
    status, efficiency = structured(status), structured(efficiency)
    need(all(v.get("job_id") == job_id and v.get("state") == "COMPLETED" and v.get("exit_code") == "0:0" for v in [status, efficiency]), "Successful terminal job required")
    need(all(status.get(k) is True for k in ["finished", "scheduler_completed", "scheduler_success_observed"]) and efficiency.get("found") is True, "Successful scheduler observation required")
    observation = status.get("observation", {})
    need(type(observation) is dict, "Slurm observation must be an object")
    need(observation.get("source") == "slurm" and observation.get("current_state_observed") is True
         and type(observation.get("observed_at")) in {int, float} and math.isfinite(observation["observed_at"]) and observation["observed_at"] > 0, "Actual Slurm status observation required")
    need(type(efficiency.get("alloc_cpus")) is int and efficiency["alloc_cpus"] == 4
         and type(efficiency.get("alloc_gpus")) is int and efficiency["alloc_gpus"] == 0
         and type(efficiency.get("req_mem_mb")) in {int, float} and efficiency["req_mem_mb"] == 16384, "Scheduler resource allocation differs")


def inventory(folder):
    result = {}
    need(folder.is_dir() and not folder.is_symlink(), "Physical source directory required")
    for path in sorted(folder.rglob("*")):
        need(not path.is_symlink(), "Linked local source/restoration member refused")
        if path.is_file():
            need(stat.S_ISREG(path.stat().st_mode), "Nonregular local inventory member")
            result[path.relative_to(folder).as_posix()] = digest(path.read_bytes())
    return result


def file_ref(path):
    path = regular_path(path)
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def validate_source(config, snapshots):
    package = Path(config["package_directory"])
    need(package.is_absolute() and package.resolve(strict=True) == package and not package.is_symlink(), "Canonical source package directory required")
    prep = parse_json(snapshots["source_preparation"])
    need(prep.get("schema") == "hpc-forest-Q15-local-source-preparation-v1" and prep.get("scope_id") == SCOPE
         and prep.get("archive", {}).get("sha256") == config["source_archive"]["sha256"]
         and prep.get("plan", {}).get("sha256") == config["source_plan"]["sha256"]
         and prep.get("package_manifest", {}).get("sha256") == config["source_manifest"]["sha256"], "Input-sealed Q15 preparation differs")
    need(prep.get("asset_counts") == {"source": 46, "validation": 150, "total": 196}
         and prep.get("configurations") == 15 and prep.get("qualification_ready") is False
         and prep.get("native_authorization") is False and prep.get("native_model_calls") == 0,
         "Source preparation is baseline-only prepared material, never an executed qualification")
    need(all(prep.get(field, {}).get("path") == config[key]["path"] for field, key in
         [("archive", "source_archive"), ("plan", "source_plan"), ("package_manifest", "source_manifest")]),
         "Prepared source references point to different local files")
    need(Path(config["source_plan"]["path"]) == package / "PLAN-Q15.json"
         and Path(config["source_manifest"]["path"]) == package / "PACKAGE-MANIFEST.json", "Source package references point elsewhere")
    manifest = parse_json(snapshots["source_manifest"])
    need(set(manifest) == {"schema", "files"} and manifest["schema"] == "hpc-forest-Q15-package-files-v1", "Unexpected package manifest schema")
    source_files = inventory(package)
    need(source_files == {**manifest["files"], "PACKAGE-MANIFEST.json": config["source_manifest"]["sha256"]}
         and len(source_files) == prep.get("package_members"), "Source package inventory differs")
    need({k: digest(v) for k, v in safe_tar(snapshots["source_archive"]).items()} == source_files, "Source tar/package inventory differs")
    plan = parse_json(snapshots["source_plan"])
    need(plan.get("schema") == "hpc-forest-matrix15-baseline-qualification-plan-v1" and plan.get("scope_id") == SCOPE
         and plan.get("subject_order") == list(SUBJECTS) and set(plan.get("subjects", {})) == set(SUBJECTS), "Closed fifteen-subject plan required")
    source_assets = validation_assets = 0
    for subject in SUBJECTS:
        row = plan["subjects"][subject]
        expected_paths = {"config": "configs/" + subject + ".json", "source": "prepared/" + subject + "/source",
                          "validation": "prepared/" + subject + "/validation", "statement": "statements/" + subject[:4] + ".txt"}
        for field, expected_path in expected_paths.items():
            name = relative(row[field]).as_posix()
            need(name == expected_path, "Q subject path differs from its confined source package layout")
            local = package.joinpath(*PurePosixPath(name).parts)
            need(local.resolve(strict=True).is_relative_to(package), "Q subject path escapes source package")
            if field in {"config", "statement"}:
                need(name in source_files, "Q subject file is absent from sealed source inventory")
        source_count = len(inventory(package / row["source"]))
        validation_count = len(inventory(package / row["validation"]))
        need(source_count == row["source_files"] and validation_count == row["validation_files"], "Q official asset counts differ")
        source_assets += source_count
        validation_assets += validation_count
    need(source_assets == 46 and validation_assets == 150, "Exactly 196 original source/validation assets required")
    need(plan.get("native_authorization") is False and all(type(plan.get(k)) is int and plan[k] == 0 for k in
         ["native_model_calls", "Controller_instances", "Mother_instances", "native_workers_started"]), "Q source must remain zero-model")
    binding = plan["source_bindings"]
    need(set(binding) == {"schema", "parent_runtime_manifest_sha256", "q_runtime_manifest_sha256", "single_pilot_protocol_sha256"}
         and binding["schema"] == "hpc-forest-Q15-single-pilot-source-binding-v1"
         and binding["parent_runtime_manifest_sha256"] == digest((package / "ORIGINAL-RUNTIME-MANIFEST.json").read_bytes())
         and binding["q_runtime_manifest_sha256"] == digest((package / "RUNTIME-Q-MANIFEST.json").read_bytes()), "Source runtime binding differs")
    need(inventory(package / "project-q") == parse_json((package / "RUNTIME-Q-MANIFEST.json").read_bytes()), "Q runtime inventory differs")
    parent_runtime = parse_json((package / "ORIGINAL-RUNTIME-MANIFEST.json").read_bytes())
    q_runtime = parse_json((package / "RUNTIME-Q-MANIFEST.json").read_bytes())
    changed = {k for k in set(parent_runtime) | set(q_runtime) if parent_runtime.get(k) != q_runtime.get(k)}
    need(changed == {"src/hpc_forest/matrix15_provenance.py", "src/hpc_forest/matrix15_qualification.py"},
         "Q derivative changed files outside its separate observer/qualification module")
    delta = parse_json((package / "QUALIFICATION-SOURCE-DELTA.json").read_bytes())
    need(delta.get("schema") == "hpc-forest-Q15-source-derivative-v1" and delta.get("native_authorization") is False
         and delta.get("scientific_checker_changes") == 0
         and delta.get("parent_observer_sha256") == parent_runtime["src/hpc_forest/matrix15_provenance.py"]
         and delta.get("Q_observer_sha256") == q_runtime["src/hpc_forest/matrix15_provenance.py"], "Q source delta declaration differs from source manifests")
    return package, plan, source_files


class Material:
    """Resolve only caller-pinned remote output/package roots, never arbitrary paths."""
    def __init__(self, files, remote_output, package, remote_package):
        self.files = files
        self.output = remote(remote_output)
        self.package = package
        self.remote_package = remote(remote_package)
        self.external_tools = set()
        self.referenced_output = set()

    def get(self, value):
        path = remote(value)
        if path.is_relative_to(self.output):
            name = path.relative_to(self.output).as_posix()
            need(name in self.files, "Referenced output file absent")
            self.referenced_output.add(name)
            return self.files[name]
        if path.is_relative_to(self.remote_package):
            name = path.relative_to(self.remote_package).as_posix()
            relative(name)
            return (self.package / name).read_bytes()
        raise Refusal("Reference escapes pinned remote roots")

    def ref(self, value):
        need(type(value) is dict and set(value) == {"path", "sha256", "bytes"} and type(value["bytes"]) is int
             and value["bytes"] >= 0 and type(value["sha256"]) is str and SHA.fullmatch(value["sha256"]), "Closed command file reference required")
        raw = self.get(value["path"])
        need(len(raw) == value["bytes"] and digest(raw) == value["sha256"], "Referenced command bytes differ")
        return raw


def close(a, b):
    need(type(a) in {int, float} and type(b) in {int, float} and math.isfinite(a) and math.isfinite(b)
         and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15), "Numeric observation differs")


def git_baseline(files, subject):
    prefix = subject + "/repo/"
    def loose(oid):
        need(type(oid) is str and GIT.fullmatch(oid), "Expected SHA1 Git object")
        name = prefix + ".git/objects/" + oid[:2] + "/" + oid[2:]
        need(name in files, "Missing loose Git object; no Git execution fallback")
        dec = zlib.decompressobj()
        raw = dec.decompress(files[name], MAX_MEMBER + 1)
        need(dec.eof and len(raw) <= MAX_MEMBER and not dec.unused_data, "Bounded complete Git object required")
        need(hashlib.sha1(raw).hexdigest() == oid, "Git object SHA1 differs")
        header, body = raw.split(b"\0", 1)
        kind, size = header.split(b" ")
        need(int(size) == len(body), "Git object length differs")
        return kind, body
    head = files[prefix + ".git/HEAD"].decode("ascii").strip()
    need(head.startswith("ref: refs/heads/"), "Expected new baseline branch HEAD")
    ref = relative(head[5:]).as_posix()
    commit = files[prefix + ".git/" + ref].decode("ascii").strip()
    kind, body = loose(commit)
    need(kind == b"commit" and body.startswith(b"tree "), "Expected Git baseline commit")
    tree = body.splitlines()[0][5:].decode("ascii")
    blobs = {}
    def walk(oid, directory="", depth=0):
        need(depth < 32, "Git tree nesting bound exceeded")
        kind, body = loose(oid)
        need(kind == b"tree", "Expected Git tree object")
        while body:
            meta, body = body.split(b"\0", 1)
            mode, name = meta.split(b" ", 1)
            name = name.decode("utf-8")
            need(relative(name).parts == (name,), "Unsafe Git entry name")
            oid, body = body[:20].hex(), body[20:]
            item = directory + name
            if mode == b"40000":
                walk(oid, item + "/", depth + 1)
            else:
                need(mode in {b"100644", b"100755"}, "Git symlink/submodule mode refused")
                kind, value = loose(oid)
                need(kind == b"blob" and item not in blobs, "Expected unique Git blob")
                blobs[item] = digest(value)
    walk(tree)
    actual = {k[len(prefix):]: digest(v) for k, v in files.items() if k.startswith(prefix) and not k.startswith(prefix + ".git/")}
    need(actual == blobs, "Restored baseline worktree differs from Git tree")
    return commit, tree, blobs


def expected_policy(subject, config, plan):
    return {"mode": "command-stream-v1", "qualification_binding": {
        "schema": "hpc-forest-matrix15-qualification-binding-v1", "scope_id": SCOPE,
        "subject_id": subject, "job_id": config["job_id"], "remote_root": config["remote_output_root"], "seed": 23,
        "prepared_manifest_sha256": plan["preparation_sha256"], "r1_contract_sha256": plan["subjects"][subject]["r1_contract_sha256"],
        "native_authorization": False}, "source_runtime_sha256": plan["source_bindings"]["q_runtime_manifest_sha256"],
        "subject_contract_sha256": plan["subjects"][subject]["r1_contract_sha256"], "qualification_protocol_sha256": config["source_plan"]["sha256"]}


def command_log_member(name):
    """Only the subject's command log root; Git reflogs remain Git evidence."""
    parts = relative(name).parts
    return len(parts) >= 2 and parts[0] in SUBJECTS and parts[1] == "logs"


def command_streams(material, outcome, summaries, policy, protocol, subject, phase, settings):
    stem = str(material.output / subject)
    names = ["build.log", "correctness.log"]
    if phase == "confirmation":
        names += [f"warmup-{i}.log" for i in range(settings["protocol"]["warmups"])] + [f"sample-{i}.log" for i in range(5)]
    logs = [stem + "/logs/e1/baseline-e1/" + phase + "/attempt-001/" + n for n in names]
    need(outcome["logs"] == logs and type(summaries) is list and len(summaries) == len(logs), "Exact ordered baseline log inventory required")
    verified_refs = []
    for log, summary in zip(logs, summaries):
        side = log + ".command-stream.json"
        need(type(summary) is dict and set(summary) == {"path", "sha256", "bytes", "mode", "operation", "verified", "individual_case_provenance_verified", "independent_performance_audit_verified"}, "Closed command summary required")
        proof_ref = {k: summary[k] for k in ["path", "sha256", "bytes"]}
        need(proof_ref["path"] == side, "Command summary path differs")
        proof = parse_json(material.ref(proof_ref))
        if not material.neutral_fixture:
            reject_simulated(proof)
        need(set(proof) == EXEC_FIELDS and proof["schema"] == "hpc-forest-matrix15-qualification-command-execution-v1", "Qualification execution schema differs")
        need(proof["context"]["path"] == log + ".command-context.json", "Command context path differs")
        context = parse_json(material.ref(proof["context"]))
        if not material.neutral_fixture:
            reject_simulated(context)
        need(set(context) == CONTEXT_FIELDS and context["schema"] == "hpc-forest-matrix15-qualification-command-context-v1", "Qualification context schema differs")
        need(all(proof[k] == v for k, v in context.items() if k != "schema"), "Execution/context identity differs")
        operation = "build" if log.endswith("/build.log") else "check" if log.endswith("/correctness.log") else "benchmark"
        need(summary == {**proof_ref, "mode": "command-stream-v1", "operation": operation, "verified": True,
                         "individual_case_provenance_verified": False, "independent_performance_audit_verified": False}, "Command summary flags differ")
        need(context["mode"] == "command-stream-v1" and context["never_model_input"] is True and context["operator_binding"] == policy
             and context["protocol_id"] == protocol and context["experiment_id"] == "baseline-e1" and type(context["epoch"]) is int
             and context["epoch"] == 1 and context["phase"] == phase and context["operation"] == operation
             and context["commit"] == outcome["commit"] and context["tree_hash"] == outcome["tree_hash"], "Baseline execution identity differs")
        need(proof["verified"] is True and proof["source_after"] == context["source_before"] == {
            "commit": outcome["commit"], "tree_hash": outcome["tree_hash"], "clean": True}, "Baseline source snapshot differs")
        need(proof["hashing_outside_measured_interval"] is True and proof["execution_semantics_changed"] is False
             and proof["case_execution_records"] == [] and all(proof[k] is False for k in ["individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified"]), "Command observation level overclaimed")
        need(context["stdin_layout"] == "original_run_process_DEVNULL_unchanged" and context["inherited_environment_captured"] is False, "Command input/environment layout differs")
        worktree = stem + "/repo"
        build = stem + "/builds/e1/baseline-e1/" + phase + "/attempt-001"
        binary = build + "/solution"
        variables = {"python": settings["identity_python_executable"], "trusted": stem + "/trusted", "worktree": worktree,
                     "build": build, "binary": binary, "phase": phase}
        argv = [arg.format_map(variables) for arg in settings["protocol"][operation]]
        need(context["worktree"] == worktree and context["binary_path"] == binary and context["argv"] == argv
             and context["environment_overrides"] == settings["protocol"]["environment"], "Unchanged R1 command template differs")
        before, after = context["argument_files_before"], proof["argument_files_after"]
        need(type(before) is list and type(after) is list, "Argument inventories required")
        expected_argument_indices = {0}
        for i, argument in enumerate(argv[1:], 1):
            path = PurePosixPath(argument) if argument.startswith("/") else PurePosixPath(worktree) / argument
            if path.is_relative_to(material.output) and path.relative_to(material.output).as_posix() in material.files:
                expected_argument_indices.add(i)
            elif path.is_relative_to(material.remote_package):
                name = relative(path.relative_to(material.remote_package).as_posix())
                if material.package.joinpath(*name.parts).is_file():
                    expected_argument_indices.add(i)
        for items in [before, after]:
            seen = set()
            for item in items:
                need(type(item) is dict and set(item) == {"argument_index", "argument", "path", "sha256", "bytes"}
                     and type(item["argument_index"]) is int and 0 <= item["argument_index"] < len(argv), "Invalid argument file reference")
                i = item["argument_index"]
                expected = str(PurePosixPath(argv[i]) if argv[i].startswith("/") else PurePosixPath(worktree) / argv[i])
                need(i not in seen and item["argument"] == argv[i] and item["path"] == expected
                     and type(item["bytes"]) is int and item["bytes"] >= 0 and SHA.fullmatch(item["sha256"]), "Argument identity differs")
                seen.add(i)
                ref = {k: item[k] for k in ["path", "sha256", "bytes"]}
                if PurePosixPath(expected).is_relative_to(material.output) or PurePosixPath(expected).is_relative_to(material.remote_package):
                    material.ref(ref)
                else:
                    need(i == 0 and expected == argv[0], "External non-executable argument reference refused")
                    material.external_tools.add((expected, item["sha256"], item["bytes"]))
            need(seen == expected_argument_indices, "Incomplete command argument file observation")
        need([v for v in before if v["path"] != binary] == [v for v in after if v["path"] != binary], "Command input bytes changed")
        need(proof["binary_after"] is not None, "Compiled baseline binary reference missing")
        binary_raw = material.ref(proof["binary_after"])
        need(len(binary_raw) >= 64 and binary_raw[:6] == b"\x7fELF\x02\x01" and int.from_bytes(binary_raw[18:20], "little") == 183,
             "Baseline executable is not received little-endian ELF64 AArch64")
        need(proof["binary_after"]["path"] == binary and proof["binary_after"]["sha256"] == outcome["binary_sha256"], "Outcome binary differs")
        if operation != "build":
            need(context["binary_before"] == proof["binary_after"], "Baseline binary changed across command")
            material.ref(context["binary_before"])
        else:
            need(context["binary_before"] is None, "New baseline build reused a prior binary")
        streams = proof["streams"]
        need(set(streams) == {"combined_stdout_stderr", "separate_stdout", "separate_stderr", "layout"}
             and streams["separate_stdout"] is None and streams["separate_stderr"] is None
             and streams["layout"] == "original_run_process_combined_unchanged" and streams["combined_stdout_stderr"]["path"] == log, "Original combined stream layout differs")
        raw_stream = material.ref(streams["combined_stdout_stderr"])
        need(proof["original_process_result"]["path"] == log + ".json", "Original process receipt path differs")
        process = parse_json(material.ref(proof["original_process_result"]))
        if not material.neutral_fixture:
            reject_simulated(process)
        need(type(proof["returncode"]) is int and proof["returncode"] == 0 and proof["timed_out"] is False
             and type(proof["measured_seconds"]) in {int, float} and math.isfinite(proof["measured_seconds"]) and proof["measured_seconds"] >= 0, "Baseline command failed/timed out")
        need(process == {"argv": argv, "returncode": 0, "seconds": proof["measured_seconds"], "timed_out": False, "log": log}, "Original process outcome differs")
        if operation == "check":
            check = parse_json(raw_stream)
            if not material.neutral_fixture:
                reject_simulated(check)
            need(check.get("correct") is True and type(check.get("cases")) is int and check["cases"] > 0, "Baseline checker output failed")
        if "/sample-" in log:
            i = int(PurePosixPath(log).stem.split("-")[-1])
            close(outcome["times"][i], proof["measured_seconds"])
        verified_refs.extend([proof_ref, proof["context"], proof["original_process_result"], streams["combined_stdout_stderr"]])
    return verified_refs


def baseline_db(path, subject, result, material, plan, commit, tree):
    # Immutable URI prevents WAL creation, schema changes, triggers, or recovery.
    before = digest(path.read_bytes())
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        need(connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "Closed SQLite snapshot is inconsistent")
        definitions = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        need(all(r["type"] in {"table", "index"} and (r["type"] != "table" or not (r["sql"] or "").upper().startswith("CREATE VIRTUAL")) for r in definitions), "SQLite views/triggers/virtual tables refused")
        expected_tables = {"metadata", "epochs", "trees", "slots", "trials", "evaluations", "interactions", "events", "documents"}
        need({r["name"] for r in definitions if r["type"] == "table"} == expected_tables, "SQLite table inventory differs")
        metadata = {}
        for row in connection.execute("SELECT key,value FROM metadata"):
            need(row["key"] not in metadata, "Duplicate SQLite metadata key")
            # Metadata values may be scalars; wrapping preserves duplicate/nonfinite checks.
            metadata[row["key"]] = parse_json(b'{"value":' + row["value"].encode() + b'}')["value"]
        need(set(metadata) == {"config", "manifest", "identity", "protocol_id", "current_epoch", "status", "started", "deadline", "qualification_only"},
             "Unexpected Q metadata, including any mother/model plan")
        if not material.neutral_fixture:
            reject_simulated(metadata)
        settings = metadata["config"]
        identity = metadata["identity"]
        trusted = {k[len(subject + "/trusted/"):]: digest(v) for k, v in material.files.items() if k.startswith(subject + "/trusted/")}
        need(metadata["manifest"] == trusted, "Trusted manifest differs from received bytes")
        need(parse_json(material.files[subject + "/trusted/config.json"]) == settings, "Protected config differs from DB")
        need(metadata["protocol_id"] == result["protocol_id"] == digest(canonical({"protocol": settings["protocol"], "manifest": trusted, "target": identity})), "Baseline protocol identity differs")
        need(metadata.get("qualification_only") is True and metadata["current_epoch"] == 1 and identity.get("machine", "").lower() in {"aarch64", "arm64"}, "Baseline DB is not Q ARM epoch1")
        need(type(metadata["started"]) in {int, float} and type(metadata["deadline"]) in {int, float}
             and math.isfinite(metadata["started"]) and metadata["started"] > 0, "Shared Q deadline timestamps missing")
        close(metadata["deadline"] - metadata["started"], material.config["maximum_seconds"])
        original = parse_json((material.package / plan["subjects"][subject]["config"]).read_bytes())
        expected = dict(original)
        expected.update(codex={"transport": "codex-mailbox", "model": None},
            target_id="romeo:slurm-" + result["policy"]["qualification_binding"]["job_id"] + ":Q15-baseline-cpu4",
            compiler=settings["compiler"], execution_provenance=result["policy"])
        need(settings == expected and settings["seed"] == 23 and settings["backend"] == "codex" and settings["protocol"]["confirmation_repetitions"] == 5, "R1 config changed outside inactive deployment/Q fields")
        need(type(identity["python_executable"]) is str and remote(identity["python_executable"]), "Observed Python path missing")
        epochs = connection.execute("SELECT id,base_commit,protocol_id,baseline_id FROM epochs").fetchall()
        need(len(epochs) == 1 and dict(epochs[0]) == {"id": 1, "base_commit": commit, "protocol_id": result["protocol_id"], "baseline_id": None}, "Q epoch differs or Controller baseline was started")
        for table in ["trees", "trials", "interactions"]:
            need(connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0, "Q contains native trees/trials/integrations")
        events = list(connection.execute("SELECT kind,payload FROM events"))
        need(len(events) == 1 and events[0]["kind"] == "workspace_created", "Unexpected Q runtime events")
        event = parse_json(events[0]["payload"].encode())
        need(event == {"base_commit": commit, "protocol_id": result["protocol_id"]}, "Workspace creation binding differs")
        slots = list(connection.execute("SELECT phase,purpose,tokens_reserved,tokens_used,usage_known FROM slots"))
        need(len(slots) == 1 and slots[0]["phase"] == "confirmation" and slots[0]["purpose"] == "Q15 official baseline only; zero model tokens"
             and slots[0]["tokens_reserved"] == slots[0]["tokens_used"] == 0 and slots[0]["usage_known"] == 1, "Q slots contain nonzero/unknown/model usage")
        costs = {"slots": len(slots), "tokens_used": sum(r["tokens_used"] for r in slots), "tokens_reserved": sum(r["tokens_reserved"] for r in slots),
                 "unknown_usage_calls": sum(r["usage_known"] == 0 for r in slots), "bounded_usage_calls": sum(r["usage_known"] == 2 for r in slots),
                 "exact_tokens_used": sum(r["tokens_used"] for r in slots if r["usage_known"] == 1)}
        need(result["costs"] == costs, "Q cost receipt differs from SQLite slots")
        evaluations = list(connection.execute("SELECT experiment_id,epoch,phase,cache_key,payload FROM evaluations"))
        need(len(evaluations) == 2 and {r["phase"] for r in evaluations} == {"qualification_precheck", "confirmation"}, "Q evaluation inventory differs")
        for row in evaluations:
            key = "precheck" if row["phase"] == "qualification_precheck" else "confirmation"
            need(row["experiment_id"] == "baseline-e1" and type(row["epoch"]) is int and row["epoch"] == 1 and parse_json(row["payload"].encode()) == result[key], "DB/outcome record differs")
            need(row["cache_key"] == result[key]["cache_key"] == digest(canonical({"tree": tree, "protocol": result["protocol_id"], "epoch": 1})), "Baseline cache identity differs")
        settings["identity_python_executable"] = identity["python_executable"]
        settings["shared_started"] = metadata["started"]
        settings["shared_deadline"] = metadata["deadline"]
        return settings
    finally:
        connection.close()
        need(digest(path.read_bytes()) == before, "SQLite reader changed received bytes")


def validate_subject(subject, result, material, plan, restored):
    need(type(result) is dict and set(result) == {"baseline_qualified", "policy", "protocol_id", "precheck", "confirmation", "precheck_command_streams", "confirmation_command_streams", "costs", "r1_contract_sha256", "case_counts"}, "Closed Q subject record required")
    policy = expected_policy(subject, material.config, plan)
    need(result["baseline_qualified"] is True and result["policy"] == policy and result["r1_contract_sha256"] == plan["subjects"][subject]["r1_contract_sha256"]
         and result["case_counts"] == plan["subjects"][subject]["case_counts"] and SHA.fullmatch(result["protocol_id"]), "Q subject policy/contract differs")
    contract = material.files[subject + "/trusted/contract.json"]
    need(digest(contract) == result["r1_contract_sha256"], "Received R1 contract changed")
    row = plan["subjects"][subject]
    validation = inventory(material.package / row["validation"])
    trusted_names = {k[len(subject + "/trusted/"):] for k in material.files if k.startswith(subject + "/trusted/")}
    need(trusted_names == set(validation) | {"config.json", "result-schema.json"}, "Unexpected protected Q workspace file")
    need(all(material.files.get(subject + "/trusted/" + name) is not None and digest(material.files[subject + "/trusted/" + name]) == checksum for name, checksum in validation.items()), "Received validation bytes differ from R1 package")
    commit, tree, blobs = git_baseline(material.files, subject)
    need(blobs == inventory(material.package / row["source"]), "Baseline source differs from official source bytes")
    for key in ["precheck", "confirmation"]:
        outcome = result[key]
        need(type(outcome) is dict and set(outcome) == OUTCOME_FIELDS and outcome["correct"] is True
             and outcome["commit"] == commit and outcome["tree_hash"] == tree and SHA.fullmatch(outcome["binary_sha256"]), "Baseline outcome identity differs")
        if key == "precheck":
            need(outcome["status"] == "development_valid" and outcome["times"] == [] and outcome["mean_seconds"] is None and outcome["score"] is None, "Precheck must remain unmeasured development validation")
        else:
            need(outcome["status"] == "valid" and type(outcome["times"]) is list and len(outcome["times"]) == 5
                 and all(type(t) in {int, float} and math.isfinite(t) and t > 0 for t in outcome["times"]), "Five positive finite baseline times required")
            close(outcome["mean_seconds"], statistics.mean(outcome["times"]))
            close(outcome["score"], 0.5)
    settings = baseline_db(restored / subject / "registry.sqlite3", subject, result, material, plan, commit, tree)
    refs = command_streams(material, result["precheck"], result["precheck_command_streams"], policy, result["protocol_id"], subject, "search", settings)
    refs += command_streams(material, result["confirmation"], result["confirmation_command_streams"], policy, result["protocol_id"], subject, "confirmation", settings)
    return {"subject_id": subject, "r1_contract_sha256": result["r1_contract_sha256"], "protocol_id": result["protocol_id"],
            "policy": policy, "commit": commit, "tree_hash": tree, "binary_sha256": result["confirmation"]["binary_sha256"],
            "confirmation_seconds": result["confirmation"]["times"], "mean_seconds": result["confirmation"]["mean_seconds"],
            "sample_stdev_seconds": statistics.stdev(result["confirmation"]["times"]), "costs": result["costs"], "evidence_refs": refs,
            "shared_started": settings["shared_started"], "shared_deadline": settings["shared_deadline"]}


def allocation(value, job_id):
    need(type(value) is dict and set(value) == {"job_id", "nodes", "tasks", "cpus_per_task", "memory_mib", "gpus", "affinity_cpu_ids", "machine", "observed_utc"}, "Closed actual Q allocation required")
    need(value["job_id"] == job_id and value["machine"] in {"aarch64", "arm64"}, "Q allocation job/ARM identity differs")
    need(all(type(value[k]) is int and value[k] == v for k, v in {"nodes": 1, "tasks": 1, "cpus_per_task": 4, "memory_mib": 16384, "gpus": 0}.items()), "Q allocation resources differ")
    ids = value["affinity_cpu_ids"]
    need(type(ids) is list and len(ids) == len(set(ids)) == 4 and all(type(v) is int and v >= 0 for v in ids), "Q requires four effective CPUs")
    try:
        observed = datetime.fromisoformat(value["observed_utc"])
    except (ValueError, TypeError) as exc:
        raise Refusal("Allocation UTC timestamp malformed") from exc
    need(observed.tzinfo is not None and observed.utcoffset().total_seconds() == 0, "UTC allocation timestamp required")
    return observed.timestamp()


def receive(input_path, input_sha256, *, neutral_fixture=False):
    source_reader_before = file_ref(Path(__file__).resolve())
    input_path = regular_path(input_path)
    raw_input = input_path.read_bytes()
    need(digest(raw_input) == input_sha256, "Reception input SHA differs")
    initial_input_ref = {"path": str(input_path), "sha256": digest(raw_input), "bytes": len(raw_input)}
    config = parse_json(raw_input)
    need(set(config) == INPUT_KEYS and config["schema"] == INPUT_SCHEMA, "Closed Q15 reception input required")
    need(config["evidence_origin"] == ("NEUTRAL" if neutral_fixture else "received"), "Prepared/synthetic/NEUTRAL evidence cannot be promoted")
    need(type(config["maximum_seconds"]) is int and 60 <= config["maximum_seconds"] <= 7200, "Bounded shared Q duration required")
    output_remote, package_remote = remote(config["remote_output_root"]), remote(config["remote_package_root"])
    need(not output_remote.is_relative_to(package_remote) and not package_remote.is_relative_to(output_remote), "Disjoint remote package/output roots required")
    destination = Path(config["reception_directory"])
    need(destination.is_absolute() and not destination.exists() and destination.parent.resolve(strict=True) == destination.parent
         and all(not p.is_symlink() for p in destination.parents), "Fresh canonical reception directory required")
    snapshots, initial_refs = {}, {}
    for name in REF_NAMES:
        path, content = read_ref(config[name])
        need(not path.is_relative_to(destination), "Input inside output destination refused")
        snapshots[name], initial_refs[name] = content, config[name]
        if not neutral_fixture and name in {"archive_announcement", "archive_transfer", "announcement_transfer", "status", "efficiency"}:
            reject_simulated(parse_json(content))
    package, plan, source_before = validate_source(config, snapshots)
    need(not destination.is_relative_to(package) and not package.is_relative_to(destination), "Source/reception directory overlap refused")
    archive_path = regular_path(config["output_archive"]["path"])
    announcement_path = regular_path(config["archive_announcement"]["path"])
    announcement = parse_json(snapshots["archive_announcement"])
    need(set(announcement) == {"schema", "path", "sha256", "private_audit_only_never_model_context", "native_model_calls"}
         and announcement["schema"] == "hpc-forest-matrix15-Q-archive-v1"
         and announcement["path"] == str(output_remote) + ".tar.gz" and announcement["sha256"] == digest(snapshots["output_archive"])
         and announcement["private_audit_only_never_model_context"] is True and type(announcement["native_model_calls"]) is int and announcement["native_model_calls"] == 0, "Exact archive announcement differs")
    validate_transfer(parse_json(snapshots["archive_transfer"]), announcement["path"], archive_path, snapshots["output_archive"])
    validate_transfer(parse_json(snapshots["announcement_transfer"]), str(output_remote) + "-archive.json", announcement_path, snapshots["archive_announcement"])
    validate_scheduler(parse_json(snapshots["status"]), parse_json(snapshots["efficiency"]), config["job_id"])
    files = safe_tar(snapshots["output_archive"], output_remote.name)
    for name in files:
        parts = PurePosixPath(name).parts
        need((len(parts) == 1 and name in {"OUTPUT-MANIFEST.json", "RESULT-Q15.json", "INTENT-ONE-Q15.json"})
             or (len(parts) >= 2 and parts[0] in SUBJECTS and parts[1] in {"registry.sqlite3", "trusted", "repo", "logs", "builds"}),
             "Unexpected Q output activity/member")
    manifest = parse_json(files["OUTPUT-MANIFEST.json"])
    need(set(manifest) == {"schema", "files"} and manifest["schema"] == "hpc-forest-matrix15-Q-private-output-files-v1"
         and manifest["files"] == {k: digest(v) for k, v in files.items() if k != "OUTPUT-MANIFEST.json"}, "Output manifest must cover every other exact file")
    need(all(not n.endswith(("-wal", "-shm", "-journal", ".pyc")) and "__pycache__" not in PurePosixPath(n).parts for n in files), "Unclosed SQLite or Python cache evidence refused")
    result, intent = parse_json(files["RESULT-Q15.json"]), parse_json(files["INTENT-ONE-Q15.json"])
    if not neutral_fixture:
        reject_simulated(result)
        reject_simulated(intent)
    need(set(intent) == {"schema", "scope_id", "allocation", "plan", "maximum_seconds", "native_authorization", "native_model_calls", "attempt", "retry"},
         "Closed Q15 intent required")
    need(set(result) == {"schema", "scope_id", "allocation", "plan", "source_bindings", "qualification_complete", "qualified_subjects", "subjects",
                        "native_authorization", "native_model_calls", "Controller_instances", "Mother_instances", "native_workers_started",
                        "individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified",
                        "scientific_gain_claimed", "old_candidates_or_reference_binaries_imported", "elapsed_seconds"},
         "Closed successful Q15 result required; prepared/synthetic/extra claims refused")
    need(not any(result.get(k) for k in ["synthetic", "prepared", "neutral_fixture", "error", "error_type"]), "Prepared/synthetic/error result cannot qualify baselines")
    need(result.get("schema") == "hpc-forest-matrix15-baseline-qualification-result-v1" and result.get("scope_id") == SCOPE
         and result.get("source_bindings") == plan["source_bindings"] and result.get("qualification_complete") is True
         and result.get("qualified_subjects") == list(SUBJECTS) and set(result.get("subjects", {})) == set(SUBJECTS), "Complete ordered Q15 result required")
    allocation_observed = allocation(result["allocation"], config["job_id"])
    exclusive = datetime(2026, 10, 31, 23, tzinfo=timezone.utc).timestamp()
    need(allocation_observed + config["maximum_seconds"] + 120 + 10800 < exclusive, "Q allocation exceeds exclusive deadline/audit reserve")
    need(intent.get("schema") == "hpc-forest-matrix15-baseline-qualification-intent-v1" and intent.get("scope_id") == SCOPE
         and intent.get("allocation") == result["allocation"] and type(intent.get("attempt")) is int and intent["attempt"] == 1
         and intent.get("retry") is False and intent.get("maximum_seconds") == config["maximum_seconds"], "Unique no-retry Q15 intent differs")
    expected_plan_ref = {"path": str(package_remote / "PLAN-Q15.json"), "sha256": config["source_plan"]["sha256"]}
    need(intent.get("plan") == result.get("plan") == expected_plan_ref and intent.get("native_authorization") is False
         and type(intent.get("native_model_calls")) is int and intent["native_model_calls"] == 0, "Intent/result source plan or authorization differs")
    need(result.get("native_authorization") is False and all(type(result.get(k)) is int and result[k] == 0 for k in
         ["native_model_calls", "Controller_instances", "Mother_instances", "native_workers_started"]), "Q result contains native activity")
    need(all(result.get(k) is False for k in ["individual_case_provenance_verified", "independent_raw_stdout_per_candidate_verified", "independent_performance_audit_verified", "scientific_gain_claimed", "old_candidates_or_reference_binaries_imported"]), "Q baseline scope overclaimed")
    need(type(result.get("elapsed_seconds")) in {int, float} and math.isfinite(result["elapsed_seconds"]) and 0 <= result["elapsed_seconds"] <= config["maximum_seconds"] + 120, "Q elapsed duration exceeds bounded allocation")
    destination.mkdir(exist_ok=False)
    restored = destination / "restauration-neuve"
    restored.mkdir(exist_ok=False)
    try:
        for name, content in files.items():
            path = restored.joinpath(*relative(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(content)
        before = inventory(restored)
        material = Material(files, str(output_remote), package, str(package_remote))
        material.config = config
        material.neutral_fixture = neutral_fixture
        subjects = [validate_subject(s, result["subjects"][s], material, plan, restored) for s in SUBJECTS]
        need(len({(s["shared_started"], s["shared_deadline"]) for s in subjects}) == 1, "Fifteen subjects do not share one unrestarted Q deadline")
        need(all(name in material.referenced_output for name in files if command_log_member(name)), "Unreferenced/orphan command log or sidecar")
        after = inventory(restored)
        need(before == after and source_before == inventory(package), "Cold reading changed received or source bytes")
        for name in REF_NAMES:
            need(read_ref(config[name])[1] == snapshots[name], "Reception input changed while auditing")
        need(input_path.read_bytes() == raw_input and file_ref(input_path) == initial_input_ref, "Reception INPUT bytes changed while auditing")
        source_reader = file_ref(Path(__file__).resolve())
        need(source_reader == source_reader_before, "Cold reader changed while auditing")
        audit = {"schema": "hpc-forest-Q15-baseline-cold-audit-v1", "scope_id": SCOPE,
                 "verified": not neutral_fixture, "NEUTRAL": neutral_fixture,
                 "neutral_fixture_checks_passed": neutral_fixture, "baseline_qualification_only": True,
                 "native_authorization": False, "native_research_admitted": False, "scientific_gain_claimed": False,
                 "native_model_calls": 0, "Controller_instances": 0, "Mother_instances": 0, "native_workers_started": 0,
                 "individual_case_provenance_verified": False, "independent_raw_stdout_per_candidate_verified": False,
                 "independent_performance_audit_verified": False, "received_programs_or_scripts_executed": 0,
                 "subject_order": list(SUBJECTS), "confirmation_samples": 75, "job_id": config["job_id"],
                 "allocation": result["allocation"], "source_bindings": plan["source_bindings"],
                 "source_reader": source_reader, "reception_input": initial_input_ref, "input_refs": initial_refs,
                 "restoration_files": len(before), "restoration_inventory_sha256_before": digest(data(before)),
                 "restoration_inventory_sha256_after": digest(data(after)), "source_package_inventory_unchanged": True,
                 "source_package_inventory_sha256": digest(data(source_before)),
                 "external_executable_observations_only": [{"path": p, "sha256": s, "bytes": n} for p, s, n in sorted(material.external_tools)],
                 "external_executable_bytes_independently_received": False,
                 "limits": ["Baseline-only Q scope; no native matrix15 admission or future native source/plan binding.",
                            "Original combined streams retained; no individual-case or separate stdout attribution.",
                            "External executable hashes are received observations; their bytes, loader, OS and hardware are not independently audited.",
                            "Restored Git loose objects, protected contracts/config, SQLite and commands checked as data only.",
                            "Scheduler wrappers establish observed state/resources; source runner reports restart guard, not a separate restart-count attestation."]}
        for subject in subjects:
            record = {"schema": "hpc-forest-Q15-baseline-subject-reference-v1", "scope_id": SCOPE,
                      "verified": not neutral_fixture, "NEUTRAL": neutral_fixture, "baseline_qualification_only": True,
                      "native_authorization": False, "native_research_admitted": False, "source_reader": source_reader,
                      "output_archive": config["output_archive"], "source_plan_sha256": config["source_plan"]["sha256"], **subject}
            path = destination / (subject["subject_id"] + "-baseline-reference.json")
            with path.open("xb") as handle:
                handle.write(data(record))
        with (destination / "AUDIT-Q15-BASELINES.json").open("xb") as handle:
            handle.write(data(audit))
        need(file_ref(Path(__file__).resolve()) == source_reader and file_ref(input_path) == audit["reception_input"], "Reader/input changed before sealing")
        receipt = {"schema": "hpc-forest-Q15-cold-reader-receipt-v1", "verified": not neutral_fixture,
                   "NEUTRAL": neutral_fixture, "source_reader": source_reader, "audit": file_ref(destination / "AUDIT-Q15-BASELINES.json"),
                   "outputs": [file_ref(p) for p in sorted(destination.glob("*-baseline-reference.json"))], "native_authorization": False}
        with (destination / "RECU-LECTEUR-Q15.json").open("xb") as handle:
            handle.write(data(receipt))
        need(inventory(restored) == before, "Post-seal restored inventory changed")
        return audit
    except Exception as exc:
        with (destination / "REFUS-Q15.json").open("xb") as handle:
            handle.write(data({"schema": "hpc-forest-Q15-cold-refusal-v1", "verified": False, "error_type": type(exc).__name__,
                               "reason": str(exc), "native_authorization": False, "NEUTRAL": neutral_fixture}))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args()
    result = receive(args.input, args.input_sha256)
    print(json.dumps({"verified": result["verified"], "subjects": len(result["subject_order"]), "native_authorization": False}))


if __name__ == "__main__":
    main()
