"""At most six independent MCP contexts; verified downloads only, never retry."""
from __future__ import annotations

import argparse
import asyncio
import importlib.machinery
import importlib.util
import json
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SCHEMA = "hpc-forest-matrix15-parallel-readonly-receive-v1"
AUDITOR = BASE / "outputs/HPC-Forest-Matrice15-Premier-Batch-Preparation-r1/lecteur/first_batch_audit.py"
AUDITOR_SHA = "dce92d6e1735a8b594528b61bc0134d6069ab524a5fecc0eb08c1d5a024d4e13"


def runtime():
    class Loader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            raw = Path(self.path).read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest() != AUDITOR_SHA:
                raise ValueError("Pinned cold reader changed")
            return compile(raw, self.path, "exec", dont_inherit=True)
    loader = Loader("matrix15_parallel_reader", str(AUDITOR))
    spec = importlib.util.spec_from_file_location(loader.name, AUDITOR, loader=loader)
    reader = importlib.util.module_from_spec(spec)
    loader.exec_module(reader)
    source = BASE / "outputs/HPC-Forest-Matrice15-Admission-r2"
    reader.sealed_source({"project_root": str(BASE / "work/matrix15-admission-no-cycle-r2/project"),
        "source_zip": reader.local_ref(source / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"),
        "runtime_manifest": reader.local_ref(source / "RUNTIME-PRIVE-LOCAL.json")})
    return reader


def validate_plan(reader, plan):
    reader.need(set(plan) == {"schema", "refs", "lanes", "config_path", "output_root"} and plan["schema"] == SCHEMA,
                "Exact readonly receive plan required")
    reader.need(type(plan["lanes"]) is int and 1 <= plan["lanes"] <= 6, "One to six contexts required")
    reader.need(plan["config_path"] == "C:/Users/nicol/.codex/config.toml", "Existing private config path required")
    reader.need(isinstance(plan["refs"], list) and 0 < len(plan["refs"]) <= 5000, "Bounded nonempty exact ARM refs required")
    seen = {}
    for ref in plan["refs"]:
        reader.remote_ref(ref)
        reader.need(ref["path"] not in seen, "Duplicate/conflicting SHA for original ARM path")
        seen[ref["path"]] = ref["sha256"]
    output = Path(plan["output_root"])
    reader.need(output.is_absolute() and ".." not in output.parts and output.is_relative_to(BASE) and output != BASE,
                "Absolute output confined to workspace required")
    reader.need(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (output, *output.parents)),
                "Linked output ancestor refused")
    output = output.resolve()
    reader.need(output.is_relative_to(BASE.resolve()) and not output.exists(), "Fresh exclusive output required")
    return output


def verify_download(reader, ref, local, arguments, response):
    payload = reader.response_value(response)
    actual = reader.local_ref(local)
    reader.need(arguments == {"remote_path": ref["path"], "local_path": str(local), "verify": True}
        and payload.get("ok") is True and payload.get("transport") == "scp" and payload.get("verifie") is True
        and payload.get("downloaded") == ref["path"] and payload.get("to") == str(local)
        and type(payload.get("bytes")) is int and payload["bytes"] == actual["bytes"]
        and actual["sha256"] == ref["sha256"]
        and all(payload.get(k) == ref["sha256"] for k in ("remote_sha256", "empreinte_locale", "empreinte_distante")),
        "Exact SCP metadata/local bytes/three hashes differ")
    return actual


