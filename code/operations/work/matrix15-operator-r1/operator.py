"""Local one-cell operator. PREPARE is the default; only ROOT opts into execution."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[2]
WORK = BASE / "work/matrix15-operator-r1"
OUTPUT = BASE / "outputs/HPC-Forest-Matrice15-Operator-Preparation-r1"
CLAIMS = WORK / "claims"
BUILDER = BASE / "outputs/HPC-Forest-Matrice15-Extension-Operation-Preparation-r1/build_inputs.py"
BUILDER_SHA = "4d26cdab42a7b47cc8d326fbd638e9f44fbe404dbcac40ad64cf7dba42dd99d1"
ROMEO_SOURCE_SHA = "a07d231e5bec01b6402503b391afb0a164c833420ce4bc67f5957aabb8ffb3ec"
PREREQUISITES = BASE / "outputs/HPC-Forest-Matrice15-Extension-Gate-Packet-r1/finalisation-r3/PREREQUISITES.json"
REQUEST_SCHEMA = "hpc-forest-matrix15-local-operator-input-v1"
REQUEST_FIELDS = {"schema", "cell_key", "unit_preparation", "extension_prepared", "prerequisites",
                  "owned_worker_receipts", "cli_executable", "skill_roots", "marker_poll_seconds",
                  "marker_max_polls", "acceptance_max_polls"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf8")


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def physical(path):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts and not any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)),
        "Ordinary absolute path required")
    return path


def ref(path):
    path = physical(Path(path).absolute())
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(item):
    need(type(item) is dict and set(item) == {"path", "sha256"}, "Exact path/SHA reference required")
    path = physical(item["path"])
    need(ref(path) == item, "Referenced bytes changed")
    return path


def document(item):
    return parse(checked(item).read_bytes())


def write(path, value):
    path = physical(Path(path).absolute())
    need(any(path.is_relative_to(root) and path != root for root in (WORK, OUTPUT)),
         "Operator evidence must remain inside its owned roots")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(value if isinstance(value, bytes) else encoded(value))
        target.flush()
        os.fsync(target.fileno())
    return ref(path)


class Journal:
    """A new journal is exclusive; interrupted actions are never retried here."""
    def __init__(self, output):
        self.output = physical(Path(output).absolute())
        need(any(self.output.is_relative_to(root) and self.output != root for root in (WORK, OUTPUT)),
             "Owned run directory required")
        self.output.mkdir(parents=True, exist_ok=False)
        self.path = self.output / "STATE.jsonl"
        self.stream = self.path.open("xb")
        self.sequence = 0

    def record(self, state, **facts):
        self.sequence += 1
        self.stream.write(encoded({"schema": "hpc-forest-matrix15-operator-journal-v1",
                                  "sequence": self.sequence, "observed_at": time.time(), "state": state, **facts}))
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def consume_unit(request, unit, request_ref, review_ref, journal):
    """One durable operator claim per registered cell, across every output path."""
    identity = hashlib.sha256(request["cell_key"].encode("utf8")).hexdigest()
    claim = write(CLAIMS / (identity + ".json"), {
        "schema": "hpc-forest-matrix15-operator-one-cell-claim-v1", "stage": "claimed_before_mcp",
        "cell_key": request["cell_key"], "session_id": unit["binding_without_job_id"]["session_id"],
        "unit_preparation": request["unit_preparation"], "input": request_ref, "root_review": review_ref,
        "journal": str(journal.path), "claimed_at": time.time(), "automatic_retry": False,
        "operator_may_remove_claim": False})
    journal.record("UNIT_CLAIMED_BEFORE_MCP", claim=claim)
    return claim


def payload(response):
    result = response.get("structuredContent")
    if result is None:
        texts = [item["text"] for item in response.get("content", []) if item.get("type") == "text"]
        need(len(texts) == 1, "One unambiguous MCP result required")
        result = parse(texts[0])
    need(type(result) is dict, "Object MCP result required")
    return result


class PrimaryMCP:
    """Preserve the complete SDK result, including aliases and every content block."""
    def __init__(self, transfer, journal):
        self.transfer, self.journal = transfer, journal
        self.counter = 0

    async def call(self, name, arguments, *, allow_missing=False):
        self.counter += 1
        number = self.counter
        # Use the same canonical spelling in tool args, receipts and local refs.
        if "local_path" in arguments:
            arguments = {**arguments, "local_path": str(physical(Path(arguments["local_path"]).absolute()))}
        self.journal.record("MCP_INTENT", call=number, tool=name, arguments=arguments)
        result = await self.transfer.session.call_tool(name, arguments)
        response = result.model_dump(mode="json", by_alias=True)
        observation = {"schema": "hpc-forest-primary-tool-observation-v1", "tool": "mcp__romeo__" + name,
                       "arguments": arguments, "observed_at": time.time(), "response": response}
        observed = write(self.journal.output / f"primary/{number:04d}-{name}.json", observation)
        self.journal.record("MCP_RECEIVED", call=number, observation=observed)
        data = payload(response)
        if response.get("isError") is True or data.get("ok") is not True:
            text = json.dumps(data, ensure_ascii=False).casefold()
            absent = any(word in text for word in ("not_found", "enoent", "no such file or directory", "does not exist"))
            if allow_missing and absent:
                return None, observed
            raise ValueError("MCP failure; preserved primary receipt: " + observed["path"])
        return data, observed


def validate_request(value):
    need(type(value) is dict and set(value) == REQUEST_FIELDS and value["schema"] == REQUEST_SCHEMA,
         "Exact operator input required")
    need(type(value["cell_key"]) is str and value["cell_key"], "Explicit registered cell required")
    need(type(value["owned_worker_receipts"]) is list, "Explicit actual owned-worker receipts or [] required")
    need(type(value["skill_roots"]) is list and value["skill_roots"], "Explicit metadata-only skill roots required")
    need(type(value["cli_executable"]) is str and physical(value["cli_executable"]).is_file(),
         "Actual explicit CLI executable required before preparing a job")
    for root in value["skill_roots"]:
        physical(root)
    need(type(value["marker_poll_seconds"]) in (int, float) and 0 < value["marker_poll_seconds"] <= 10,
         "Bounded polling interval required")
    for key in ("marker_max_polls", "acceptance_max_polls"):
        need(type(value[key]) is int and 1 <= value[key] <= 300, "Bounded read-only polling required")
    for key in ("unit_preparation", "extension_prepared", "prerequisites"):
        checked(value[key])
    need(value["prerequisites"] == ref(PREREQUISITES), "Actual finalized extension prerequisites required")
    for item in value["owned_worker_receipts"]:
        checked(item)
    return value


def review_execution(request_ref, review_ref):
    review = document(review_ref)
    request = validate_request(document(request_ref))
    unit = document(request["unit_preparation"])
    prepared = document(request["extension_prepared"])
    identity = document(prepared["locked_sources"]["VENV-RUNTIME-IDENTITY.json"])
    sources = {"builder": BUILDER_SHA, "RomeoFiles": ROMEO_SOURCE_SHA,
               "reviewed_sources": {name: item["sha256"] for name, item in prepared["locked_sources"].items()},
               "reviewed_bootstrap": {name: item["sha256"] for name, item in prepared["locked_bootstrap"].items()},
               "launcher": identity["launcher"]}
    need(review.get("schema") == "hpc-forest-matrix15-operator-root-review-v1"
         and review.get("decision") == "SHIP" and review.get("root_execute_one_approved") is True
         and review.get("input_sha256") == request_ref["sha256"]
         and review.get("operator_sha256") == ref(Path(__file__).absolute())["sha256"]
         and review.get("job_body_sha256") == unit["job_body"]["sha256"]
         and review.get("source_pins") == sources,
         "ROOT SHIP must bind this exact input, operator, body and source/runtime pins")
    need(unit["cell_key"] == prepared["cell_key"] == request["cell_key"]
         and unit["prerequisites"] == prepared["prerequisite_ref"] == request["prerequisites"],
         "Prepared unit, builder and prerequisites must name the same one cell")
    return request, unit, prepared


class Sources:
    """Load the existing reviewed producers; never replace their admission checks."""
    def __init__(self):
        raw = checked({"path": str(BUILDER), "sha256": BUILDER_SHA}).read_bytes()
        spec = importlib.util.spec_from_file_location("matrix15_operator_builder", BUILDER)
        self.builder = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(BUILDER), "exec", dont_inherit=True), self.builder.__dict__)
        _upstream, self.reader, self.dynamic, self.capacity, self.bootstrap = self.builder.runtime()
        self.dynamic.load_runtime()  # Exact sealed127 source ZIP and runtime, file-only verification.
        self.project = self.dynamic.PROJECT
        for module in (self.dynamic.native, self.dynamic.contract, self.dynamic.cp):
            need(Path(module.__file__).resolve().is_relative_to((self.project / "src").resolve()),
                 "Admission imports must come from the exact sealed source tree")
        from hpc_forest.codex_worker import RomeoFiles
        import hpc_forest.codex_worker as source
        need(Path(source.__file__).resolve() == (self.project / "src/hpc_forest/codex_worker.py").resolve()
             and ref(Path(source.__file__).absolute())["sha256"] == ROMEO_SOURCE_SHA,
             "RomeoFiles must come from the sealed127 source, never editable history")
        self.RomeoFiles = RomeoFiles
        self.identity = self.capacity.load_venv_identity()
        need(Path(sys.executable).resolve() == Path(self.identity["launcher"]["path"]).resolve(),
             "ROOT must run this operator with the pinned venv launcher")

    def transfer_context(self, prepared):
        return self.RomeoFiles(Path(prepared["codex_config"]))

    def static_transfers(self, prepared):
        refs, _plan, aliases = self.dynamic.static_inputs(prepared["statics"])
        remote = document(prepared["statics_arm"])
        refs = {**refs, "subject_qualification": prepared["subject_qualification"]}
        remote = {**remote, "subject_qualification": self.dynamic.native.alias_reference(
            refs["subject_qualification"], aliases, platform="arm")}
        need(len(refs) == 9 and set(refs) == set(remote), "Existing nine exact transfer roles required")
        return [(key, local, remote[key]["path"]) for key, local in sorted(refs.items())]

    def check_prerequisites(self, request, prepared):
        self.builder.prerequisites(self.dynamic, self.reader, document(request["prerequisites"]),
                                   request["cell_key"], prepared["capacity_registry"])

    def check_unit_input(self, request, unit, prepared, journal):
        """Exercise the unchanged helper's REF3 reader locally before any MCP action."""
        config = document(unit["bootstrap_input"])
        refs, _plan, _aliases = self.dynamic.static_inputs(prepared["statics"])
        helper = self.bootstrap.load_helper((self.builder.BOOTSTRAP / "sealed-bootstrap-helper.py").absolute())
        self.bootstrap.validate_input(helper, config, checked(refs["plan"]).read_bytes())
        prior = document(request["prerequisites"])
        gate = config["first_batch_gate"]
        need(type(gate) is dict and set(gate) == {"path", "sha256", "bytes"}
             and {key: gate[key] for key in ("path", "sha256")} == prior["gate_arm"],
             "Materialized gate must be the actual bounded ARM REF3, never historical REF2")
        # Only substitute the received local spelling to exercise the very same reader.
        # The serialized ARM input and its path/SHA/bytes are never rewritten.
        local = prior["first_batch_extension_gate"]
        need(local["sha256"] == gate["sha256"], "Received gate identity differs")
        helper.read_ref({"path": str(checked(local)), "sha256": gate["sha256"], "bytes": gate["bytes"]})
        journal.record("SEALED_HELPER_GATE_REF3_CHECKED", bootstrap_input=unit["bootstrap_input"],
                       arm_gate=gate, received_local_gate=local, helper_sha256=self.builder.BOOT_PINS["sealed-bootstrap-helper.py"])

    def observe_cli(self, request, output):
        return self.dynamic.probe_cli(request["cli_executable"], request["skill_roots"], output)

    def build(self, input_ref):
        return self.builder.build(input_ref)

    def assemble(self, input_ref, journal):
        # The full CIM census and maximum-four reservation remain inside this producer's lock.
        delivery = Path(self.dynamic.__file__).parent
        local_copy = write(journal.output / "dynamic-input.json", checked(input_ref).read_bytes())
        relative = os.path.relpath(local_copy["path"], delivery)
        argv = [self.identity["launcher"]["path"], "-B", "dynamic_admission.py", "assemble", "--input", relative]
        need(all("hpc-forest" not in item.casefold() for item in argv), "Neutral relative assembler argv required")
        journal.record("ASSEMBLE_INTENT", argv=argv, cwd=str(delivery), input=local_copy)
        done = subprocess.run(argv, cwd=delivery, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                              capture_output=True, timeout=180, check=False,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        stdout = write(journal.output / "assemble.stdout", done.stdout)
        stderr = write(journal.output / "assemble.stderr", done.stderr)
        journal.record("ASSEMBLE_RETURNED", returncode=done.returncode, stdout=stdout, stderr=stderr)
        need(done.returncode == 0, "Admission assembly failed; no retry or capacity cleanup here")
        result = parse(done.stdout)
        checked(result)
        return result

    def launch_worker(self, worker_ref, binding, journal):
        worker = document(worker_ref)
        need(worker["persistent"] is True and "--once" not in worker["argv"], "Exact persistent producer argv required")
        need(Path(worker["cwd"]).resolve() == self.project.resolve()
             and worker["environment"] == {"PYTHONPATH": str(self.project / "src")}, "Sealed worker cwd/environment required")
        checked(worker_ref)
        stdout_path, stderr_path = journal.output / "worker.stdout", journal.output / "worker.stderr"
        journal.record("WORKER_LAUNCH_INTENT", worker=worker_ref, binding=binding)
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            started = time.time()
            process = subprocess.Popen(worker["argv"], cwd=worker["cwd"],
                env={**os.environ, **worker["environment"], "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        launch = write(journal.output / "WORKER-LAUNCH.json", {"schema": "hpc-forest-root-owned-native-worker-launch-v1",
            "session_id": binding["session_id"], "job_id": binding["job_id"], "started_at": started,
            "process_id": process.pid, "reviewed_argv": worker_ref, "hidden": True,
            "stdout": str(stdout_path), "stderr": str(stderr_path)})
        journal.record("WORKER_LAUNCHED", receipt=launch)
        # A venv redirector may briefly precede its base child; observe only, never restart it.
        for index in range(10):
            census_raw = self.capacity.collect_windows()
            census = write(journal.output / f"worker-census/{index:02d}.json", census_raw)
            now = time.time()
            analysis = self.capacity.classify_processes(parse(census_raw), now, venv_identity=self.identity)
            groups = [group for group in analysis["private_native_groups"]
                      if group[0]["session_id"] == binding["session_id"]]
            if len(groups) == 1 and len(groups[0]) == 2:
                processes = [{key: p[key] for key in self.capacity.PROCESS_FIELDS} for p in groups[0]]
                need(processes[1]["ProcessId"] == process.pid and processes[0]["ParentProcessId"] == process.pid,
                     "Observed pair is not the exact launched base child and venv parent")
                need(all(p["CommandLine"] == subprocess.list2cmdline(worker["argv"])
                         and self.capacity.creation_time(p["CreationDate"]) >= started for p in processes),
                     "Owned pair must preserve this launch's exact argv and fresh creation identities")
                receipt = write(journal.output / "OWNED-WORKER-IDENTITY.json", {
                    "schema": "hpc-forest-native-owned-worker-identity-v1", "verified": True,
                    "ownership_established": True, "session_id": binding["session_id"],
                    "channel": groups[0][0]["channel"], "processes": processes})
                journal.record("PERSISTENT_WORKER_IDENTIFIED", receipt=receipt, full_census=census)
                return receipt
            time.sleep(0.25)
        raise ValueError("Worker launched but exact two-process identity not observed; stop without restart/kill")


async def scp_readback(mcp, local, remote, *, label):
    """Verify arbitrary bytes through a fresh primary SCP receipt, never UTF-8 conversion."""
    path = checked(local)
    target = mcp.journal.output / "scp-upload-readbacks" / (hashlib.sha256(remote.encode()).hexdigest() + ".bin")
    target.parent.mkdir(parents=True, exist_ok=True)
    result, observed = await mcp.call("download_from_romeo", {
        "remote_path": remote, "local_path": str(target), "recursive": False, "verify": True})
    received = ref(target)
    need(received["sha256"] == local["sha256"] and target.stat().st_size == path.stat().st_size
         and target.read_bytes() == path.read_bytes()
         and result.get("transport") == "scp" and result.get("verifie") is True
         and result.get("downloaded") == remote and result.get("to") == str(target)
         and result.get("bytes") == path.stat().st_size
         and result.get("empreinte_locale") == result.get("empreinte_distante") == local["sha256"]
         and ("remote_sha256" not in result or result["remote_sha256"] == local["sha256"]),
         "Exact fresh SCP readback required: " + label)
    mcp.journal.record("UPLOADED_BYTES_SCP_RECEIVED", remote=remote, source=local,
                       received=received, primary=observed)
    return observed, received


async def upload_checked(mcp, local, remote, *, label):
    path = checked(local)
    result, receipt = await mcp.call("upload_to_romeo", {"local_path": str(path), "remote_path": remote, "verify": True})
    need(result.get("transport") == "scp" and result.get("verifie") is True
         and result.get("empreinte_locale") == result.get("empreinte_distante") == local["sha256"]
         and result.get("bytes") == path.stat().st_size and result.get("to") == remote,
         "Exact SCP upload required: " + label)
    observed, _received = await scp_readback(mcp, local, remote, label=label)
    return receipt, observed


async def bootstrap_one(request, unit, mcp, journal):
    manifest = document(unit["upload_manifest"])
    remote_stage = PurePosixPath(manifest["remote_stage"])
    stage = journal.output / "BOOTSTRAP-STAGE" / remote_stage.name
    stage.mkdir(parents=True, exist_ok=False)
    staged = []
    for member in manifest["members"]:
        remote = PurePosixPath(member["remote"]["path"])
        need(remote.parent == remote_stage, "Bootstrap member must keep its exact stage basename")
        local = {key: member["local"][key] for key in ("path", "sha256")}
        item = write(stage / remote.name, checked(local).read_bytes())
        need(item["sha256"] == member["remote"]["sha256"], "Bootstrap staged bytes changed")
        staged.append((item, str(remote)))
    # The parent already exists. SCP creates this exact directory basename.
    # Directory verifie:false is not an integrity proof; each file is received below.
    directory, directory_raw = await mcp.call("upload_to_romeo", {
        "local_path": str(stage), "remote_path": str(remote_stage.parent), "verify": True})
    journal.record("BOOTSTRAP_DIRECTORY_UPLOADED_UNVERIFIED", primary=directory_raw,
                   directory_verifie=directory.get("verifie"), integrity_established=False)
    for local, remote in staged:
        await scp_readback(mcp, local, remote, label="bootstrap staged file")
    arguments = document(unit["job_prepare_arguments"])
    need(arguments["command"].encode("utf8") == checked(unit["job_body"]).read_bytes(), "Reviewed body differs from job args")
    plan, plan_ref = await mcp.call("job_prepare", arguments)
    need(plan.get("submitted") is False and plan.get("submittable") is True
         and isinstance(plan.get("plan_id"), str) and plan.get("plan_sha256"), "One submittable prepared plan required")
    intent = write(journal.output / "SUBMISSION-INTENT.json", {
        "schema": "hpc-forest-matrix15-operator-submission-intent-v1", "cell_key": request["cell_key"],
        "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"], "plan_observation": plan_ref,
        "unit_preparation": request["unit_preparation"], "job_body": unit["job_body"],
        "one_submission_only": True, "automatic_retry": False, "recorded_at": time.time()})
    journal.record("SUBMISSION_INTENT_PERSISTED", intent=intent)
    submitted, submit_ref = await mcp.call("job_submit", {"plan_id": plan["plan_id"], "confirm": True})
    need(submitted.get("submitted") is True and submitted.get("submission_observed") is True
         and submitted.get("plan_id") == plan["plan_id"] and submitted.get("plan_sha256") == plan["plan_sha256"],
         "Exact one-plan submission observation required; uncertainty stops without resubmission")
    binding = {**unit["binding_without_job_id"], "job_id": submitted["job_id"]}
    journal.record("BOOTSTRAP_SUBMITTED", binding=binding, receipt=submit_ref)
    return binding


