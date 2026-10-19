"""Pure local Q15 source packaging; never evaluate a baseline or call a model."""
from __future__ import annotations

import argparse
import ast
import io
import json
import tarfile
from pathlib import Path

import qualification_contract as q

EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}


def file_ref(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": q.sha(path.read_bytes())}


def source_files(root):
    root = Path(root).resolve(strict=True)
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        q.need(not path.is_symlink(), "Linked project source refused")
        if path.is_file():
            q.relative(relative.as_posix())
            result[relative.as_posix()] = path.read_bytes()
    q.need(result, "Empty runtime source refused")
    return result


def qualifier_observer(raw):
    """Change only the policy validator and its explicit Q context/schema names."""
    text = raw.decode("utf8")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    changes = []
    replacement = ("def command_stream_policy(config: dict) -> dict | None:\n"
                   "    from .matrix15_qualification import qualification_command_stream_policy\n"
                   "    return qualification_command_stream_policy(config)\n")
    found = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "command_stream_policy":
            changes.append((node.lineno - 1, node.end_lineno, replacement))
            found.append(node.name)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"CONTEXT_SCHEMA", "EXECUTION_SCHEMA"}:
                suffix = "context" if name == "CONTEXT_SCHEMA" else "execution"
                changes.append((node.lineno - 1, node.end_lineno,
                                name + " = 'hpc-forest-matrix15-qualification-command-" + suffix + "-v1'\n"))
                found.append(name)
    q.need(set(found) == {"command_stream_policy", "CONTEXT_SCHEMA", "EXECUTION_SCHEMA"} and len(found) == 3,
           "Unexpected observer source shape; no broad replacement allowed")
    for first, last, value in sorted(changes, reverse=True):
        lines[first:last] = [value]
    updated = "".join(lines)
    before_functions = {node.name: ast.get_source_segment(text, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    after_functions = {node.name: ast.get_source_segment(updated, node) for node in ast.parse(updated).body if isinstance(node, ast.FunctionDef)}
    q.need(before_functions.keys() == after_functions.keys()
           and all(before_functions[name] == after_functions[name] for name in before_functions if name != "command_stream_policy"),
           "Qualification derivative changed the original observation/timing implementation")
    return updated.encode(), {"changed_function": "command_stream_policy",
        "changed_constants": ["CONTEXT_SCHEMA", "EXECUTION_SCHEMA"],
        "other_function_source_unchanged": True, "native_authorization": False}


def prepared_prefix(remote):
    q.need(isinstance(remote, str) and remote.count("/preparation/") == 1, "Exact R1 preparation root shape required")
    prefix = "preparation/" + remote.split("/preparation/", 1)[1]
    q.relative(prefix)
    return prefix


def case_keys(rows):
    return {(row["input_fingerprint"], tuple(row["capture_files"])) for row in rows}


def assemble(project, prepared_manifest, contracts_reference, statements_root, harness, output):
    project, statements_root = Path(project).resolve(strict=True), Path(statements_root).resolve(strict=True)
    prepared_manifest, contracts_reference, harness = map(Path, (prepared_manifest, contracts_reference, harness))
    prep_raw, r1_raw, harness_raw = (path.read_bytes() for path in (prepared_manifest, contracts_reference, harness))
    q.need(q.sha(prep_raw) == q.PREP_SHA and q.sha(r1_raw) == q.R1_SHA and q.sha(harness_raw) == q.HARNESS_SHA,
           "Original R1 prepared/paired-contract/mixed-harness SHA pins differ")
    prep, contracts = q.read(prep_raw), q.read(r1_raw)
    q.need(prep.get("schema") == "hpc-forest-shared-official-preparation-v1"
           and isinstance(prep.get("files"), dict) and isinstance(prep.get("records"), dict)
           and set(contracts.get("subjects", {})) == set(q.SUBJECTS), "Actual R1 preparation/15contracts required")
    output = Path(output)
    q.need(output.is_absolute() and output.parent.resolve(strict=True) == output.parent and not output.exists(),
           "Unique new Q15 assembly output required")
    q.need(not output.is_relative_to(project) and not output.is_relative_to(statements_root),
           "Q15 output must be disjoint from every preserved input tree")
    payload, refs, subjects = {}, [], {}

    def add(name, raw):
        q.relative(name)
        q.need(name not in payload, "Duplicate Q15 package member")
        payload[name] = raw

    def copy_ref(path, name, *, checksum=None):
        path = Path(path).resolve(strict=True)
        raw = path.read_bytes()
        q.need(not path.is_symlink() and (checksum is None or q.sha(raw) == checksum), "Referenced R1 material changed")
        add(name, raw)
        refs.append({"original": file_ref(path), "package_member": name, "bytes": len(raw)})
        return raw

    add("evidence/prepared-r1-manifest.json", prep_raw)
    add("evidence/contrats-reference.json", r1_raw)
    refs.extend([{"original": file_ref(prepared_manifest), "package_member": "evidence/prepared-r1-manifest.json", "bytes": len(prep_raw)},
                 {"original": file_ref(contracts_reference), "package_member": "evidence/contrats-reference.json", "bytes": len(r1_raw)}])
    counts = {"source": 0, "validation": 0, "total": 0}
    for subject in q.SUBJECTS:
        record = prep["records"].get(subject)
        q.need(isinstance(record, dict) and record.get("status") == "ready", "Subject R1 preparation not ready")
        contract_ref = contracts["subjects"][subject]["contract"]
        contract_path, contract_raw = q.artifact(contract_ref)
        campaign = contract_path.parent.parent
        role_rows = {}
        for role, local_root in (("source", campaign / "repo"), ("validation", campaign / "trusted")):
            prefix = prepared_prefix(record["prepared"][role]) + "/"
            rows = {name[len(prefix):]: checksum for name, checksum in prep["files"].items() if name.startswith(prefix)}
            q.need(rows, "R1 whitelist missing an exact subject/role")
            for name, checksum in rows.items():
                q.relative(name)
                q.need(isinstance(checksum, str) and q.SHA.fullmatch(checksum), "R1 whitelist SHA malformed")
                copy_ref(local_root / name, "prepared/" + subject + "/" + role + "/" + name, checksum=checksum)
            role_rows[role] = rows
            counts[role] += len(rows)
        q.need(role_rows["validation"].get("contract.json") == contract_ref["sha256"]
               and payload["prepared/" + subject + "/validation/contract.json"] == contract_raw,
               "Prepared whitelist differs from paired R1 contract reference")
        original_config_raw = copy_ref(campaign / "trusted/config.json", "configs/" + subject + ".json")
        original_config, contract = q.read(original_config_raw), q.read(contract_raw)
        q.need(original_config.get("problem") == subject and original_config.get("seed") == 23
               and original_config.get("protocol", {}).get("confirmation_repetitions") == 5
               and original_config.get("harness") == q.read(harness_raw), "R1 subject/seed/harness/five-confirmations differ")
        all_cases = [*contract["search"], *contract["confirmation"], contract["benchmark"]]
        subjects[subject] = {"source": "prepared/" + subject + "/source", "validation": "prepared/" + subject + "/validation",
            "config": "configs/" + subject + ".json", "r1_contract_sha256": contract_ref["sha256"],
            "r1_contract_reference": contract_ref, "r1_audit_reference": contracts["subjects"][subject]["audit"],
            "original_preparation_record_sha256": q.sha(q.data(record)), "source_files": len(role_rows["source"]),
            "validation_files": len(role_rows["validation"]), "statement": "statements/" + subject[:4] + ".txt",
            "case_counts": {"search_rows": len(contract["search"]), "confirmation_rows": len(contract["confirmation"]),
                "benchmark_rows": 1, "unique_inputs": len(case_keys(all_cases)),
                "search_checker_unique_inputs": len(case_keys([*contract["search"], contract["benchmark"]])),
                "confirmation_checker_unique_inputs": len(case_keys([*contract["confirmation"], contract["benchmark"]]))}}
    counts["total"] = counts["source"] + counts["validation"]
    q.need(counts == {"source": 46, "validation": 150, "total": 196}, "Actual exact R1 whitelist is not46+150=196")
    for year in ("2020", "2021", "2022", "2023"):
        copy_ref(statements_root / (year + ".txt"), "statements/" + year + ".txt")
    copy_ref(harness, "harness-mixed.json", checksum=q.HARNESS_SHA)
    parent_runtime = source_files(project)
    q.need(q.sha(q.data({name: q.sha(raw) for name, raw in parent_runtime.items()}))
           == q.PARENT_RUNTIME_MANIFEST_SHA256, "Reviewed single-pilot source bytes required")
    runtime = dict(parent_runtime)
    observer_name = "src/hpc_forest/matrix15_provenance.py"
    runtime[observer_name], delta = qualifier_observer(runtime[observer_name])
    local_root = Path(__file__).resolve().parent
    qcontract_raw = (local_root / "qualification_contract.py").read_bytes()
    runtime["src/hpc_forest/matrix15_qualification.py"] = qcontract_raw
    for name, raw in runtime.items():
        add("project-q/" + name, raw)
    add("qualification_contract.py", qcontract_raw)
    add("qualify15.py", (local_root / "qualify15.py").read_bytes())
    add("ORIGINAL-RUNTIME-MANIFEST.json", q.data({name: q.sha(raw) for name, raw in parent_runtime.items()}))
    add("RUNTIME-Q-MANIFEST.json", q.data({name: q.sha(raw) for name, raw in runtime.items()}))
    add("QUALIFICATION-SOURCE-DELTA.json", q.data({"schema": "hpc-forest-Q15-source-derivative-v1", **delta,
        "parent_observer_sha256": q.sha(parent_runtime[observer_name]), "Q_observer_sha256": q.sha(runtime[observer_name]),
        "new_module": "src/hpc_forest/matrix15_qualification.py", "scientific_checker_changes": 0,
        "shared_future_matrix_project_modified": False}))
    plan = {"schema": "hpc-forest-matrix15-baseline-qualification-plan-v1", "scope_id": q.SCOPE,
        "subject_order": list(q.SUBJECTS), "subjects": subjects, "asset_counts": counts,
        "preparation_sha256": q.PREP_SHA, "r1_contracts_sha256": q.R1_SHA, "harness_sha256": q.HARNESS_SHA,
        "source_bindings": {"schema": "hpc-forest-Q15-single-pilot-source-binding-v1",
            "parent_runtime_manifest_sha256": q.PARENT_RUNTIME_MANIFEST_SHA256,
            "q_runtime_manifest_sha256": q.sha(payload["RUNTIME-Q-MANIFEST.json"]),
            "single_pilot_protocol_sha256": q.SINGLE_PILOT_PROTOCOL_SHA256},
        "native_authorization": False, "native_model_calls": 0, "Controller_instances": 0,
        "Mother_instances": 0, "native_workers_started": 0, "new_inputs_or_oracles": 0,
        "configuration_count": 15, "statement_count": 4, "harness_count": 1,
        "limits": ["196whitelisted official source/validation files only; not the entire original prepared package.",
                   "Config and annual statement provenance are separate actual R1 file references, not fabricated prepared-manifest entries.",
                   "Q15 baseline readiness only; no inference authorization, gain, or independent case/performance admission."]}
    add("PLAN-Q15.json", q.data(plan))
    add("LOCAL-ORIGINAL-REFERENCES.json", q.data({"schema": "hpc-forest-Q15-local-original-refs-v1", "files": refs}))
    # Finish the original reads before creating any deliverable.
    for ref in refs:
        q.artifact(ref["original"])
    q.need(parent_runtime == source_files(project), "Shared future source changed while packaging")
    add("PACKAGE-MANIFEST.json", q.data({"schema": "hpc-forest-Q15-package-files-v1",
                                       "files": {name: q.sha(raw) for name, raw in payload.items()}}))
    output.mkdir(exist_ok=False)
    package = output / "paquet"
    package.mkdir()
    for name, raw in payload.items():
        path = package.joinpath(*q.relative(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        q.need(path.read_bytes() == raw, "Written Q15 package bytes differ")
    archive_path = output / "HPC-Forest-Q15-baseline-source-r1.tar.gz"
    with archive_path.open("xb") as raw, tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, value in sorted(payload.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(value), 0o600, 0
            archive.addfile(item, io.BytesIO(value))
    receipt = {"schema": "hpc-forest-Q15-local-source-preparation-v1", "scope_id": q.SCOPE,
        "archive": file_ref(archive_path), "plan": file_ref(package / "PLAN-Q15.json"),
        "package_manifest": file_ref(package / "PACKAGE-MANIFEST.json"), "source_delta": file_ref(package / "QUALIFICATION-SOURCE-DELTA.json"),
        "asset_counts": counts, "runtime_source_files": len(runtime), "package_members": len(payload),
        "configurations": 15, "statements": 4, "harnesses": 1, "compiled_baselines": 0,
        "local_qualification_executed": False, "jobs_submitted": 0, "transfers": 0, "native_model_calls": 0,
        "native_authorization": False, "qualification_ready": False, "scientific_gain_claimed": False}
    with (output / "PREPARATION-Q15.json").open("xb") as stream:
        stream.write(q.data(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--prepared-manifest", type=Path, required=True)
    parser.add_argument("--contracts-reference", type=Path, required=True)
    parser.add_argument("--statements-root", type=Path, required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(assemble(args.project, args.prepared_manifest, args.contracts_reference,
                              args.statements_root, args.harness, args.output)))


if __name__ == "__main__":
    main()
