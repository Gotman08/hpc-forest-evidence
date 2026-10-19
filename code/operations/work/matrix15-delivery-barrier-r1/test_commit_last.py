"""Offline transfer fakes only; no subprocess, server, CLI, sleep or model."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("commit_last.py")
SPEC = importlib.util.spec_from_file_location("commit_last_under_test", SOURCE)
barrier_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(barrier_module)
CommitLastTransfers, BarrierError = barrier_module.CommitLastTransfers, barrier_module.BarrierError
NONCE = "a" * 32
POLICY = "b" * 64


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf8")
    return path


class FakeVerifiedTransfers:
    def __init__(self):
        self.calls, self.seconds, self.fail_suffix, self.corrupt = [], 0, None, None

    async def upload(self, local, remote):
        # The fake advances only virtual time, including a metadata delay >15 s.
        if remote.endswith((".codex.jsonl.json", ".delivered.json")):
            self.seconds += 20
        self.calls.append({"local": str(local), "remote": remote, "at_virtual_second": self.seconds})
        if self.fail_suffix and remote.endswith(self.fail_suffix):
            raise OSError("Simulated metadata transfer failure")
        raw = local.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        payload = {"ok": True, "verifie": True, "sent": str(local.resolve()), "to": remote,
                   "bytes": len(raw), "transport": "scp", "remote_sha256": digest,
                   "empreinte_locale": digest, "empreinte_distante": digest}
        if self.corrupt:
            self.corrupt(payload)
        return payload


class CommitLastTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="offline-delivery-barrier-", dir=SOURCE.parent)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(SOURCE.parent.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / NONCE
        self.local.mkdir()
        self.binding = {"scope_id": "hpc-forest-matrix15-native-max-r2",
                        "cell_key": "forest-r2/gpt-6-astra/max/2023-count/seed-23",
                        "subject_id": "2023-count", "model": "gpt-6-astra", "effort": "max",
                        "session_id": "c" * 32, "job_id": "12345", "remote_root": "/fresh/cell-c",
                        "source_zip_sha256": "1" * 64, "plan_sha256": "2" * 64,
                        "preparation_manifest_sha256": "3" * 64, "r1_contract_sha256": "4" * 64}
        self.channel = "/fresh/cell-c/results-12345/mailbox"
        self.transfer = FakeVerifiedTransfers()
        self.barrier = CommitLastTransfers(self.transfer, self.channel, self.binding, policy_sha256=POLICY)
        self.response = write(self.local / "response.json", {"nonce": NONCE, "session_id": self.binding["session_id"],
                              "model": self.binding["model"], "reasoning_effort": "max", "request_sha256": "d" * 64,
                              "infrastructure_error": False})
        self.response_digest = hashlib.sha256(self.response.read_bytes()).hexdigest()
        self.ready = write(self.local / "response-ready.json", {"sha256": self.response_digest, "bytes": self.response.stat().st_size})
        self.invocation = self.projection("invocation", {"model": self.binding["model"], "reasoning_effort": "max",
                                            "request_sha256": "d" * 64, "source_execution_allowed": False})
        self.process = self.projection("process", {"returncode": 0, "timed_out": False})
        self.delivered = write(self.local / "delivered.json", {**self.binding, "request_sha256": "d" * 64,
                               "response_sha256": self.response_digest, "delivered_at": 123.0})

    def projection(self, kind, record):
        name = "invocation.json" if kind == "invocation" else "codex.jsonl.json"
        return write(self.local / (name + ".arm-projection.json"), {
            "schema": "hpc-forest-r2e-private-cli-metadata-projection-v1", "kind": kind,
            "record_without_private_argv": record, "argv_public": ["fixed-codex.exe", "exec"],
            "private_record_sha256": ("e" if kind == "invocation" else "f") * 64,
            "private_argv_sha256": "5" * 64, "private_skill_override_sha256": "6" * 64,
            "task_cli_policy_sha256": POLICY, "private_skill_path_count": 2,
            "private_review_required": True, "private_argv_verified": False,
            "projection_is_executable": False, "raw_record_exported": False})

    def destination(self, kind):
        directory, suffix = {"response": ("responses", "response.json"), "ready": ("responses", "ready.json"),
                             "invocation": ("logs", "invocation.json"), "process": ("logs", "codex.jsonl.json"),
                             "delivered": ("logs", "delivered.json")}[kind]
        return self.channel + "/" + directory + "/" + NONCE + "." + suffix

    async def before_commit(self):
        invocation = await self.barrier.upload(self.invocation, self.destination("invocation"))
        response = await self.barrier.upload(self.response, self.destination("response"))
        deferred = await self.barrier.upload(self.ready, self.destination("ready"))
        return invocation, response, deferred

    def assert_no_ready_upload(self):
        self.assertNotIn(self.destination("ready"), [call["remote"] for call in self.transfer.calls])

    async def test_slow_metadata_over_fifteen_seconds_keeps_ready_last(self):
        invocation, response, deferred = await self.before_commit()
        self.assertIs(invocation["deferred"], False)
        self.assertIs(response["deferred"], False)
        self.assertIs(deferred["deferred"], True)
        self.assertIs(deferred["verified"], False)
        self.assertEqual(deferred["pending"]["local"], barrier_module.snapshot(self.ready))
        self.assert_no_ready_upload()
        await self.barrier.upload(self.process, self.destination("process"))
        self.assertGreater(self.transfer.seconds, 15)
        self.assert_no_ready_upload()
        result = await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assertIs(result["deferred"], False)
        self.assertIs(result["ready_commit"]["verified"], True)
        self.assertEqual([call["remote"] for call in self.transfer.calls],
                         [self.destination(k) for k in ("invocation", "response", "process", "delivered", "ready")])
        events = self.barrier.events
        self.assertEqual(len([e for e in events if e["kind"] == "deferred"]), 1)
        self.assertEqual([e["artifact"] for e in events if e["kind"] == "transfer-verified"][-2:], ["delivered", "ready"])
        self.assertIsNone(self.barrier.pending)

    async def test_metadata_exception_never_attempts_ready_and_latches_no_retry(self):
        await self.before_commit()
        self.transfer.fail_suffix = ".codex.jsonl.json"
        with self.assertRaises(OSError):
            await self.barrier.upload(self.process, self.destination("process"))
        with self.assertRaisesRegex(BarrierError, "retry forbidden"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()
        self.assertEqual(len(self.transfer.calls), 3)

    async def test_delivered_transfer_failure_keeps_ready_unattempted(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        self.transfer.fail_suffix = ".delivered.json"
        with self.assertRaises(OSError):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()
        self.assertIsNotNone(self.barrier.pending)

    async def test_missing_process_refuses_delivery_and_ready(self):
        await self.before_commit()
        with self.assertRaisesRegex(BarrierError, "all three"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()
        self.assertEqual(len(self.transfer.calls), 2)

    async def test_wrong_ready_digest_refuses_without_transfer(self):
        await self.barrier.upload(self.response, self.destination("response"))
        write(self.ready, {"sha256": "0" * 64, "bytes": self.response.stat().st_size})
        with self.assertRaisesRegex(BarrierError, "READY payload"):
            await self.barrier.upload(self.ready, self.destination("ready"))
        self.assert_no_ready_upload()

    async def test_wrong_cell_binding_refuses_before_delivered_upload(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        data = json.loads(self.delivered.read_bytes())
        write(self.delivered, {**data, "session_id": "0" * 32})
        with self.assertRaisesRegex(BarrierError, "expected binding"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()
        self.assertEqual(len(self.transfer.calls), 3)

    async def test_wrong_delivered_response_digest_refuses(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        data = json.loads(self.delivered.read_bytes())
        write(self.delivered, {**data, "response_sha256": "0" * 64})
        with self.assertRaises(BarrierError):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()

    async def test_wrong_nonce_and_destination_refuse_without_any_transfer(self):
        for remote in (self.destination("response").replace(NONCE, "0" * 32),
                       self.destination("response") + "/", self.channel + "/../response.json"):
            with self.subTest(remote=remote):
                barrier = CommitLastTransfers(self.transfer, self.channel, self.binding, policy_sha256=POLICY)
                with self.assertRaises(BarrierError):
                    await barrier.upload(self.response, remote)
        self.assertEqual(self.transfer.calls, [])

    async def test_raw_invocation_cannot_bypass_projection(self):
        raw = write(self.local / "invocation.json", {"argv": ["secret-path"]})
        with self.assertRaisesRegex(BarrierError, "raw metadata bypass"):
            await self.barrier.upload(raw, self.destination("invocation"))
        self.assertEqual(self.transfer.calls, [])

    async def test_repeat_does_not_overwrite(self):
        await self.before_commit()
        with self.assertRaisesRegex(BarrierError, "Repeated destination"):
            await self.barrier.upload(self.ready, self.destination("ready"))
        self.assert_no_ready_upload()
        self.assertEqual(len(self.transfer.calls), 2)

    async def test_second_nonce_cannot_enter_pending(self):
        await self.before_commit()
        other_nonce = "0" * 32
        folder = self.root / other_nonce
        folder.mkdir()
        path = write(folder / "response.json", json.loads(self.response.read_bytes()))
        with self.assertRaisesRegex(BarrierError, "one active"):
            await self.barrier.upload(path, self.destination("response").replace(NONCE, other_nonce))
        self.assert_no_ready_upload()
        self.assertEqual(len(self.transfer.calls), 2)

    async def test_malformed_verified_receipts_never_allow_ready(self):
        corruptions = ({"verifie": None}, {"verifie": 1}, {"ok": False}, {"bytes": True},
                       {"to": "/different"}, {"empreinte_distante": "0" * 64},
                       {"remote_sha256": "0" * 64}, {"empreinte_locale": "0" * 64}, {"verified": None})
        for alteration in corruptions:
            with self.subTest(alteration=alteration):
                transfer = FakeVerifiedTransfers()
                transfer.corrupt = lambda payload, values=alteration: payload.update(values)
                barrier = CommitLastTransfers(transfer, self.channel, self.binding, policy_sha256=POLICY)
                with self.assertRaisesRegex(BarrierError, "verified RomeoFiles"):
                    await barrier.upload(self.response, self.destination("response"))
                self.assertEqual(len(transfer.calls), 1)
                self.assertFalse(any(call["remote"].endswith(".ready.json") for call in transfer.calls))

    async def test_unverified_process_payload_is_preserved_but_never_commits_ready(self):
        await self.before_commit()
        self.transfer.corrupt = lambda payload: payload.update(verifie=None)
        with self.assertRaisesRegex(BarrierError, "verified RomeoFiles"):
            await self.barrier.upload(self.process, self.destination("process"))
        self.assert_no_ready_upload()
        returned = [e for e in self.barrier.events if e["kind"] == "transfer-returned"]
        self.assertIsNone(returned[-1]["receipt"]["verifie"])
        self.assertFalse(self.barrier.events[-1]["ready_publication_may_be_unknown"])

    async def test_mutated_pending_file_refuses_ready(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        self.ready.write_bytes(self.ready.read_bytes() + b" ")
        with self.assertRaisesRegex(BarrierError, "prerequisite changed"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()

    async def test_projection_identity_mismatch_refuses_ready(self):
        await self.before_commit()
        data = json.loads(self.process.read_bytes())
        write(self.process, {**data, "private_argv_sha256": "0" * 64})
        await self.barrier.upload(self.process, self.destination("process"))
        with self.assertRaisesRegex(BarrierError, "another invocation"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()

    async def test_response_payload_nonce_mismatch_refuses_ready(self):
        data = json.loads(self.response.read_bytes())
        write(self.response, {**data, "nonce": "0" * 32})
        self.response_digest = hashlib.sha256(self.response.read_bytes()).hexdigest()
        write(self.ready, {"sha256": self.response_digest, "bytes": self.response.stat().st_size})
        data = json.loads(self.delivered.read_bytes())
        write(self.delivered, {**data, "response_sha256": self.response_digest})
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        with self.assertRaisesRegex(BarrierError, "Metadata nonce"):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assert_no_ready_upload()

    async def test_other_primary_is_delegated_and_marked_not_deferred(self):
        log = self.local / "codex.jsonl"
        log.write_bytes(b"raw preserved\n")
        result = await self.barrier.upload(log, self.channel + "/logs/" + NONCE + ".codex.jsonl")
        self.assertIs(result["deferred"], False)
        self.assertIs(result["verified"], True)
        self.assertEqual(len(self.transfer.calls), 1)

    async def test_local_symlink_refused(self):
        link = self.root / "response-link.json"
        try:
            link.symlink_to(self.response)
        except OSError:
            # Windows file symlinks need a privilege unavailable on this host.
            # Its existing My Documents junction exercises a real linked ancestor,
            # without creating or modifying that junction or writing through it.
            documents = Path.home() / "Documents"
            alias = Path.home() / "My Documents"
            self.assertTrue(alias.is_junction(), "A real link fixture is required")
            link = alias / self.response.relative_to(documents)
        with self.assertRaisesRegex(BarrierError, "links refused"):
            barrier_module.snapshot(link)

    async def test_ready_transfer_failure_is_recorded_as_publication_unknown(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        self.transfer.fail_suffix = ".ready.json"
        with self.assertRaises(OSError):
            await self.barrier.upload(self.delivered, self.destination("delivered"))
        self.assertTrue(self.barrier.events[-1]["ready_publication_may_be_unknown"])
        self.assertIsNotNone(self.barrier.pending)
        with self.assertRaisesRegex(BarrierError, "retry forbidden"):
            await self.barrier.upload(self.ready, self.destination("ready"))

    async def test_successful_commit_nonce_cannot_be_replayed(self):
        await self.before_commit()
        await self.barrier.upload(self.process, self.destination("process"))
        await self.barrier.upload(self.delivered, self.destination("delivered"))
        with self.assertRaisesRegex(BarrierError, "never replayed nonce"):
            await self.barrier.upload(self.response, self.destination("response"))
        self.assertEqual(len(self.transfer.calls), 5)