async def poll_zero_marker(request, binding, mcp, journal):
    remote = binding["remote_root"] + "-admission/ZERO-MODEL-MARKER.json"
    for _ in range(request["marker_max_polls"]):
        status, status_ref = await mcp.call("job_status", {"job_id": binding["job_id"]})
        need(status.get("job_id") == binding["job_id"], "Original job identity changed")
        need(status.get("finished") is False, "Bootstrap became terminal; stop and preserve it")
        if status.get("state") == "RUNNING":
            readback, raw = await mcp.call("read_remote_file", {"path": remote, "offset": 1, "limit": 300, "max_chars": 50000}, allow_missing=True)
            if readback is not None:
                need(readback.get("truncated") is False, "Whole zero-model marker required")
                marker_ref = write(journal.output / "ZERO-MODEL-MARKER.json", readback["content"].encode("utf8"))
                journal.record("ZERO_MODEL_MARKER_RECEIVED", marker=marker_ref, readback=raw, job_status=status_ref)
                return marker_ref, raw, status_ref
        await asyncio.sleep(request["marker_poll_seconds"])
    raise ValueError("Zero-model marker poll bound reached; no resubmission")


async def receive_fresh_proofs(sources, prepared, mcp, journal):
    semaphore = asyncio.Semaphore(6)
    async def one(key, local, remote):
        need(remote.startswith("/"), "Exact predeclared ARM alias required")
        target = journal.output / "fresh-scp" / (key + ".bin")
        target.parent.mkdir(exist_ok=True)
        async with semaphore:
            result, raw = await mcp.call("download_from_romeo", {
                "remote_path": remote, "local_path": str(target), "verify": True, "recursive": False})
        received = ref(target)
        need(received["sha256"] == local["sha256"] and checked(local).stat().st_size == target.stat().st_size,
             "Fresh SCP bytes differ from immutable local source")
        need(result.get("transport") == "scp" and result.get("verifie") is True
             and result.get("empreinte_locale") == result.get("empreinte_distante") == local["sha256"],
             "Fresh SCP hashes unverified")
        return key, {"local": local, "remote_path": remote, "sha256": local["sha256"],
                     "bytes": target.stat().st_size, "raw": raw, "readback": received}
    results = await asyncio.gather(*(one(*item) for item in sources.static_transfers(prepared)), return_exceptions=True)
    # All already-started reads are allowed to persist their receipts before a failure stops the unit.
    errors = [value for value in results if isinstance(value, BaseException)]
    need(not errors, "Fresh transfer failure; preserve all received receipts and stop: " + str(errors[:1]))
    transfers = dict(results)
    journal.record("NINE_FRESH_PROOFS_RECEIVED", transfers=write(journal.output / "FRESH-TRANSFERS.json", transfers))
    return transfers


