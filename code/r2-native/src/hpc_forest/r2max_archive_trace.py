"""Read original received members only; never follow cluster paths on the local host."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import statistics
import zlib
from pathlib import PurePosixPath

from .core import InfrastructureError, digest
from .primes_contract import COMPILER_FLAGS, REFERENCE_SHA256

PURPOSE = "qualification-only-not-model-official"


def require(condition, message):
    if not condition:
        raise InfrastructureError("Received Evaluator trace: " + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(value):
    require(isinstance(value, str) and value and "\\" not in value and "\0" not in value, "unsafe member name")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == value and value != ".", "member escape")
    return value


def absolute(value):
    require(isinstance(value, str) and value and "\\" not in value and "\0" not in value, "unsafe remote path")
    path = PurePosixPath(value)
    require(path.is_absolute() and ".." not in path.parts and str(path) == value, "remote path escape")
    return path


def object_value(raw):
    value = json.loads(raw)
    require(isinstance(value, dict), "object required")
    return value


def verify_archive_trace(value, read_member, *, read_prepared_member=None):
    try:
        return _verify(value, read_member, read_prepared_member)
    except InfrastructureError:
        raise
    except (KeyError, TypeError, ValueError, OSError, zlib.error) as exc:
        raise InfrastructureError("Received Evaluator trace: malformed, absent or inconsistent member") from exc


def _verify(value, read_member, read_prepared):
    proof = value.get("official_evaluator_trace_qualification", {})
    files = value.get("official_evaluator_trace_files", {})
    require(proof.get("verified") is True and proof.get("execution_purpose") == PURPOSE
            and proof.get("sha256") == files.get("trace-qualification.json"),
            "new source needs its own official Evaluator trace qualification")
    require(read_prepared is not None and isinstance(files, dict) and 0 < len(files) <= 1000,
            "prepared bytes and bounded inventory required")
    members, total = {}, 0
    for name, expected in files.items():
        relative(name)
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "invalid member SHA")
        raw = read_member(name)
        require(isinstance(raw, bytes), "original member bytes required")
        total += len(raw)
        require(total <= 64 * 1024 * 1024 and sha(raw) == expected, "member SHA/size differs")
        members[name] = raw
    root = absolute(proof["path"]).parent
    require(root.name == "official-evaluator-trace"
            and root == absolute(value["prepared_root"]).parent / "official-evaluator-trace"
            and absolute(proof["path"]).name == "trace-qualification.json", "qualification root binding differs")

    def key(path):
        original = absolute(path)
        require(original.is_relative_to(root), "reference escapes received trace root")
        name = relative(original.relative_to(root).as_posix())
        require(name in members, "reference absent from received inventory")
        return name

    def referenced(ref, expected_name=None):
        require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "invalid linked reference")
        name = key(ref["path"])
        require(ref["sha256"] == files[name] and (expected_name is None or name == expected_name), "linked reference SHA/path differs")
        return name, object_value(members[name])

    trace = object_value(members["trace-qualification.json"])
    require(trace.get("schema") == "hpc-forest-primes-r2max-official-evaluator-trace-qualification-v1"
            and trace.get("verified") is True and trace.get("execution_purpose") == PURPOSE
            and trace.get("reference_source_sha256") == REFERENCE_SHA256
            and trace.get("allocation") == value.get("allocation")
            and trace.get("native_model_calls") == 0 and trace.get("new_model_candidates") == 0
            and trace.get("native_first_start_proved") is False and trace.get("performance_research_result") is False
            and trace.get("negative_preserved_no_retry") is True
            and set(trace.get("private_execution_provenance", {})) == {"search", "confirmation"},
            "official-only allocation/zero-model summary differs")
    prepared_files = value.get("prepared_files", {})
    trusted = {name.removeprefix("trusted/"): expected for name, expected in files.items() if name.startswith("trusted/")}
    expected_trusted = {name.removeprefix("validation/"): expected for name, expected in prepared_files.items()
                        if name.startswith("validation/")}
    require(trusted and trusted == expected_trusted, "trusted contract/input/checker inventory differs from preparation")
    for name in trusted:
        require(members["trusted/" + name] == read_prepared("validation/" + name), "trusted bytes differ from preparation")
    source_files = {name.removeprefix("unchanged-official-source/"): expected for name, expected in files.items()
                    if name.startswith("unchanged-official-source/") and not name.startswith("unchanged-official-source/.git/")}
    expected_source = {name.removeprefix("source/"): expected for name, expected in prepared_files.items() if name.startswith("source/")}
    require(source_files == expected_source and source_files, "official worktree differs from preparation")
    for name in source_files:
        require(members["unchanged-official-source/" + name] == read_prepared("source/" + name), "official worktree bytes differ")
    official_name = "unchanged-official-source/src/model-view/primetest.c"
    require(files[official_name] == REFERENCE_SHA256, "official source SHA differs")
    contract = object_value(members["trusted/contract.json"])
    preparation = object_value(read_prepared("certified-preparation-receipt.json"))
    protocol = trace["protocol"]
    expected_protocol = {"build": ["{python}", "{trusted}/contract_tool.py", "build", "{worktree}", "{build}"],
        "check": ["{python}", "{trusted}/contract_tool.py", "check", "{binary}", "{phase}"],
        "benchmark": ["/bin/sh", "{trusted}/benchmark.sh", "{binary}"], "repetitions": 3,
        "confirmation_repetitions": 5, "warmups": 1, "timeout_seconds": preparation["protocol_timeout_seconds"],
        "build_timeout_seconds": 120, "environment": {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE",
            "OMP_PROC_BIND": "TRUE", "CUDA_VISIBLE_DEVICES": ""}, "private_execution_audit": True,
        "private_execution_purpose": PURPOSE}
    require(protocol == expected_protocol, "Evaluator protocol differs")
    protocol_id = digest({"protocol": protocol, "manifest": trusted})
    require(trace.get("protocol_id") == protocol_id, "protocol/trusted SHA binding differs")
    commit = trace["official_source_commit"]
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "invalid official commit")

    def git_object(identifier, kind):
        require(isinstance(identifier, str) and re.fullmatch(r"[0-9a-f]{40}", identifier), "invalid Git object")
        name = "unchanged-official-source/.git/objects/" + identifier[:2] + "/" + identifier[2:]
        decoder = zlib.decompressobj()
        raw = decoder.decompress(members[name], 8 * 1024 * 1024 + 1)
        require(len(raw) <= 8 * 1024 * 1024 and decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail, "oversized or trailing Git object")
        require(hashlib.sha1(raw, usedforsecurity=False).hexdigest() == identifier, "Git object bytes differ")
        header, body = raw.split(b"\0", 1)
        require(header == kind.encode() + b" " + str(len(body)).encode(), "Git object type/size differs")
        return body

    head = members["unchanged-official-source/.git/HEAD"].decode().strip()
    require(head == "ref: refs/heads/main"
            and members["unchanged-official-source/.git/refs/heads/main"].decode().strip() == commit,
            "official HEAD/commit differs")
    tree = git_object(commit, "commit").splitlines()[0].decode().removeprefix("tree ")
    tree_cursor = tree
    for index, part in enumerate(("src", "model-view", "primetest.c")):
        raw, entries = git_object(tree_cursor, "tree"), {}
        while raw:
            entry, rest = raw.split(b"\0", 1)
            mode, name = entry.split(b" ", 1)
            require(len(rest) >= 20 and name.decode() not in entries, "malformed Git tree")
            entries[name.decode()] = (mode, rest[:20].hex())
            raw = rest[20:]
        mode, tree_cursor = entries[part]
        require(mode == (b"100644" if index == 2 else b"40000"), "official Git source mode differs")
    require(git_object(tree_cursor, "blob") == members[official_name], "Git official source blob differs")
    used_proofs, used_contexts, used_cases, used_logs = set(), set(), set(), set()
    external_command_hashes = {}
    python = None
    worktree = str(root / "unchanged-official-source")
    for phase, repetitions in (("search", 3), ("confirmation", 5)):
        outcome = trace[phase]
        require(outcome.get("status") == "valid" and outcome.get("correct") is True
                and outcome.get("commit") == commit and outcome.get("tree_hash") == tree
                and outcome.get("cache_key") == digest({"tree": tree, "protocol": protocol_id, "epoch": 1}),
                "outcome identity/commit/tree/cache differs")
        times = outcome.get("times", [])
        require(len(times) == repetitions and all(type(t) in {int, float} and math.isfinite(t) and t > 0 for t in times)
                and outcome.get("mean_seconds") == statistics.mean(times) and outcome.get("score") == 0.5,
                "outcome measures/summary differ")
        prefix = f"logs/e1/{PURPOSE}/{phase}/attempt-001/"
        log_names = [prefix + name for name in ["build.log", "correctness.log", "warmup-0.log",
                                               *(f"sample-{n}.log" for n in range(repetitions))]]
        require([key(path) for path in outcome.get("logs", [])] == log_names, "outcome log order/coverage differs")
        refs = trace.get("private_execution_provenance", {}).get(phase, [])
        require(len(refs) == len(log_names), "missing/unlinked Evaluator references")
        build_prefix = f"builds/e1/{PURPOSE}/{phase}/attempt-001/"
        binary_key = build_prefix + "solution"
        binary = members[binary_key]
        binary_sha = sha(binary)
        require(len(binary) >= 64 and binary[:6] == b"\x7fELF\x02\x01" and binary[18:20] == b"\xb7\x00"
                and outcome.get("binary_sha256") == binary_sha, "received ARM64 outcome binary differs")
        compiler = object_value(members[build_prefix + "compiler-command.json"])
        compiler_argv = compiler.get("argv", [])
        require(compiler_argv and absolute(compiler_argv[0]).is_absolute()
                and compiler_argv == [compiler_argv[0], "-I", worktree + "/src", worktree + "/src/model-view/primetest.c",
                                     *COMPILER_FLAGS, "-o", str(root / binary_key)]
                and compiler.get("compiler_flags") == COMPILER_FLAGS, "official compiler command differs")
        for log_name, proof_ref in zip(log_names, refs, strict=True):
            proof_name, execution = referenced(proof_ref, log_name + ".private-execution.json")
            require(proof_name not in used_proofs, "duplicate Evaluator reference")
            used_proofs.add(proof_name)
            context_name, context = referenced(execution.get("context"), log_name + ".private-context.json")
            used_contexts.add(context_name)
            operation = "build" if log_name.endswith("/build.log") else "check" if log_name.endswith("/correctness.log") else "benchmark"
            metadata = {"schema": "hpc-forest-private-evaluation-context-v1", "never_model_input": True,
                "execution_purpose": PURPOSE, "experiment_id": PURPOSE, "epoch": 1, "commit": commit,
                "tree_hash": tree, "phase": phase, "protocol_id": protocol_id, "operation": operation,
                "worktree": worktree, "binary_path": str(root / binary_key),
                "binary_sha256_before": None if operation == "build" else binary_sha}
            require(all(context.get(k) == v for k, v in metadata.items()), "context experiment/phase/commit/tree/binary differs")
            cases = [] if operation == "build" else [*contract[phase], contract["benchmark"]] if operation == "check" else [contract["benchmark"]]
            private_cases = [{"name": case["name"], "case_sha256": digest(case),
                "stdin_sha256": files["trusted/" + relative(case["stdin"])],
                "stdin_bytes": len(members["trusted/" + case["stdin"]])} for case in cases]
            require(context.get("private_cases") == private_cases, "context input/case bytes differ")
            argv = context.get("argv", [])
            require(argv and isinstance(argv[0], str), "missing command argv")
            if operation != "benchmark":
                absolute(argv[0])
                python = python or argv[0]
                require(argv[0] == python, "Python command identity differs between phases")
            expected_argv = ([python, str(root / "trusted/contract_tool.py"), "build", worktree, str(root / build_prefix)]
                             if operation == "build" else [python, str(root / "trusted/contract_tool.py"), "check", str(root / binary_key), phase]
                             if operation == "check" else ["/bin/sh", str(root / "trusted/benchmark.sh"), str(root / binary_key)])
            require(argv == expected_argv, "command/binary argv differs")
            hashes = context.get("command_file_sha256", {})
            expected_hash_keys = {argv[0], str(root / ("trusted/benchmark.sh" if operation == "benchmark" else "trusted/contract_tool.py"))}
            if operation != "build":
                expected_hash_keys.add(str(root / binary_key))
            require(set(hashes) == expected_hash_keys, "command file references differ")
            for path, expected_hash in hashes.items():
                require(isinstance(expected_hash, str) and re.fullmatch(r"[0-9a-f]{64}", expected_hash), "invalid command hash")
                if absolute(path).is_relative_to(root):
                    require(files[key(path)] == expected_hash, "received command file SHA differs")
                else:
                    require(path not in external_command_hashes or external_command_hashes[path] == expected_hash,
                            "external command declaration differs")
                    external_command_hashes[path] = expected_hash
            require(execution.get("schema") == "hpc-forest-private-evaluation-execution-v2" and execution.get("verified") is True
                    and all(execution.get(k) == v for k, v in context.items() if k != "schema")
                    and execution.get("binary_sha256_after") == binary_sha and execution.get("returncode") == 0
                    and execution.get("timed_out") is False and execution.get("execution_semantics_changed") is False
                    and execution.get("hashing_outside_measured_interval") is True, "Evaluator execution metadata differs")
            result = object_value(members[log_name + ".json"])
            seconds = execution.get("measured_seconds")
            require(type(seconds) in {int, float} and math.isfinite(seconds) and seconds > 0
                    and result == {"argv": argv, "returncode": 0, "seconds": seconds, "timed_out": False, "log": str(root / log_name)},
                    "original process result/measure differs")
            if "/sample-" in log_name:
                require(times[int(PurePosixPath(log_name).stem.split("-")[1])] == seconds, "outcome sample differs from measured log")
            streams = execution.get("streams", {})
            combined = streams.get("combined_stdout_stderr", {})
            require(streams.get("layout") == "original_run_process_combined_unchanged"
                    and streams.get("separate_stdout") is None and streams.get("separate_stderr") is None
                    and combined == {"path": str(root / log_name), "sha256": files[log_name], "bytes": len(members[log_name])},
                    "received original combined stream differs")
            used_logs.update((log_name, log_name + ".json"))
            case_refs = execution.get("case_execution_records", [])
            if operation != "check":
                require(case_refs == [], "unlinked cases on non-check operation")
                continue
            unique_cases, seen = [], set()
            for case in cases:
                identifier = (case["input_fingerprint"], tuple(case["capture_files"]))
                if identifier not in seen:
                    seen.add(identifier)
                    unique_cases.append(case)
            require(len(case_refs) == len(unique_cases), "checker case coverage differs")
            expected_cases = {digest(case): case for case in unique_cases}
            got_cases = set()
            for case_ref in case_refs:
                case_name, case_proof = referenced(case_ref)
                require(case_name.startswith("private-audit/executions/")
                        and len(PurePosixPath(case_name).parts) == 4
                        and re.fullmatch(r"[0-9a-f]{32}", PurePosixPath(case_name).parts[2])
                        and PurePosixPath(case_name).name == "execution-provenance.json" and case_name not in used_cases,
                        "unlinked/duplicate case execution reference")
                used_cases.add(case_name)
                case_digest = case_proof.get("case_sha256")
                require(case_digest in expected_cases and case_digest not in got_cases, "case identity/coverage differs")
                got_cases.add(case_digest)
                case = expected_cases[case_digest]
                require(case_proof.get("schema") == "hpc-forest-private-case-execution-v2"
                        and case_proof.get("context") == {"path": str(root / context_name), "sha256": files[context_name], "value": context}
                        and case_proof.get("experiment_id") == PURPOSE and case_proof.get("phase") == phase
                        and case_proof.get("role") == "qualification-official-reference"
                        and case_proof.get("argv") == [str(root / binary_key), *case["argv"]]
                        and case_proof.get("binary_path") == str(root / binary_key)
                        and case_proof.get("binary_sha256_before") == case_proof.get("binary_sha256_after") == binary_sha
                        and case_proof.get("stdin_sha256") == files["trusted/" + case["stdin"]]
                        and case_proof.get("stdin_bytes") == len(members["trusted/" + case["stdin"]])
                        and case_proof.get("input_fingerprint_declared") == case["input_fingerprint"]
                        and case_proof.get("asset_sha256") == {} and case_proof.get("case") == case["name"]
                        and case_proof.get("returncode") == 0 and case_proof.get("timed_out") is False
                        and case_proof.get("never_model_input") is True
                        and case_proof.get("hashing_outside_execution_timer") is True
                        and case_proof.get("capture_layout") == "separate_actual_stdout_and_stderr"
                        and case_proof.get("context_changed_after_execution") is not True
                        and type(case_proof.get("execution_seconds")) in {int, float}
                        and math.isfinite(case_proof["execution_seconds"]) and case_proof["execution_seconds"] > 0,
                        "case context/phase/binary/input/return metadata differs")
                parent = str(PurePosixPath(case_name).parent)
                for stream in ("stdout", "stderr"):
                    stream_name = parent + "/" + stream + ".bin"
                    require(case_proof.get(stream) == {"file": stream + ".bin", "sha256": files[stream_name], "bytes": len(members[stream_name])},
                            "case raw stream SHA/bytes differ")
                expected_stdout = case["expected"]["stdout"]
                raw_stdout = members[parent + "/stdout.bin"]
                require(base64.b64decode(expected_stdout["base64"], validate=True) == raw_stdout
                        and expected_stdout["sha256"] == sha(raw_stdout) and expected_stdout["bytes"] == len(raw_stdout),
                        "actual official stdout differs from byte oracle")
                historical = parent + "/execution.json"
                require(case_proof.get("historical_record") == {"file": "execution.json", "sha256": files[historical]}
                        and object_value(members[historical]) == {"case": case["name"], "returncode": 0, "timed_out": False, "never_model_input": True},
                        "historical execution record differs")
            require(object_value(members[log_name]) == {"correct": True, "cases": len(unique_cases)}, "combined checker JSON differs")
    require({name for name in files if name.endswith(".private-execution.json")} == used_proofs
            and {name for name in files if name.endswith(".private-context.json")} == used_contexts
            and {name for name in files if name.endswith("/execution-provenance.json")} == used_cases,
            "unlinked private execution/context/case references")
    require({name for name in files if name.startswith("logs/")} == used_logs | used_proofs | used_contexts,
            "unlinked original logs")
    expected_private = {str(PurePosixPath(name).parent / suffix) for name in used_cases
                        for suffix in ("execution-provenance.json", "execution.json", "stdout.bin", "stderr.bin")}
    require({name for name in files if name.startswith("private-audit/")} == expected_private,
            "unlinked private raw execution member")
    return {"original_archive_links_verified": True, "phases": ["search", "confirmation"],
            "evaluator_executions": len(used_proofs), "case_executions": len(used_cases),
            "cluster_paths_followed_locally": False, "external_executable_bytes_independently_verified": False}
