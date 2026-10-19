"""Synthetic in-memory graph and inert files; never production receipts or real processes."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import statistics
import subprocess
import tarfile
import zlib
from pathlib import Path, PurePosixPath

import pytest

from hpc_forest import codex_mailbox, codex_process, codex_worker, contracts
from hpc_forest import native_r2max as native
from hpc_forest.core import InfrastructureError, atomic_json, digest, file_digest
from hpc_forest.r2max_archive_trace import PURPOSE


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(autouse=True)
def no_processes_or_persistent_hooks(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("No real process in neutral test"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("No real process in neutral test"))
    for module in (codex_mailbox, codex_process, codex_worker):
        monkeypatch.setattr(module, "MODEL", module.MODEL)
        monkeypatch.setattr(module, "EFFORT", module.EFFORT)
    for module in (codex_process, codex_worker):
        monkeypatch.setattr(module, "check_dependencies", module.check_dependencies)


def installed_unit_gate(tmp_path, monkeypatch):
    artifacts = {}
    for key in native.ARTIFACTS:
        path = tmp_path / (key + ".json")
        atomic_json(path, {"neutral_fixture_only": key})
        artifacts[key] = {"path": str(path), "sha256": file_digest(path)}
    model = next(iter(native.CELLS))
    state = {"model": model, "effort": "max", "session_id": native.CELLS[model], "job_id": "999999",
             "remote_root": "/UNIT/root", "artifacts": artifacts}
    path = tmp_path / "authorization.json"
    atomic_json(path, state)
    # An intentionally isolated metadata double; this is not validate_receipt admission.
    monkeypatch.setattr(native, "validate_receipt", lambda *a, **k: copy.deepcopy(state))
    native.install_identity(path, prepared=False)
    return path, state, codex_worker.check_dependencies


@pytest.mark.parametrize("field", ["job_id", "remote_root", "scope_id"])
def test_same_model_session_cannot_replace_cell_binding(tmp_path, monkeypatch, field):
    path, state, gate = installed_unit_gate(tmp_path, monkeypatch)
    assert gate(path, {native.SCOPE})["model"] == state["model"]
    state[field] = "OTHER_UNIT_BINDING"
    atomic_json(path, state)
    with pytest.raises(InfrastructureError, match="replaced"):
        gate(path, {native.SCOPE})


@pytest.mark.parametrize("key", ["plan", "source_zip", "cli_identity", "integration_review", "transport_admission"])
def test_same_pair_cannot_replace_valid_admission_refs(tmp_path, monkeypatch, key):
    path, state, gate = installed_unit_gate(tmp_path, monkeypatch)
    replacement = tmp_path / (key + "-replacement.json")
    atomic_json(replacement, {"different_inert_unit_admission": True})
    state["artifacts"][key] = {"path": str(replacement), "sha256": file_digest(replacement)}
    atomic_json(path, state)
    with pytest.raises(InfrastructureError, match="replaced"):
        gate(path, {native.SCOPE})


@pytest.mark.parametrize("key", sorted(native.ARTIFACTS))
def test_each_initial_artifact_is_rehashed_before_call(tmp_path, monkeypatch, key):
    path, state, gate = installed_unit_gate(tmp_path, monkeypatch)
    Path(state["artifacts"][key]["path"]).write_bytes(b"ALTERED_UNIT_DATA")
    with pytest.raises(InfrastructureError, match="changed R2 admission"):
        gate(path, {native.SCOPE})


def test_full_binding_checked_even_if_validator_double_returns_another_job(tmp_path, monkeypatch):
    path, state, gate = installed_unit_gate(tmp_path, monkeypatch)
    state["job_id"] = "999998"  # Receipt bytes remain frozen; independent binding still rejects.
    with pytest.raises(InfrastructureError, match="cell/admission/CLI"):
        gate(path, {native.SCOPE})


class UnitArchive:
    """A pure graph, with a fake inert ELF header; cannot qualify the actual contract."""
    def __init__(self):
        self.root = PurePosixPath("/UNIT/CLUSTER/Q/official-evaluator-trace")
        self.files, self.prepared = {}, {}
        source = Path(os.environ["R2MAX_CERTIFIED_PACKAGE"]) / "data/model-view/primetest.c"
        official = source.read_bytes()  # Official bytes are never compiled or run here.
        cases = {}
        for phase in ("search", "confirmation"):
            cases[phase] = []
            for number in range(1, 7):
                stdin = f"{phase}-{number}.data"
                self.prepared["validation/" + stdin] = f"UNIT_PRIVATE_{phase}_{number}".encode()
                cases[phase].append({"name": f"{phase}-case-{number}", "stdin": stdin, "argv": [], "files": [],
                    "capture_files": [], "input_fingerprint": f"UNIT_{phase}_{number}",
                    "expected": {"stdout": contracts.blob(f"UNIT_OUTPUT_{phase}_{number}".encode())}})
        contract = {**cases, "benchmark": {**cases["search"][-1], "name": "benchmark-case-1"},
                    "comparison": {"mode": "bytes"}}
        self.prepared.update({"validation/contract.json": encoded(contract), "validation/contract_tool.py": b"UNIT_NOT_EXECUTED_CHECKER",
            "validation/benchmark.sh": b"UNIT_NOT_EXECUTED_BENCHMARK", "source/src/model-view/primetest.c": official,
            "source/Makefile": b"UNIT_NO_BUILD", "source/run.sh": b"UNIT_NO_RUN",
            "certified-preparation-receipt.json": encoded({"protocol_timeout_seconds": 5})})
        for name, raw in self.prepared.items():
            if name.startswith("validation/"):
                self.files["trusted/" + name.removeprefix("validation/")] = raw
            elif name.startswith("source/"):
                self.files["unchanged-official-source/" + name.removeprefix("source/")] = raw
        def git_object(kind, raw):
            content = kind.encode() + b" " + str(len(raw)).encode() + b"\0" + raw
            identifier = hashlib.sha1(content, usedforsecurity=False).hexdigest()
            self.files["unchanged-official-source/.git/objects/" + identifier[:2] + "/" + identifier[2:]] = zlib.compress(content)
            return identifier
        def tree(entries):
            return git_object("tree", b"".join(mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(identifier)
                                               for mode, name, identifier in entries))
        leaf = tree([("100644", "primetest.c", git_object("blob", official))])
        src = tree([("40000", "model-view", leaf)])
        git_tree = tree([("100644", "Makefile", git_object("blob", b"UNIT_NO_BUILD")),
                         ("100644", "run.sh", git_object("blob", b"UNIT_NO_RUN")), ("40000", "src", src)])
        commit = git_object("commit", f"tree {git_tree}\nauthor UNIT\ncommitter UNIT\n\nUNIT_ONLY\n".encode())
        self.files["unchanged-official-source/.git/HEAD"] = b"ref: refs/heads/main\n"
        self.files["unchanged-official-source/.git/refs/heads/main"] = (commit + "\n").encode()
        protocol = {"build": ["{python}", "{trusted}/contract_tool.py", "build", "{worktree}", "{build}"],
            "check": ["{python}", "{trusted}/contract_tool.py", "check", "{binary}", "{phase}"],
            "benchmark": ["/bin/sh", "{trusted}/benchmark.sh", "{binary}"], "repetitions": 3, "confirmation_repetitions": 5,
            "warmups": 1, "timeout_seconds": 5, "build_timeout_seconds": 120,
            "environment": {"OMP_NUM_THREADS": "4", "OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "TRUE", "CUDA_VISIBLE_DEVICES": ""},
            "private_execution_audit": True, "private_execution_purpose": PURPOSE}
        protocol_id = digest({"protocol": protocol, "manifest": {name.removeprefix("trusted/"): sha(raw)
                              for name, raw in self.files.items() if name.startswith("trusted/")}})
        allocation = {"job_id": "UNIT_NOT_A_JOB"}
        trace = {"schema": "hpc-forest-primes-r2max-official-evaluator-trace-qualification-v1", "verified": True,
            "execution_purpose": PURPOSE, "reference_source_sha256": native.REFERENCE_SHA256, "allocation": allocation,
            "official_source_commit": commit, "protocol": protocol, "protocol_id": protocol_id,
            "private_execution_provenance": {}, "native_model_calls": 0, "new_model_candidates": 0,
            "native_first_start_proved": False, "performance_research_result": False, "negative_preserved_no_retry": True}
        for phase, repetitions in (("search", 3), ("confirmation", 5)):
            prefix = f"logs/e1/{PURPOSE}/{phase}/attempt-001/"
            build_prefix = f"builds/e1/{PURPOSE}/{phase}/attempt-001/"
            binary_name = build_prefix + "solution"
            binary = bytearray(80)
            binary[:6], binary[18:20] = b"\x7fELF\x02\x01", b"\xb7\x00"
            binary[30:30 + len(phase)] = phase.encode()
            self.files[binary_name] = bytes(binary)  # In-memory inert bytes, never an executable file.
            binary_sha = sha(self.files[binary_name])
            worktree = str(self.root / "unchanged-official-source")
            self.files[build_prefix + "compiler-command.json"] = encoded({"argv": ["/UNIT_GCC_NOT_RUN", "-I", worktree + "/src",
                worktree + "/src/model-view/primetest.c", *native.COMPILER_FLAGS, "-o", str(self.root / binary_name)],
                "compiler_flags": native.COMPILER_FLAGS})
            logs, proof_refs, times = [], [], [(n + 1) / 8 for n in range(repetitions)]
            names = ["build.log", "correctness.log", "warmup-0.log", *(f"sample-{n}.log" for n in range(repetitions))]
            for name in names:
                operation = "build" if name == "build.log" else "check" if name == "correctness.log" else "benchmark"
                log_name, context_name = prefix + name, prefix + name + ".private-context.json"
                proof_name = prefix + name + ".private-execution.json"
                argv = (["/UNIT_PYTHON_NOT_RUN", str(self.root / "trusted/contract_tool.py"), "build", worktree, str(self.root / build_prefix)]
                        if operation == "build" else ["/UNIT_PYTHON_NOT_RUN", str(self.root / "trusted/contract_tool.py"), "check", str(self.root / binary_name), phase]
                        if operation == "check" else ["/bin/sh", str(self.root / "trusted/benchmark.sh"), str(self.root / binary_name)])
                command_hashes = {argv[0]: sha(b"UNIT_EXTERNAL_COMMAND_DECLARATION"), argv[1]: sha(self.files[str(PurePosixPath(argv[1]).relative_to(self.root))])}
                if operation != "build":
                    command_hashes[str(self.root / binary_name)] = binary_sha
                selected = [] if operation == "build" else [*contract[phase], contract["benchmark"]] if operation == "check" else [contract["benchmark"]]
                context = {"schema": "hpc-forest-private-evaluation-context-v1", "never_model_input": True,
                    "execution_purpose": PURPOSE, "experiment_id": PURPOSE, "epoch": 1, "commit": commit, "tree_hash": git_tree,
                    "phase": phase, "protocol_id": protocol_id, "operation": operation, "argv": argv, "worktree": worktree,
                    "binary_path": str(self.root / binary_name), "binary_sha256_before": None if operation == "build" else binary_sha,
                    "command_file_sha256": command_hashes, "private_cases": [{"name": case["name"], "case_sha256": digest(case),
                        "stdin_sha256": sha(self.files["trusted/" + case["stdin"]]), "stdin_bytes": len(self.files["trusted/" + case["stdin"]])} for case in selected]}
                self.files[context_name] = encoded(context)
                case_refs, unique = [], {}
                if operation == "check":
                    for case in selected:
                        unique.setdefault(case["input_fingerprint"], case)
                    for case in unique.values():
                        parent = "private-audit/executions/" + digest({"phase": phase, "case": case["name"]})[:32]
                        self.files[parent + "/stdout.bin"] = contracts.unblob(case["expected"]["stdout"])
                        self.files[parent + "/stderr.bin"] = b"UNIT_PRIVATE_STDERR"
                        self.files[parent + "/execution.json"] = encoded({"case": case["name"], "returncode": 0, "timed_out": False, "never_model_input": True})
                        case_proof = {"schema": "hpc-forest-private-case-execution-v2", "case": case["name"], "case_sha256": digest(case),
                            "context": {"path": str(self.root / context_name), "sha256": sha(self.files[context_name]), "value": context},
                            "experiment_id": PURPOSE, "phase": phase, "role": "qualification-official-reference", "argv": [str(self.root / binary_name)],
                            "binary_path": str(self.root / binary_name), "binary_sha256_before": binary_sha, "binary_sha256_after": binary_sha,
                            "stdin_sha256": sha(self.files["trusted/" + case["stdin"]]), "stdin_bytes": len(self.files["trusted/" + case["stdin"]]),
                            "input_fingerprint_declared": case["input_fingerprint"], "asset_sha256": {}, "returncode": 0, "timed_out": False,
                            "never_model_input": True, "hashing_outside_execution_timer": True, "capture_layout": "separate_actual_stdout_and_stderr",
                            "execution_seconds": 0.01, "historical_record": {"file": "execution.json", "sha256": sha(self.files[parent + "/execution.json"])},
                            **{stream: {"file": stream + ".bin", "sha256": sha(self.files[parent + "/" + stream + ".bin"]),
                                "bytes": len(self.files[parent + "/" + stream + ".bin"])} for stream in ("stdout", "stderr")}}
                        case_name = parent + "/execution-provenance.json"
                        self.files[case_name] = encoded(case_proof)
                        case_refs.append({"path": str(self.root / case_name), "sha256": sha(self.files[case_name])})
                self.files[log_name] = encoded({"correct": True, "cases": len(unique)}) if operation == "check" else b"UNIT_COMBINED_STDOUT_STDERR"
                seconds = times[int(name.removeprefix("sample-").removesuffix(".log"))] if name.startswith("sample-") else 0.0625
                self.files[log_name + ".json"] = encoded({"argv": argv, "returncode": 0, "seconds": seconds, "timed_out": False, "log": str(self.root / log_name)})
                execution = {**context, "schema": "hpc-forest-private-evaluation-execution-v2", "verified": True,
                    "context": {"path": str(self.root / context_name), "sha256": sha(self.files[context_name])},
                    "binary_sha256_after": binary_sha, "returncode": 0, "timed_out": False, "measured_seconds": seconds,
                    "hashing_outside_measured_interval": True, "execution_semantics_changed": False,
                    "streams": {"layout": "original_run_process_combined_unchanged", "separate_stdout": None, "separate_stderr": None,
                        "combined_stdout_stderr": {"path": str(self.root / log_name), "sha256": sha(self.files[log_name]), "bytes": len(self.files[log_name])}},
                    "case_execution_records": case_refs}
                self.files[proof_name] = encoded(execution)
                proof_refs.append({"path": str(self.root / proof_name), "sha256": sha(self.files[proof_name])})
                logs.append(str(self.root / log_name))
            trace[phase] = {"status": "valid", "correct": True, "commit": commit, "tree_hash": git_tree,
                "cache_key": digest({"tree": git_tree, "protocol": protocol_id, "epoch": 1}), "binary_sha256": binary_sha,
                "times": times, "mean_seconds": statistics.mean(times), "score": 0.5, "logs": logs}
            trace["private_execution_provenance"][phase] = proof_refs
        self.files["trace-qualification.json"] = encoded(trace)
        self.value = {"prepared_root": "/UNIT/CLUSTER/Q/prepared", "allocation": allocation,
            "prepared_files": {name: sha(raw) for name, raw in self.prepared.items()}}
        self.seal()

    def seal(self):
        self.value["official_evaluator_trace_files"] = {name: sha(raw) for name, raw in self.files.items()}
        self.value["official_evaluator_trace_qualification"] = {"path": str(self.root / "trace-qualification.json"),
            "sha256": sha(self.files["trace-qualification.json"]), "verified": True, "execution_purpose": PURPOSE}

    def read(self):
        return native.verify_trace_members(self.value, self.files.__getitem__, read_prepared_member=self.prepared.__getitem__)

    def json(self, name):
        return json.loads(self.files[name])

    def update(self, name, value):
        self.files[name] = encoded(value)

    def resign(self):
        # Rehash outer refs too: tests must reach the semantic binding, not only an old SHA.
        ordered = ([n for n in self.files if n.endswith(".private-context.json")]
            + [n for n in self.files if n.endswith("/execution-provenance.json")]
            + [n for n in self.files if n.endswith(".private-execution.json")] + ["trace-qualification.json"])
        def fix(value, parent):
            if isinstance(value, dict):
                value = {k: fix(v, parent) for k, v in value.items()}
                if "path" in value and "sha256" in value and str(value["path"]).startswith(str(self.root) + "/"):
                    name = str(PurePosixPath(value["path"]).relative_to(self.root))
                    if name in self.files:
                        value["sha256"] = sha(self.files[name])
                        if "bytes" in value:
                            value["bytes"] = len(self.files[name])
                        if "value" in value:
                            value["value"] = self.json(name)
                if "file" in value and "sha256" in value:
                    name = str(PurePosixPath(parent) / value["file"])
                    if name in self.files:
                        value["sha256"] = sha(self.files[name])
                        if "bytes" in value:
                            value["bytes"] = len(self.files[name])
                return value
            if isinstance(value, list):
                return [fix(v, parent) for v in value]
            return value
        for name in ordered:
            self.update(name, fix(self.json(name), str(PurePosixPath(name).parent)))
        self.seal()


def test_received_graph_verified_without_any_cluster_file_access():
    graph = UnitArchive()
    proof = graph.read()
    assert proof["evaluator_executions"] == 14 and proof["case_executions"] == 13
    assert proof["cluster_paths_followed_locally"] is False
    assert proof["external_executable_bytes_independently_verified"] is False


@pytest.mark.parametrize("target", ["raw", "context", "phase", "binary", "outcome", "input", "measure"])
def test_received_graph_tampering_refused_even_after_outer_rehash(target):
    graph = UnitArchive()
    case_name = next(name for name in graph.files if name.endswith("/execution-provenance.json"))
    proof_name = next(name for name in graph.files if name.endswith(".private-execution.json") and "/correctness.log" in name)
    if target == "raw":
        graph.files[str(PurePosixPath(case_name).parent / "stdout.bin")] = b"ALTERED_PRIVATE_OUTPUT"
    elif target == "context":
        name = next(name for name in graph.files if name.endswith(".private-context.json"))
        value = graph.json(name)
        value["experiment_id"] = "OTHER_EXPERIMENT"
        graph.update(name, value)
    elif target == "phase":
        value = graph.json(case_name)
        value["phase"] = "confirmation"
        graph.update(case_name, value)
    elif target == "binary":
        value = graph.json(proof_name)
        value["binary_sha256_after"] = "0" * 64
        graph.update(proof_name, value)
    elif target == "outcome":
        value = graph.json("trace-qualification.json")
        value["search"]["times"][0] += 1
        value["search"]["mean_seconds"] = statistics.mean(value["search"]["times"])
        graph.update("trace-qualification.json", value)
    elif target == "input":
        graph.files["trusted/search-1.data"] = b"ALTERED_PRIVATE_INPUT"
    else:
        name = next(name for name in graph.files if "/sample-0.log.json" in name)
        value = graph.json(name)
        value["seconds"] += 1
        graph.update(name, value)
    graph.resign()
    with pytest.raises(InfrastructureError):
        graph.read()


@pytest.mark.parametrize("kind", ["escape", "foreign_absolute", "absent", "unlinked", "unlinked_raw", "duplicate"])
def test_received_graph_unsafe_absent_or_unlinked_refs_refused(kind):
    graph = UnitArchive()
    trace = graph.json("trace-qualification.json")
    refs = trace["private_execution_provenance"]["search"]
    if kind == "escape":
        refs[0]["path"] = str(graph.root) + "/../outside.json"
    elif kind == "foreign_absolute":
        refs[0]["path"] = "/FOREIGN/never-read.json"
    elif kind == "absent":
        refs[0]["path"] = str(graph.root / "missing.json")
    elif kind == "duplicate":
        refs[1] = refs[0]
    elif kind == "unlinked_raw":
        graph.files["private-audit/stray-stdout.bin"] = b"UNLINKED_UNIT_RAW"
    else:
        name = next(name for name in graph.files if name.endswith(".private-execution.json"))
        graph.files[name + ".unlinked.private-execution.json"] = graph.files[name]
    graph.update("trace-qualification.json", trace)
    graph.seal()
    with pytest.raises(InfrastructureError):
        graph.read()


def test_reception_checks_received_members_with_prepared_reader_not_cluster_paths(tmp_path, monkeypatch):
    graph = UnitArchive()
    qualification = {**graph.value, "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
                     "preparation_manifest_sha256": native.PREPARATION_MANIFEST_SHA256}
    qpath = tmp_path / "unit-qualification.json"
    atomic_json(qpath, qualification)
    archive = tmp_path / "unit-reception.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        entries = {"qualification.json": qpath.read_bytes(),
                   **{"prepared/" + name: raw for name, raw in graph.prepared.items()},
                   **{"official-evaluator-trace/" + name: raw for name, raw in graph.files.items()}}
        for name, raw in entries.items():
            member = tarfile.TarInfo("qualification/" + name)
            member.size = len(raw)
            output.addfile(member, io.BytesIO(raw))
    audit_path = tmp_path / "unit-audit.json"
    audit = {"schema": "hpc-forest-primes-r2max-allocated-contract-reception-audit-v1", "scope_id": native.SCOPE,
             "verified": True, "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
             "preparation_manifest_sha256": native.PREPARATION_MANIFEST_SHA256,
             "qualification_sha256": file_digest(qpath), "archive_sha256": file_digest(archive),
             "all_members_regular_unique": True, "restored_files_byte_identical": True,
             "actual_compiler_command_verified": True, "certified_twelve_case_contract_verified": True, "native_model_calls": 0}
    atomic_json(audit_path, audit)
    received = {**qualification, "qualification_sha256": file_digest(qpath),
                "archive": {"path": str(archive), "sha256": file_digest(archive)},
                "audit": {"path": str(audit_path), "sha256": file_digest(audit_path)}}
    # Only the separately covered finite-contract gate is stubbed in this graph unit.
    # UNIT_NOT_A_JOB, fake checker and inert ELF cannot admit a real native source.
    monkeypatch.setattr(native, "verify_preparation", lambda *a: None)
    monkeypatch.setattr(native, "verify_qualification_members", lambda *a: None)
    native.verify_reception(received, qpath, tmp_path)
