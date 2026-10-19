"""Create a private, isolated revision. Never run a model or modify an input."""
from __future__ import annotations

import difflib
import hashlib
import json
import pprint
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

CURRENT = Path("C:/Users/nicol/Documents/Codex/2026-10-19/je-voudrais-que-tu-commit-et")
ORIGINAL = Path("C:/Users/nicol/Documents/Codex/2026-10-19/c-users-nicol-documents-codex-2026-4")
SOURCE = ORIGINAL / "work/r2-matrix15-preparation-r1/project"
WORK = CURRENT / "work/matrix15-single-pilot-r1"
OUTPUT = CURRENT / "outputs/HPC-Forest-Matrice15-Pilote-Unique-r1"
OLD_PROTOCOL = ORIGINAL / "outputs/HPC-Forest-R2-Matrice15-Preparation-r1/PROTOCOLE-60-CELLULES.json"
OLD_PRIMES = ORIGINAL / "outputs/HPC-Forest-R2-Reprise-20261019-r1/PROTOCOLE-R2H.json"
SOL = ORIGINAL / "outputs/HPC-Forest-R2-Reprise-20261019-r1/LIBERATION-SCIENTIFIQUE-SOL-COMPLETE.json"
EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
REQUEST = "je voudrais que tu commit et push toutes les donne qu#on a recu et aussi le pdf article sur le rep, de plus  il fqudrqis pas tous les lancer sur nombre premier c#etais juste un test une fois nombre premier passer sans bug on passe au 15 sujet avec tous les models en Max stp"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path)}