async def receive(plan, reader, *, relay_class=None):
    """The optional Python-only client seam is always labelled NEUTRAL in its artifacts."""
    output = validate_plan(reader, plan)
    output.mkdir(parents=True, exist_ok=False)
    for name in ("files", "raw", "catalog", "failures"):
        (output / name).mkdir()
    neutral = relay_class is not None
    if relay_class is None:
        from hpc_forest.codex_worker import RomeoFiles
        relay_class = RomeoFiles
    entries, failures = [], []
    def failure(filename, data):
        data = {"schema": "hpc-forest-readonly-receive-refusal-v1", "verified": False, "observed_at": time.time(),
                "neutral": neutral, "retry_performed": False, **data}
        failures.append(reader.write_exclusive(output / "failures" / filename, data))
    async def lane(number):
        assigned = list(enumerate(plan["refs"], 1))[number::min(plan["lanes"], len(plan["refs"]))]
        processed = 0
        try:
            async with relay_class(Path(plan["config_path"])) as relay:
                catalog = await relay.session.list_tools()
                reader.write_exclusive(output / "raw" / f"lane-{number}-tools.json",
                    {"neutral": neutral, "observed_at": time.time(), "response": catalog.model_dump(mode="json", by_alias=True, exclude_none=False)})
                reader.need("download_from_romeo" in {tool.name for tool in catalog.tools}, "Verified download tool absent")
                for ordinal, (index, ref) in enumerate(assigned):
                    processed = ordinal + 1
                    local = output / "files" / f"{index:05d}.bin"
                    arguments = {"remote_path": ref["path"], "local_path": str(local), "verify": True}
                    stage = "before_rpc"
                    try:
                        reader.need(not local.exists(), "Download destination already exists")
                        stage = "rpc"
                        result = await relay.session.call_tool("download_from_romeo", arguments)
                        observed_at = time.time()
                        stage = "serialization"
                        response = result.model_dump(mode="json", by_alias=True, exclude_none=False)
                        wrapper = {"schema": "hpc-forest-primary-tool-observation-v1", "tool": "mcp__romeo__download_from_romeo",
                                   "arguments": arguments, "observed_at": observed_at, "response": response}
                        if neutral:
                            wrapper["neutral"] = True
                        raw = reader.write_exclusive(output / "raw" / f"{index:05d}.json", wrapper)
                        stage = "verification"
                        actual = verify_download(reader, ref, local, arguments, response)
                        entry = {"remote_ref": ref, "local_ref": actual, "transfer_receipt": raw}
                        reader.write_exclusive(output / "catalog" / f"{index:05d}.json", entry)
                        entries.append((index, entry))
                    except asyncio.CancelledError:
                        failure(f"{index:05d}.json", {"remote_ref": ref, "stage": stage, "cancelled": True,
                            "rpc_completion_unknown": stage == "rpc", "no_tool_result_fabricated": True})
                        raise
                    except Exception as exc:  # noqa: BLE001 -- preserve any real SDK/verification failure without retry.
                        failure(f"{index:05d}.json", {"remote_ref": ref, "stage": stage, "error_type": type(exc).__name__,
                            "reason": str(exc)[:1000], "rpc_completion_unknown": stage == "rpc", "no_tool_result_fabricated": True})
        except Exception as exc:  # noqa: BLE001 -- a failed context must leave a dated refusal and partial catalog.
            failure(f"lane-{number}.json", {"error_type": type(exc).__name__, "reason": str(exc)[:1000],
                "unattempted_refs": [item[1] for item in assigned[processed:]], "no_tool_result_fabricated": True})
    tasks = [asyncio.create_task(lane(i)) for i in range(min(plan["lanes"], len(plan["refs"])))]
    try:
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for number, outcome in enumerate(outcomes):
            if isinstance(outcome, BaseException):
                failure(f"lane-{number}-interrupted.json", {"error_type": type(outcome).__name__,
                    "rpc_completion_unknown": True, "no_tool_result_fabricated": True})
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        failure("run-interrupted.json", {"rpc_completion_unknown": True, "no_tool_result_fabricated": True})
        raise
    finally:
        catalog_ref = reader.write_exclusive(output / "CATALOG.json", [entry for _index, entry in sorted(entries)])
        receipt = reader.write_exclusive(output / "RECEPTION.json", {"schema": "hpc-forest-parallel-readonly-reception-v1",
            "verified": not neutral and not failures and len(entries) == len(plan["refs"]), "neutral": neutral,
            "requested": len(plan["refs"]), "received": len(entries), "contexts_maximum": plan["lanes"],
            "catalog": catalog_ref, "failures": failures, "no_retry": True, "remote_mutation_or_model_call": False})
    if any(isinstance(outcome, BaseException) for outcome in outcomes):
        raise asyncio.CancelledError("Interrupted lane; preserved receipts must be inspected, never retried")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--receive", action="store_true")
    args = parser.parse_args(argv)
    reader = runtime()
    path = reader.ordinary(args.input)
    reader.need(reader.sha(path.read_bytes()) == args.input_sha256, "Sealed receive input changed")
    plan = reader.parse(path.read_bytes())
    if args.receive:
        ref = asyncio.run(receive(plan, reader))
        status = reader.parse(Path(ref["path"]).read_bytes())["verified"]
    else:
        output = validate_plan(reader, plan)
        output.mkdir(parents=True, exist_ok=False)
        ref = reader.write_exclusive(output / "PREPARE.json", {"verified": False, "prepared_only": True,
            "input_sha256": args.input_sha256, "contexts_started": 0, "network_called": False})
        status = True
    print(json.dumps(ref))
    return 0 if status else 1


if __name__ == "__main__":
    raise SystemExit(main())