def build_authorization(request, prepared, marker, marker_raw, status, transfers, sources, journal):
    cli = sources.observe_cli(request, journal.output / "cli-observation")
    journal.record("CLI_METADATA_OBSERVED", observation=cli)
    input_value = {"schema": "hpc-forest-matrix15-extension-operation-builder-input-v1", "mode": "BUILD",
        "prepared": request["extension_prepared"], "marker": marker, "marker_readback": marker_raw,
        "job_status": status, "transfers": transfers, "cli_observation": cli,
        "owned_worker_receipts": request["owned_worker_receipts"],
        "output_directory": str(Path(request["extension_prepared"]["path"]).parent.with_name(
            Path(request["extension_prepared"]["path"]).parent.name + "-binding"))}
    builder_input = write(journal.output / "INPUT-BUILDER.json", input_value)
    dynamic_input = sources.build(builder_input)
    journal.record("DYNAMIC_INPUT_BUILT", input=dynamic_input)
    authorization = sources.assemble(dynamic_input, journal)
    journal.record("AUTHORIZATION_ASSEMBLED", authorization=authorization)
    return authorization


async def transfer_authorization(authorization, binding, request, mcp, journal):
    directory = Path(authorization["path"]).parent
    pending = document(ref(directory / "ARM-TRANSFER-PENDING.json"))
    members = pending["members"]
    arm_authorization, commit = arm_authorization_members(pending, binding)
    # Preserve each basename when the SCP tool treats an existing remote directory as a target.
    ordered = [member for member in members if member is not commit] + [commit]
    for member in ordered:
        remote = member["remote"]["path"]
        staged = write(journal.output / "STAGE" / PurePosixPath(remote).name,
                       checked({k: member["local"][k] for k in ("path", "sha256")}).read_bytes())
        need(staged["sha256"] == member["remote"]["sha256"], "ARM member changed before transfer")
        await upload_checked(mcp, staged, remote, label="authorization member")
        journal.record("AUTHORIZATION_MEMBER_RECEIVED", remote=member["remote"], commit=member is commit)
    remote = binding["remote_root"] + "-admission/authorization-accepted.json"
    for _ in range(request["acceptance_max_polls"]):
        accepted, observed = await mcp.call("read_remote_file", {
            "path": remote, "offset": 1, "limit": 300, "max_chars": 64000}, allow_missing=True)
        if accepted is not None:
            need(accepted.get("truncated") is False, "Whole admission acceptance required")
            actual = parse(accepted["content"])
            need(actual.get("admission_accepted") is True and actual.get("runtime_validated") is True
                 and actual.get("authorization_sha256") == arm_authorization["remote"]["sha256"],
                 "Exact actual ARM authorization acceptance required")
            received = write(journal.output / "authorization-accepted.json", accepted["content"].encode("utf8"))
            journal.record("ARM_AUTHORIZATION_ACCEPTED", receipt=received, readback=observed)
            return ref(directory / "WORKER-ARGV.json")
        await asyncio.sleep(request["marker_poll_seconds"])
    raise ValueError("ARM acceptance not observed; no worker launch or authorization replay")


