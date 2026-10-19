"""Portable strict gate for a received and actually released first Matrix15 batch.

No generation, transport, auth mutation or receipt creation is performed here.
Both hosts pass an exact resolver; Windows may map only explicit received refs.
"""
from __future__ import annotations

import contextlib
import hashlib
import math
import re
import time
from pathlib import Path

SCHEMA = "hpc-forest-matrix15-extension-first-batch-gate-v1"
SOURCE_SHA = "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4"
PLAN_SHA = "a3b429cca6fe70555ec8c24fb3e91671846f87e658c62fc5b6bb0c8566bcd97f"
FIRST_SESSION = "9a681c2826854a4b885e94c5e6243f0a"
FIRST_ROOT = "/gpfs/scratch/nimarano/hpc-forest-matrix15-native-max-r2-" + FIRST_SESSION
FIRST_FIELDS = {"scope_id": "hpc-forest-matrix15-native-max-r2", "cell_key": "forest-r2/gpt-6-luna/max/2020-quicksort/seed-23",
                "subject_id": "2020-quicksort", "model": "gpt-6-luna", "effort": "max", "session_id": FIRST_SESSION,
                "remote_root": FIRST_ROOT, "source_zip_sha256": SOURCE_SHA, "plan_sha256": PLAN_SHA,
                "preparation_manifest_sha256": "d60b93312c34319386cc7057fd77248df38282ee717ee63ca80ad911cf5e7313",
                "r1_contract_sha256": "c2fa077535e04b8d3f65ca4e4705ba178b55de6513aa4d1f071374bf9a776a16"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
ROOT_REVIEW_FIELDS = {"schema", "verified", "evidence_origin", "first_binding", "source_zip_sha256", "plan_sha256",
                      "all_private_raws_received_and_hashed", "actual_arm_release_received", "release_sha256",
                      "engine_release_receipt_sha256", "private_review_receipt_sha256", "proposal_receipt_sha256",
                      "root_review_instruction", "reviewed_at", "automatic_extension"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def exact_reader(ref, resolver):
    need(type(ref) is dict and set(ref) == {"path", "sha256"} and isinstance(ref["path"], str)
         and SHA.fullmatch(str(ref["sha256"])), "Exact first-batch path/SHA reference required")
    path = Path(resolver(ref))
    need(path.is_file() and path.stat().st_size <= 8 * 1024**2
         and not any(item.is_symlink() or getattr(item, "is_junction", lambda: False)() for item in (path, *path.parents)),
         "Received first-batch reference missing/oversized/linked")
    need(hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"], "Received first-batch reference bytes changed")
    return path


@contextlib.contextmanager
def resolver_context(native, batch, resolver):
    original_native, original_batch = native.artifact, batch.artifact
    try:
        native.artifact = lambda ref, **_kwargs: exact_reader(ref, resolver)
        batch.artifact = lambda ref: exact_reader(ref, resolver)
        yield
    finally:
        native.artifact, batch.artifact = original_native, original_batch


def validate_gate(gate, *, read_ref, native, batch):
    fields = {"schema", "verified", "evidence_origin", "source_zip_sha256", "plan_sha256", "first_binding",
              "authorization", "paused_snapshot", "first_start_receipt", "evaluation_snapshot", "release",
              "private_cli_audit", "engine_release_receipt", "proposal_receipt", "root_reception_review"}
    need(type(gate) is dict and set(gate) == fields and gate.get("schema") == SCHEMA
         and gate.get("verified") is True and gate.get("evidence_origin") == "received"
         and gate.get("source_zip_sha256") == SOURCE_SHA and gate.get("plan_sha256") == PLAN_SHA,
         "Actual received and verified first-batch gate required")
    binding = gate["first_binding"]
    need(type(binding) is dict and set(binding) == {*FIRST_FIELDS, "job_id"}
         and all(binding.get(key) == value for key, value in FIRST_FIELDS.items())
         and re.fullmatch(r"[1-9][0-9]*", binding.get("job_id", "")), "Original Luna/MAX/quicksort first-batch identity required")
    output = FIRST_ROOT + "/results-" + binding["job_id"]
    exact = {"authorization": FIRST_ROOT + "-admission/authorization.json",
             "paused_snapshot": output + "/premier-batch-en-attente.json",
             "first_start_receipt": output + "/premier-demarrage-verifie.json",
             "release": output + "/autorisation-apres-premier-batch.json",
             "engine_release_receipt": output + "/premier-batch-release-verifiee.json"}
    for key, path in exact.items():
        need(type(gate[key]) is dict and gate[key].get("path") == path, "Original exact ARM path differs: " + key)
    with resolver_context(native, batch, read_ref):
        ref_keys = fields - {"schema", "verified", "evidence_origin", "source_zip_sha256", "plan_sha256", "first_binding"}
        paths = {key: native.artifact(gate[key]) for key in ref_keys}
        auth = native.read_json(paths["authorization"])
        need(set(auth) == native.AUTHORIZATION_FIELDS and auth.get("schema") == "hpc-forest-matrix15-authorization-v1"
             and native.cell_binding(auth) == binding and auth.get("verified") is True,
             "Historical first authorization differs")
        # No current-time validation of old capacity or old auth expiry: this is past evidence.
        snapshot = native.read_json(paths["paused_snapshot"])
        snapshot["self_ref"] = gate["paused_snapshot"]
        first = native.read_json(paths["first_start_receipt"])
        release = native.read_json(paths["release"])
        need(release.get("private_cli_audit") == gate["private_cli_audit"]
             and release.get("evaluation_snapshot") == gate["evaluation_snapshot"], "Release dependency differs from gate")
        audit = batch.validate_first_batch_release(release, snapshot, first, auth)
        identity = {**binding, "protocol_id": first["protocol_id"]}
        proposal = native.read_json(paths["proposal_receipt"])
        proposal_fields = {"schema", "verified", *identity, "input", "private_audit", "projection", "proposed_release",
                           "source127_validate_first_batch_release_passed", "release_installed", "upload_performed",
                           "native_model_calls", "no_replay", "new_model_or_budget_authorized", "existing_search_deadline"}
        need(set(proposal) == proposal_fields
             and proposal.get("schema") == "hpc-forest-matrix15-first-batch-proposal-receipt-v1"
             and proposal.get("verified") is True and all(proposal.get(key) == value for key, value in identity.items())
             and proposal.get("source127_validate_first_batch_release_passed") is True
             and proposal.get("release_installed") is False and proposal.get("upload_performed") is False
             and type(proposal.get("native_model_calls")) is int and proposal["native_model_calls"] == 0
             and proposal.get("no_replay") is True and proposal.get("new_model_or_budget_authorized") is False
             and type(proposal.get("existing_search_deadline")) in {int, float}
             and math.isfinite(proposal["existing_search_deadline"]) and proposal["existing_search_deadline"] > 0,
             "Actual source127 cold-audit proposal receipt required")
        for name in ("input", "private_audit", "projection", "proposed_release"):
            value = proposal.get(name)
            need(type(value) is dict and set(value) == {"path", "sha256", "bytes"}
                 and isinstance(value["path"], str) and SHA.fullmatch(str(value["sha256"]))
                 and type(value["bytes"]) is int and value["bytes"] > 0,
                 "Actual cold-audit sized output reference required")
        need(proposal["projection"]["sha256"] == gate["private_cli_audit"]["sha256"]
             and proposal["proposed_release"]["sha256"] == gate["release"]["sha256"]
             and proposal["private_audit"]["sha256"] == audit["private_review_receipt_sha256"],
             "Cold-audit proposal references do not match the actually consumed release")
        accepted = native.read_json(paths["engine_release_receipt"])
        accepted_fields = {"verified", *identity, "release", "private_cli_audit", "private_review_receipt_sha256",
                           "budget_or_chronology_reset", "replayed_claims"}
        need(set(accepted) == accepted_fields and accepted.get("verified") is True
             and all(accepted.get(key) == value for key, value in identity.items())
             and accepted.get("release") == gate["release"] and accepted.get("private_cli_audit") == gate["private_cli_audit"]
             and accepted.get("private_review_receipt_sha256") == audit["private_review_receipt_sha256"]
             and accepted.get("budget_or_chronology_reset") is False
             and type(accepted.get("replayed_claims")) is int and accepted["replayed_claims"] == 0,
             "Actual native engine did not receive/accept the audited first-batch release")
        review = native.read_json(paths["root_reception_review"])
        need(set(review) == ROOT_REVIEW_FIELDS
             and review.get("schema") == "hpc-forest-matrix15-extension-first-batch-root-review-v1"
             and review.get("verified") is True and review.get("evidence_origin") == "received"
             and review.get("first_binding") == binding and review.get("source_zip_sha256") == SOURCE_SHA
             and review.get("plan_sha256") == PLAN_SHA and review.get("all_private_raws_received_and_hashed") is True
             and review.get("actual_arm_release_received") is True and review.get("automatic_extension") is False
             and review.get("release_sha256") == gate["release"]["sha256"]
             and review.get("engine_release_receipt_sha256") == gate["engine_release_receipt"]["sha256"]
             and review.get("private_review_receipt_sha256") == audit["private_review_receipt_sha256"]
             and review.get("proposal_receipt_sha256") == gate["proposal_receipt"]["sha256"]
             and isinstance(review.get("root_review_instruction"), str) and review["root_review_instruction"].strip()
             and type(review.get("reviewed_at")) in {int, float} and math.isfinite(review["reviewed_at"])
             and 0 < review["reviewed_at"] <= time.time(), "Explicit reviewed root reception is absent or unbound")
    return {"first_binding": binding, "release_sha256": gate["release"]["sha256"],
            "engine_release_receipt_sha256": gate["engine_release_receipt"]["sha256"],
            "root_review_sha256": gate["root_reception_review"]["sha256"]}
