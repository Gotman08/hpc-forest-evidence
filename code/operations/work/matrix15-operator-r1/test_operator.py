"""NEUTRAL mocks only: never connect, submit, reserve, probe a CLI or start a worker."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bounded_operator", HERE / "operator.py")
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)


class Tests(unittest.TestCase):
    def setUp(self):
        self.folder = HERE / "tests-NEUTRAL" / uuid.uuid4().hex
        self.folder.mkdir(parents=True)

    def test_default_prepare_does_not_construct_runtime_or_call_any_action(self):
        with patch.object(op, "Sources", side_effect=AssertionError("No producer import")), \
             patch.object(op, "execute_one", side_effect=AssertionError("No execution")):
            op.main(["--output", str(self.folder / "prepare")])
        value = json.loads((self.folder / "prepare/PREPARATION.json").read_text())
        self.assertEqual(value["mode"], "PREPARE")
        self.assertIs(value["verified"], False)
        for key in ("network_calls", "native_model_calls", "jobs_submitted"):
            self.assertEqual(value[key], 0)
        self.assertFalse(value["registry_modified"] or value["worker_started"])

    def test_execute_flag_without_root_review_cannot_construct_sources(self):
        with patch.object(op, "Sources", side_effect=AssertionError("Not authorized")):
            with self.assertRaises(ValueError):
                op.main(["--output", str(self.folder / "run"), "--execute-one"])
        self.assertFalse((self.folder / "run").exists())

    def test_journal_is_exclusive_and_durable_no_resume(self):
        journal = op.Journal(self.folder / "run")
        journal.record("NEUTRAL_INTENT", plan_id="mock-plan")
        journal.close()
        self.assertEqual(json.loads(journal.path.read_text())["state"], "NEUTRAL_INTENT")
        with self.assertRaises(FileExistsError):
            op.Journal(self.folder / "run")

    def test_full_sdk_response_and_aliases_are_preserved(self):
        raw = {"structuredContent": {"ok": True}, "isError": False,
               "_meta": {"NEUTRAL": True}, "content": [{"type": "text", "text": "unchanged"},
               {"type": "resource_link", "uri": "NEUTRAL://example", "name": "keep"}]}
        calls = []
        class Result:
            def model_dump(self, **kwargs):
                calls.append(kwargs)
                return raw
        class Session:
            async def call_tool(self, name, arguments):
                return Result()
        journal = op.Journal(self.folder / "mcp")
        try:
            result, observed = asyncio.run(op.PrimaryMCP(SimpleNamespace(session=Session()), journal).call(
                "job_status", {"job_id": "NEUTRAL"}))
        finally:
            journal.close()
        self.assertEqual(op.document(observed)["response"], raw)
        self.assertEqual(calls, [{"mode": "json", "by_alias": True}])
        states = [json.loads(line)["state"] for line in journal.path.read_text().splitlines()]
        self.assertEqual(states, ["MCP_INTENT", "MCP_RECEIVED"])

    def test_uncertain_submit_has_persisted_intent_and_is_not_retried(self):
        journal = op.Journal(self.folder / "submit")
        body = op.write(journal.output / "body.sh", b"NEUTRAL body\n")
        args = op.write(journal.output / "args.json", {"command": "NEUTRAL body\n"})
        manifest = op.write(journal.output / "manifest.json", {"remote_stage": "/NEUTRAL/inputs",
            "members": [{"local": body, "remote": {"path": "/NEUTRAL/inputs/body.sh", "sha256": body["sha256"]}}]})
        names = []
        class MCP:
            def __init__(self):
                self.journal = journal
            async def call(self, name, arguments):
                names.append(name)
                if name == "upload_to_romeo":
                    if not Path(arguments["local_path"]).is_dir() or arguments["remote_path"] != "/NEUTRAL":
                        raise AssertionError("Initial upload must create the exact new directory from its existing parent")
                    return {"ok": True, "verifie": False}, body
                if name == "download_from_romeo":
                    Path(arguments["local_path"]).write_bytes(b"NEUTRAL body\n")
                    return {"downloaded": arguments["remote_path"], "to": arguments["local_path"],
                        "transport": "scp", "verifie": True, "bytes": len(b"NEUTRAL body\n"),
                        "empreinte_locale": body["sha256"], "empreinte_distante": body["sha256"]}, body
                if name == "job_prepare":
                    return {"submitted": False, "submittable": True, "plan_id": "NEUTRAL-plan",
                            "plan_sha256": "a" * 64}, body
                self.assert_intent = (journal.output / "SUBMISSION-INTENT.json").is_file()
                if not self.assert_intent:
                    raise AssertionError("Intent missing before submit")
                raise TimeoutError("NEUTRAL uncertain submit")
        try:
            with self.assertRaises(TimeoutError):
                asyncio.run(op.bootstrap_one({"cell_key": "NEUTRAL", "unit_preparation": body},
                    {"upload_manifest": manifest, "job_prepare_arguments": args, "job_body": body}, MCP(), journal))
        finally:
            journal.close()
        self.assertEqual(names, ["upload_to_romeo", "download_from_romeo", "job_prepare", "job_submit"])
        self.assertTrue((journal.output / "SUBMISSION-INTENT.json").is_file())

    def test_commit_is_last_and_staging_keeps_exact_remote_basenames(self):
        journal = op.Journal(self.folder / "transfer")
        dynamic = journal.output / "NEUTRAL-dynamic"
        dynamic.mkdir()
        auth = op.write(dynamic / "authorization.json", {"NEUTRAL": True})
        members = []
        for name in ("authorization.sha256.json", "proof.json", "authorization.json"):
            content = {"authorization": "/NEUTRAL-admission/authorization.json", "sha256": auth["sha256"],
                       "bytes": Path(auth["path"]).stat().st_size} if name == "authorization.sha256.json" else {"NEUTRAL": name}
            local = auth if name == "authorization.json" else op.write(dynamic / name, content)
            members.append({"local": local, "remote": {"path": "/NEUTRAL-admission/" + name,
                                                        "sha256": local["sha256"]}})
        op.write(dynamic / "ARM-TRANSFER-PENDING.json", {"members": members, "authorization": members[-1]["remote"]})
        op.write(dynamic / "WORKER-ARGV.json", {"argv": ["NEUTRAL"], "persistent": True})
        uploads = []
        async def upload(_mcp, local, remote, **kwargs):
            uploads.append((Path(local["path"]).name, remote))
            return None, None
        class MCP:
            async def call(self, name, arguments, **kwargs):
                if name != "read_remote_file" or arguments["max_chars"] > 64000 or arguments["limit"] != 300:
                    raise AssertionError("Real bounded accepted-receipt API arguments required")
                return {"truncated": False, "content": json.dumps({"admission_accepted": True,
                    "runtime_validated": True, "authorization_sha256": auth["sha256"]})}, auth
        try:
            with patch.object(op, "upload_checked", upload):
                asyncio.run(op.transfer_authorization(auth, {"remote_root": "/NEUTRAL"},
                    {"acceptance_max_polls": 1}, MCP(), journal))
        finally:
            journal.close()
        self.assertEqual([Path(remote).name for _, remote in uploads], [name for name, _ in uploads])
        self.assertEqual(uploads[-1][0], "authorization.sha256.json")
        self.assertEqual(len(uploads), 3)

    def test_binary_and_large_json_uploads_are_received_by_scp_not_text(self):
        journal = op.Journal(self.folder / "arbitrary-bytes")
        blobs = {"NEUTRAL-binary.gz": bytes(range(256)) * 23000,
                 "NEUTRAL-large-json.json": op.encoded({"NEUTRAL": "x" * 2_000_000})}
        sources = {"/NEUTRAL/" + name: op.write(journal.output / name, raw) for name, raw in blobs.items()}
        class MCP:
            def __init__(self):
                self.journal = journal
            async def call(self, name, arguments):
                if name == "read_remote_file":
                    raise AssertionError("Uploaded artifact bytes cannot use a text readback")
                local = sources[arguments["remote_path"]]
                raw = Path(local["path"]).read_bytes()
                common = {"transport": "scp", "verifie": True, "bytes": len(raw),
                          "empreinte_locale": local["sha256"], "empreinte_distante": local["sha256"],
                          "remote_sha256": local["sha256"]}
                if name == "upload_to_romeo":
                    return {**common, "to": arguments["remote_path"]}, local
                Path(arguments["local_path"]).write_bytes(raw)
                return {**common, "downloaded": arguments["remote_path"], "to": arguments["local_path"]}, local
        try:
            for remote, local in sources.items():
                asyncio.run(op.upload_checked(MCP(), local, remote, label="NEUTRAL fixture bytes"))
        finally:
            journal.close()
        self.assertEqual(len(list((journal.output / "scp-upload-readbacks").glob("*.bin"))), 2)

    def test_actual_frozen_pending_metadata_resolves_arm_member_and_commit(self):
        pending_path = op.BASE / "outputs/HPC-Forest-Matrice15-Execution-root-01/admission-windows-r2/ARM-TRANSFER-PENDING.json"
        pending = json.loads(pending_path.read_bytes())
        target = pending["authorization"]["path"]
        root = target.removesuffix("-admission/authorization.json")
        authorization, commit = op.arm_authorization_members(pending, {"remote_root": root})
        self.assertEqual(len(pending["members"]), 43)
        self.assertEqual(sum(member["bytes"] for member in pending["members"]), 6588597)
        self.assertEqual(authorization["remote"], pending["authorization"])
        self.assertNotEqual(authorization["remote"]["sha256"], pending["source_authorization"]["sha256"])
        self.assertTrue(commit["remote"]["path"].endswith("/authorization.sha256.json"))
        without_convenience_key = {key: value for key, value in pending.items() if key != "authorization"}
        self.assertEqual(op.arm_authorization_members(without_convenience_key, {"remote_root": root}), (authorization, commit))
        wrong_projection = {**pending, "authorization": pending["source_authorization"]}
        with self.assertRaises(ValueError):
            op.arm_authorization_members(wrong_projection, {"remote_root": root})

    def test_fresh_nine_reads_are_bounded_and_all_receipts_finish(self):
        journal = op.Journal(self.folder / "receive")
        original = op.write(journal.output / "immutable.bin", b"NEUTRAL bytes")
        active, maximum, finished = 0, 0, []
        class MCP:
            async def call(self, name, arguments):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.001)
                Path(arguments["local_path"]).write_bytes(b"NEUTRAL bytes")
                active -= 1
                finished.append(arguments["remote_path"])
                return {"transport": "scp", "verifie": True, "empreinte_locale": original["sha256"],
                        "empreinte_distante": original["sha256"]}, original
        source = SimpleNamespace(static_transfers=lambda _prepared: [
            (str(index), original, "/NEUTRAL/" + str(index)) for index in range(9)])
        try:
            value = asyncio.run(op.receive_fresh_proofs(source, {}, MCP(), journal))
        finally:
            journal.close()
        self.assertEqual(len(value), 9)
        self.assertEqual(len(finished), 9)
        self.assertLessEqual(maximum, 6)
        self.assertEqual(maximum, 6)

    def test_execution_failure_stops_without_later_phases_or_cleanup(self):
        events = []
        source = SimpleNamespace(dynamic=SimpleNamespace(contract=SimpleNamespace(REGISTERED_CELLS={"NEUTRAL": {}})),
            check_prerequisites=lambda *args: events.append("prerequisites"),
            check_unit_input=lambda *args: events.append("helper_ref3"))
        class Context:
            async def __aenter__(self):
                return SimpleNamespace(session=None)
            async def __aexit__(self, *args):
                events.append("relay_closed")
        source.transfer_context = lambda _: Context()
        async def fail(*args):
            events.append("bootstrap")
            raise TimeoutError("NEUTRAL uncertain plan")
        with patch.object(op, "review_execution", return_value=({"cell_key": "NEUTRAL", "unit_preparation": {}},
                {"binding_without_job_id": {"session_id": "NEUTRAL"}}, {})), \
             patch.object(op, "CLAIMS", self.folder / "claims"), \
             patch.object(op, "bootstrap_one", fail), \
             patch.object(op, "poll_zero_marker", side_effect=AssertionError("No later phase")):
            with self.assertRaises(TimeoutError):
                asyncio.run(op.execute_one(self.folder / "stop", {}, {}, sources_factory=lambda: source))
        states = [json.loads(line) for line in (self.folder / "stop/STATE.jsonl").read_text().splitlines()]
        self.assertEqual(states[-1]["state"], "STOP_UNCERTAIN_OR_FAILED")
        self.assertFalse(states[-1]["automatic_retry"] or states[-1]["cleanup_or_kill_performed"])
        self.assertEqual(events, ["prerequisites", "helper_ref3", "bootstrap", "relay_closed"])
        self.assertEqual(len(list((self.folder / "claims").glob("*.json"))), 1)

    def test_same_cell_cannot_be_replayed_with_another_output_or_preparation(self):
        first = op.Journal(self.folder / "one")
        second = op.Journal(self.folder / "two")
        request = {"cell_key": "NEUTRAL-cell", "unit_preparation": {"sha256": "a" * 64}}
        unit = {"binding_without_job_id": {"session_id": "NEUTRAL"}}
        try:
            with patch.object(op, "CLAIMS", self.folder / "claims"):
                claim = op.consume_unit(request, unit, {}, {}, first)
                with self.assertRaises(FileExistsError):
                    op.consume_unit({**request, "unit_preparation": {"sha256": "b" * 64}}, unit,
                                    {"sha256": "2" * 64}, {"sha256": "3" * 64}, second)
        finally:
            first.close()
            second.close()
        self.assertTrue(Path(claim["path"]).is_file())
        self.assertFalse(op.document(claim)["operator_may_remove_claim"])

    def test_two_concurrent_claims_for_same_cell_have_one_winner(self):
        first = op.Journal(self.folder / "race-one")
        second = op.Journal(self.folder / "race-two")
        request = {"cell_key": "NEUTRAL-race", "unit_preparation": {}}
        unit = {"binding_without_job_id": {"session_id": "NEUTRAL"}}
        def attempt(journal):
            try:
                return op.consume_unit(request, unit, {}, {}, journal)
            except FileExistsError:
                return None
        try:
            with patch.object(op, "CLAIMS", self.folder / "claims"), ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, (first, second)))
        finally:
            first.close()
            second.close()
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(len(list((self.folder / "claims").glob("*.json"))), 1)

    def test_mcp_open_failure_retains_claim_and_other_output_cannot_open_mcp(self):
        opened = []
        source = SimpleNamespace(dynamic=SimpleNamespace(contract=SimpleNamespace(REGISTERED_CELLS={"NEUTRAL": {}})),
            check_prerequisites=lambda *args: None, check_unit_input=lambda *args: None)
        class Context:
            async def __aenter__(self):
                opened.append(True)
                raise TimeoutError("NEUTRAL relay opening uncertain")
            async def __aexit__(self, *args):
                return False
        source.transfer_context = lambda _: Context()
        request = {"cell_key": "NEUTRAL", "unit_preparation": {}}
        unit = {"binding_without_job_id": {"session_id": "NEUTRAL"}}
        with patch.object(op, "review_execution", return_value=(request, unit, {})), \
             patch.object(op, "CLAIMS", self.folder / "claims"):
            with self.assertRaises(TimeoutError):
                asyncio.run(op.execute_one(self.folder / "relay-one", {}, {}, sources_factory=lambda: source))
            with self.assertRaises(FileExistsError):
                asyncio.run(op.execute_one(self.folder / "relay-two", {}, {}, sources_factory=lambda: source))
        self.assertEqual(len(opened), 1)
        self.assertEqual(len(list((self.folder / "claims").glob("*.json"))), 1)

    def test_ref2_preflight_failure_has_no_claim_or_mcp_open(self):
        def reject(*args):
            raise ValueError("NEUTRAL historical REF2")
        source = SimpleNamespace(dynamic=SimpleNamespace(contract=SimpleNamespace(REGISTERED_CELLS={"NEUTRAL": {}})),
            check_prerequisites=lambda *args: None, check_unit_input=reject,
            transfer_context=lambda _: (_ for _ in ()).throw(AssertionError("No MCP opening")))
        with patch.object(op, "review_execution", return_value=({"cell_key": "NEUTRAL"}, {}, {})), \
             patch.object(op, "CLAIMS", self.folder / "claims"):
            with self.assertRaisesRegex(ValueError, "REF2"):
                asyncio.run(op.execute_one(self.folder / "bad-ref2", {}, {}, sources_factory=lambda: source))
        self.assertFalse((self.folder / "claims").exists())

    def test_assembler_uses_relative_neutral_argv_and_persists_both_streams(self):
        journal = op.Journal(self.folder / "assemble")
        source = op.Sources.__new__(op.Sources)
        delivery = self.folder / "producer"
        delivery.mkdir()
        source.dynamic = SimpleNamespace(__file__=str(delivery / "dynamic_admission.py"))
        source.identity = {"launcher": {"path": "C:\\NEUTRAL\\python.exe"}}
        data = op.write(journal.output / "source-input.json", {"NEUTRAL": True})
        result = op.write(journal.output / "authorization.json", {"NEUTRAL": True})
        def run(argv, **kwargs):
            self.assertTrue(all("hpc-forest" not in part.casefold() for part in argv))
            self.assertFalse(Path(argv[-1]).is_absolute())
            self.assertEqual(kwargs["cwd"], delivery)
            return SimpleNamespace(returncode=0, stdout=op.encoded(result), stderr=b"")
        try:
            with patch.object(op.subprocess, "run", run):
                actual = source.assemble(data, journal)
        finally:
            journal.close()
        self.assertEqual(actual, result)
        self.assertTrue((journal.output / "assemble.stdout").is_file())
        self.assertTrue((journal.output / "assemble.stderr").is_file())

    def test_gate_ref3_uses_actual_sealed_helper_reader_before_any_action(self):
        journal = op.Journal(self.folder / "ref3")
        helper_path = op.BASE / "outputs/HPC-Forest-Matrice15-Bootstrap-Extension-Preparation-r3/lecteur/sealed-bootstrap-helper.py"
        helper = SimpleNamespace(__name__="NEUTRAL_helper", __file__=str(helper_path))
        # Source-only standard-library helper; its main is not entered.
        exec(compile(helper_path.read_bytes(), str(helper_path), "exec"), helper.__dict__)
        local = op.write(journal.output / "NEUTRAL-gate.json", b"N" * 3119)
        plan = op.write(journal.output / "NEUTRAL-plan.json", {})
        arm = {"path": "/NEUTRAL/gate.json", "sha256": local["sha256"]}
        prior = op.write(journal.output / "NEUTRAL-prior.json", {
            "gate_arm": arm, "first_batch_extension_gate": local})
        source = op.Sources.__new__(op.Sources)
        source.dynamic = SimpleNamespace(static_inputs=lambda _: ({"plan": plan}, {}, {}))
        source.bootstrap = SimpleNamespace(load_helper=lambda _: helper, validate_input=lambda *args: None)
        source.builder = SimpleNamespace(BOOTSTRAP=helper_path.parent,
            BOOT_PINS={"sealed-bootstrap-helper.py": op.ref(helper_path)["sha256"]})
        try:
            for index, gate in enumerate((arm, {**arm, "bytes": 3118}, {**arm, "bytes": 3119})):
                config = op.write(journal.output / f"NEUTRAL-input-{index}.json", {"first_batch_gate": gate})
                call = lambda: source.check_unit_input({"prerequisites": prior}, {"bootstrap_input": config},
                                                       {"statics": None}, journal)
                if index < 2:
                    with self.assertRaises(ValueError):
                        call()
                else:
                    call()
        finally:
            journal.close()
        states = [json.loads(line)["state"] for line in journal.path.read_text().splitlines()]
        self.assertEqual(states, ["SEALED_HELPER_GATE_REF3_CHECKED"])


if __name__ == "__main__":
    unittest.main()