def arm_authorization_members(pending, binding):
    """Resolve host-specific authorization from its exact ARM member and commit."""
    admission = binding["remote_root"] + "-admission/"
    auth = [m for m in pending["members"] if m["remote"]["path"] == admission + "authorization.json"]
    commit = [m for m in pending["members"] if m["remote"]["path"] == admission + "authorization.sha256.json"]
    need(len(auth) == len(commit) == 1, "Exactly one ARM authorization and last commit member required")
    auth, commit = auth[0], commit[0]
    if "authorization" in pending:
        need(pending["authorization"] == auth["remote"], "ARM authorization projection differs from its actual member")
    marker = document({key: commit["local"][key] for key in ("path", "sha256")})
    local_auth = {key: auth["local"][key] for key in ("path", "sha256")}
    need(local_auth["sha256"] == auth["remote"]["sha256"]
         and marker == {"authorization": auth["remote"]["path"], "sha256": auth["remote"]["sha256"],
                        "bytes": checked(local_auth).stat().st_size}, "ARM commit does not bind its exact host authorization")
    return auth, commit


def prepare(output, request_ref=None):
    journal = Journal(output)
    try:
        if request_ref is not None:
            checked(request_ref)
        receipt = write(journal.output / "PREPARATION.json", {
            "schema": "hpc-forest-matrix15-local-operator-prepared-v1", "mode": "PREPARE", "verified": False,
            "input": request_ref, "network_calls": 0, "native_model_calls": 0, "jobs_submitted": 0,
            "registry_modified": False, "worker_started": False, "automatic_extension": False,
            "execute_one_requires_root_ship": True,
            "next_stage_root_controls": ["first-batch audit", "first-batch release", "reservation closure"]})
        journal.record("PREPARE_ONLY", receipt=receipt)
        return receipt
    finally:
        journal.close()