def write_json(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if path.is_symlink() or path.is_junction():
            raise ValueError("Source contains a link: " + str(relative))
        if path.is_file():
            result[relative.as_posix()] = sha(path)
    return result


def main():
    if WORK.exists() or OUTPUT.exists():
        raise FileExistsError("Isolated revision already exists; do not overwrite")
    before = inventory(SOURCE)
    originals = {str(p): sha(p) for p in (OLD_PROTOCOL, OLD_PRIMES, SOL)}
    WORK.mkdir()
    OUTPUT.mkdir(parents=True)
    project = WORK / "project"
    shutil.copytree(SOURCE, project, ignore=shutil.ignore_patterns(*EXCLUDED))
    if inventory(project) != before:
        raise ValueError("Copy differs from source before revision")
    write_json(OUTPUT / "SOURCE-ORIGINALE-AVANT.json", {"source": str(SOURCE), "files": before,
                                                       "historical_protocols_and_release": originals})

    protocol = json.loads(OLD_PROTOCOL.read_text(encoding="utf8"))
    old_sessions = {cell["session_id"] for cell in protocol["cells"]}
    for cell in protocol["cells"]:
        cell["session_id"] = uuid.uuid4().hex
    new_sessions = {cell["session_id"] for cell in protocol["cells"]}
    assert len(new_sessions) == 60 and not old_sessions.intersection(new_sessions)
    protocol["schema"] = "hpc-forest-matrix15-human-single-pilot-protocol-v2"
    protocol["created_utc"] = datetime.now(UTC).isoformat()
    protocol["status"] = "isolated_private_code_preparation_only"
    protocol["revision_of"] = ref(OLD_PROTOCOL)
    protocol["historical_primes_protocol"] = ref(OLD_PRIMES)
    protocol["historical_human_messages"] = protocol.pop("human_messages")
    protocol["human_messages"] = [REQUEST]
    protocol["human_revision_date"] = "2026-10-19"
    protocol["required_before_model_launch"] = (
        "The one already received and independently audited Sol MAX primes pilot, exact immutable release; "
        "no additional primes cells required. All subject qualifications, receptions, capacity, "
        "fresh single-cell admissions and no-replay guards remain required."
    )
    protocol["primes_release"] = ref(SOL)
    protocol["pilot_count"] = 1
    protocol["remaining_primes_cells_to_launch"] = 0
    protocol["new_sessions_only"] = True
    protocol["runtime_plan_created"] = False
    protocol["qualification_ready"] = False
    protocol["launch_ready"] = False
    new_protocol = OUTPUT / "PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json"
    write_json(new_protocol, protocol)
    write_json(OUTPUT / "MANIFESTE-60-CELLULES-NEUVES.json", {
        "schema": "hpc-forest-matrix15-fresh-single-pilot-cell-manifest-v1",
        "protocol": ref(new_protocol), "previous_protocol": ref(OLD_PROTOCOL),
        "models": protocol["models"], "efforts": protocol["efforts"],
        "subjects": protocol["subjects"], "cells": protocol["cells"], "cell_count": 60,
        "all_sessions_new_and_unique": True, "jobs_submitted": 0, "native_model_calls": 0,
    })

    contract = project / "src/hpc_forest/matrix15_contract.py"
    text = contract.read_text(encoding="utf8")
    text = text.replace('PROTOCOL_SHA256 = "93e51d9e2a8985641b678826698f5dfd63da069dd5fdaf708e04803453d3de21"',
                        'PROTOCOL_SHA256 = "' + sha(new_protocol) + '"')
    start = text.index("REGISTERED_CELLS = ")
    stop = text.index("\nBUDGETS = ", start)
    text = text[:start] + "REGISTERED_CELLS = " + pprint.pformat(
        {cell["cell_key"]: cell for cell in protocol["cells"]}, width=110, sort_dicts=False
    ) + text[stop:]
    contract.write_text(text, encoding="utf8", newline="\n")

    native = project / "src/hpc_forest/native_matrix15.py"
    text = native.read_text(encoding="utf8")
    start = text.index("def verify_primes_release(")
    stop = text.index("\ndef verify_qualification(", start)
    gate = '''SOL_PILOT_RELEASE_SHA256 = "RELEASE_DIGEST"
SOL_PILOT_FINAL_AUDIT_SHA256 = "b8bfd8c55dc0c4b02bed058cb58e17178400fa026cd53655ec987af0f8e0222e"
SOL_PILOT_EXTERNAL_AUDIT_SHA256 = "86da0f5789ed1f6c9926289d92d198b4c2399626df5664afb58a9d6d3a71913a"


def verify_primes_release(path, read_ref=artifact):
    """Accept only the already audited Sol pilot; subject/capacity gates remain separate."""
    value = read_json(path)
    identity = {"schema": "hpc-forest-r2h-first-cell-scientific-release-v1",
                "scope_id": "hpc-forest-primes-native-max-r2h", "model": "gpt-6.1-sol",
                "effort": EFFORT, "session_id": "0f1de21e9eda4fb89a8dbd66c6fa8d6c", "job_id": "755306",
                "source_zip_sha256": "1eea1a11a5f6bdcadedbb295d708bcb0b67c428ea623c80c5391a884bdb8dba7",
                "plan_sha256": "9b060aa89f278bfd124da607f25c119654eb5dd21d7f19e2ecb0f8acf5ca5a72"}
    need(all(value.get(key) == expected for key, expected in identity.items()),
         "The exact already received Sol MAX primes pilot is required")
    flags = ("verified", "pipeline_complete", "five_confirmations_verified", "received_native_cohort_audited",
             "all_started_calls_reconciled", "independent_performance_remeasurement_verified",
             "owned_worker_and_passives_absent", "complete_52_file_cache_preserved",
             "reference_and_winner_sources_commits_trees_outcomes_equal_before_and_after_owned_stop")
    need(all(value.get(key) is True for key in flags)
         and all(value.get(key) is False for key in ("prepared", "synthetic", "old_cohort", "budget_or_chronology_reset"))
         and all(type(value.get(key)) is int and value[key] == expected for key, expected in
                 (("exact_known_native_calls", 3), ("exact_known_tokens", 59037), ("unknown_usage_calls", 0), ("replayed_claims", 0))),
         "Sol pilot is incomplete, synthetic, unreconciled or has unknown/replayed usage")
    need(file_digest(path) == SOL_PILOT_RELEASE_SHA256, "Sol pilot release SHA differs from the reviewed immutable receipt")
    paths = evidence_refs(value, read_ref)
    proofs = {ref["sha256"]: read_json(proof) for ref, proof in zip(value["evidence_refs"], paths, strict=True)}
    need(SOL_PILOT_FINAL_AUDIT_SHA256 in proofs and SOL_PILOT_EXTERNAL_AUDIT_SHA256 in proofs,
         "The real final audit and independent external measurement are required")
    audit = proofs[SOL_PILOT_FINAL_AUDIT_SHA256]
    measurement = proofs[SOL_PILOT_EXTERNAL_AUDIT_SHA256]
    need(all(audit.get(key) == identity[key] for key in ("scope_id", "model", "effort", "session_id", "job_id",
                                                        "source_zip_sha256", "plan_sha256"))
         and audit.get("terminal_pipeline", {}).get("pipeline_complete") is True
         and audit.get("campaign", {}).get("lineage_and_five_confirmations_verified") is True
         and audit.get("transport_cost_reconciliation", {}).get("exact_known_native_invocations") == 3
         and audit.get("transport_cost_reconciliation", {}).get("exact_known_tokens") == 59037
         and audit.get("transport_cost_reconciliation", {}).get("unknown_native_invocations") == 0,
         "The bounded final audit does not prove five confirmations and exact usage")
    need(measurement.get("schema") == "hpc-forest-r2h-independent-cold-audit-v1"
         and measurement.get("verified") is True and measurement.get("model") == identity["model"]
         and measurement.get("effort") == EFFORT and measurement.get("original_search_job_id") == identity["job_id"]
         and measurement.get("job_id") == value.get("external_pair", {}).get("job_id")
         and measurement.get("independent_from_search") is True
         and measurement.get("frozen_winner_reconfirmed") is True
         and measurement.get("independent_performance_audit_verified") is True
         and measurement.get("unique_certified_inputs") == 12 and measurement.get("blocking_findings") == [],
         "The separate bounded external remesurement is unproved")
    read_ref(measurement["archive"])
    return value

'''.replace("RELEASE_DIGEST", sha(SOL))
    text = (text[:start] + gate + text[stop:]).replace("    MODELS,\n", "")
    text = text.replace("Prepared plan cannot launch without actual four-model primes scientific release",
                        "Prepared plan cannot launch without the reviewed single Sol primes pilot")
    native.write_text(text, encoding="utf8", newline="\n")
    runner = project / "examples/marathon22/forest_matrix15.py"
    text = runner.read_text(encoding="utf8").replace("the four-model primes release", "the single audited Sol primes pilot")
    runner.write_text(text, encoding="utf8", newline="\n")

    after = inventory(SOURCE)
    if after != before or any(sha(Path(p)) != digest for p, digest in originals.items()):
        raise ValueError("Original input changed during preparation")
    write_json(OUTPUT / "PRESERVATION-SOURCES-HISTORIQUES.json", {
        "original_sources_unchanged": True, "historical_protocols_and_release_unchanged": True,
        "original_inventory": ref(OUTPUT / "SOURCE-ORIGINALE-AVANT.json"),
        "original_files": len(before), "excluded": sorted(EXCLUDED), "jobs_submitted": 0,
        "native_model_calls": 0, "active_chat_modified": False,
    })
    changed = []
    patch = []
    for key, digest in inventory(project).items():
        if before.get(key) == digest:
            continue
        changed.append(key)
        patch.extend(difflib.unified_diff((SOURCE / key).read_text(encoding="utf8").splitlines(True),
                     (project / key).read_text(encoding="utf8").splitlines(True), fromfile="a/" + key, tofile="b/" + key))
    (WORK / "single-pilot.patch").write_text("".join(patch), encoding="utf8", newline="\n")
    write_json(OUTPUT / "PREPARATION-REVISION-ISOLEE.json", {
        "schema": "hpc-forest-matrix15-isolated-single-pilot-revision-v1", "protocol": ref(new_protocol),
        "pilot_release": ref(SOL), "private_project": str(project), "private_patch": ref(WORK / "single-pilot.patch"),
        "modified_files": changed, "new_sessions": len(new_sessions), "launch_ready": False,
        "subject_qualifications_and_receptions_still_required": True,
        "capacity_and_single_cell_admissions_still_required": True,
        "native_model_calls": 0, "jobs_submitted": 0, "publication_of_private_engine_authorized": False,
    })
    print(json.dumps({"protocol_sha256": sha(new_protocol), "release_sha256": sha(SOL),
                      "files_copied": len(before), "changed": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
