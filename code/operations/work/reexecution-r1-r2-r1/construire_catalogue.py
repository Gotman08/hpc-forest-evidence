"""Preserve two exact private snapshots and their associated historical records."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
OUTPUT = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r1"
R1 = Path("C:/Users/nicol/Documents/Codex/2026-10-15/cr/outputs/HPC-Forest-Harnais-Comparaison-r1")
R2 = BASE / "outputs/HPC-Forest-Matrice15-Admission-r2"
STATICS = BASE / "outputs/HPC-Forest-Matrice15-Operation-Preparation-r2"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(relative, raw):
    target = OUTPUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
    return {"path": relative, "sha256": sha(raw)}


def copy(relative, source):
    return put(relative, source.read_bytes())


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = json.loads((R1 / "manifest-source-derivee.json").read_bytes())
    r1_manifest = original["files"]
    r2_manifest = json.loads((R2 / "RUNTIME-PRIVE-LOCAL.json").read_bytes())
    files = {}
    files["r1-source"] = copy("archives/R1-Harnais-Comparaison-9a68a83f.zip", R1 / "HPC-Forest-Harnais-Comparaison-r1.zip")
    files["r2-source"] = copy("archives/R2-Matrice15-b79e6fdc.zip", R2 / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip")
    if files["r1-source"]["sha256"] != "9a68a83fde4acb6bd247d79e00490e7d36f0c4c59c6c881152101e4c499387eb" or files["r2-source"]["sha256"] != "b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4":
        raise RuntimeError("Archive source inattendue")
    r1_runtime = put("manifestes/R1-runtime-94.json", (json.dumps(r1_manifest, sort_keys=True, indent=2) + "\n").encode())
    r2_runtime = copy("manifestes/R2-runtime-127.json", R2 / "RUNTIME-PRIVE-LOCAL.json")
    associated = {"r1": [], "r2": []}
    for name in ("manifest-source-derivee.json", "plan-comparaison.json", "reference-r1-matrix-plan.json", "PREPARATION-VERIFIEE.json", "PROTOCOLE.md"):
        associated["r1"].append(copy("documents/R1/" + name, R1 / name))
    for name in ("REVISION-ADMISSION-SANS-CYCLE.json", "PROTOCOLE-60-CELLULES-PILOTE-UNIQUE.json", "VALIDATION-LOCALE.json"):
        associated["r2"].append(copy("documents/R2/" + name, R2 / name))
    for name in ("STATICS.json", "STATIC-ARTIFACTS-ARM.json", "STATIC-ARTIFACTS-WINDOWS.json", "DEPLOIEMENT-STATIQUE.json"):
        associated["r2"].append(copy("documents/R2/operation-r2-" + name, STATICS / name))
    static_refs = json.loads((STATICS / "STATICS.json").read_bytes())["artifacts"]
    for key, name in (("plan", "PLAN-NATIF-60-v2.json"), ("artifact_aliases", "ALIAS-STATIQUES-v2.json")):
        source = Path(static_refs[key]["path"])
        if sha(source.read_bytes()) != static_refs[key]["sha256"]:
            raise RuntimeError("Document statique modifie")
        associated["r2"].append(copy("documents/R2/" + name, source))
    entries = {
        "r1-harnais-9a68": {
            "label": "R1 historique : snapshot du moteur de comparaison conservant les references R1",
            "source_snapshot_role": "harness-comparison derivative, not a claim that every historical R1 result used this exact source",
            "source_zip": files["r1-source"], "runtime_manifest": r1_runtime, "source_file_count": len(r1_manifest),
            "original_source_zip": str(R1 / "HPC-Forest-Harnais-Comparaison-r1.zip"),
            "original_manifest": {"path": str(R1 / "manifest-source-derivee.json"), "sha256": sha((R1 / "manifest-source-derivee.json").read_bytes())},
            "source_base_sha256_recorded_in_historical_manifest": original["base_source_sha256"],
            "associated_plan_scope": "hpc-forest-harness-comparison-20261016-r1",
            "historical_reference_scope": "hpc-forest-archives-2020-2024-mother-r1",
            "associated_records": associated["r1"],
        },
        "r2-matrice15-b79": {
            "label": "R2 courant : moteur natif Matrice15, pilote unique puis quatre modeles MAX",
            "source_snapshot_role": "native matrix15 source with acyclic plan v2 admission",
            "source_zip": files["r2-source"], "runtime_manifest": r2_runtime, "source_file_count": len(r2_manifest),
            "original_source_zip": str(R2 / "HPC-FOREST-MATRIX15-ADMISSION-r2.zip"),
            "original_manifest": {"path": str(R2 / "RUNTIME-PRIVE-LOCAL.json"), "sha256": sha((R2 / "RUNTIME-PRIVE-LOCAL.json").read_bytes())},
            "associated_plan_scope": "hpc-forest-matrix15-native-max-r2",
            "associated_records": associated["r2"],
        },
    }
    catalogue = {"schema": "hpc-forest-private-r1-r2-reexecution-catalogue-v1", "private_local_only": True,
        "selection_rule": "Select the exact source SHA from the actual campaign/result receipt; directory r1/r2 labels are insufficient",
        "all_other_historical_variants_preserved": True, "editions": entries}
    catalogue_ref = put("CATALOGUE.json", (json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n").encode())
    for key, manifest in (("r1-source", r1_manifest), ("r2-source", r2_manifest)):
        with zipfile.ZipFile(OUTPUT / files[key]["path"]) as archive:
            actual = {name.removeprefix("HPC-Forest/"): sha(archive.read(name)) for name in archive.namelist()}
        if actual != manifest:
            raise RuntimeError("Archive et manifeste divergents")
    copy("preparer_copie.py", ROOT / "preparer_copie.py")
    print(json.dumps({"catalogue": catalogue_ref, "counts": {key: value["source_file_count"] for key, value in entries.items()}}))


if __name__ == "__main__":
    main()