async def execute_one(output, request_ref, review_ref, *, sources_factory=Sources):
    request, unit, prepared = review_execution(request_ref, review_ref)
    journal = Journal(output)
    try:
        journal.record("ROOT_EXECUTE_ONE_APPROVED", input=request_ref, review=review_ref, cell_key=request["cell_key"])
        sources = sources_factory()
        need(request["cell_key"] in sources.dynamic.contract.REGISTERED_CELLS, "Exact registered cell required")
        sources.check_prerequisites(request, prepared)
        sources.check_unit_input(request, unit, prepared, journal)
        consume_unit(request, unit, request_ref, review_ref, journal)
        async with sources.transfer_context(prepared) as transfer:
            mcp = PrimaryMCP(transfer, journal)
            binding = await bootstrap_one(request, unit, mcp, journal)
            marker, marker_raw, status = await poll_zero_marker(request, binding, mcp, journal)
            transfers = await receive_fresh_proofs(sources, prepared, mcp, journal)
            authorization = build_authorization(request, prepared, marker, marker_raw, status, transfers, sources, journal)
            worker_ref = await transfer_authorization(authorization, binding, request, mcp, journal)
        owned = sources.launch_worker(worker_ref, binding, journal)
        journal.record("EXECUTE_ONE_HANDOFF", binding=binding, owned_worker_receipt=owned,
                       first_batch_audit_performed=False, first_batch_release_performed=False,
                       reservation_closed=False, automatic_extension=False)
        return owned
    except BaseException as error:
        journal.record("STOP_UNCERTAIN_OR_FAILED", exception_type=type(error).__name__, error=str(error),
                       automatic_retry=False, cleanup_or_kill_performed=False)
        raise
    finally:
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--input-sha256")
    parser.add_argument("--execute-one", action="store_true")
    parser.add_argument("--root-review", type=Path)
    parser.add_argument("--root-review-sha256")
    args = parser.parse_args(argv)
    need(bool(args.input) == bool(args.input_sha256), "Input path and SHA must be paired")
    request = {"path": str(args.input.absolute()), "sha256": args.input_sha256} if args.input else None
    if not args.execute_one:
        result = prepare(args.output.absolute(), request)
    else:
        need(request is not None and args.root_review is not None and args.root_review_sha256,
             "Explicit --execute-one and ROOT review reference required")
        need(all("hpc-forest" not in item.casefold() for item in (argv if argv is not None else sys.argv)),
             "Run from the operator directory with neutral relative input/review/output arguments")
        review = {"path": str(args.root_review.absolute()), "sha256": args.root_review_sha256}
        result = asyncio.run(execute_one(args.output.absolute(), request, review))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
