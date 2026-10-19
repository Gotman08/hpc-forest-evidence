"""Build a new private source-reexecution package from exact existing bytes."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
OLD = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r1"
NEW = BASE / "outputs/HPC-Forest-Reexecution-R1-R2-r2"
SOURCE = Path(r"C:\Users\nicol\Documents\Codex\2026-10-15\cr\outputs\HPC-Forest-Etude-2020-2024-r1")
EXPECTED = "cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18"


def raw_ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def package_ref(path):
    value = raw_ref(path)
    return {"path": path.relative_to(NEW).as_posix(), "sha256": value["sha256"]}


def copy_exact(source, destination):
    before = raw_ref(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert not destination.exists()
    shutil.copy2(source, destination)
    assert raw_ref(destination)["sha256"] == before["sha256"] == raw_ref(source)["sha256"]
    return before


def main():
    assert not NEW.exists()
    verification_path = Path(__file__).with_name("VERIFICATION-ARCHIVE-R1-CD769.json")
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    assert verification["sha256_verified"] and verification["archive_safety"]["safe_names_and_types"]
    assert verification["source"]["sha256"] == EXPECTED and verification["regular_files"] == 90
    NEW.mkdir()
    for name in ("archives", "manifestes", "documents"):
        shutil.copytree(OLD / name, NEW / name)
    (NEW / "verifications").mkdir()
    exact_zip = NEW / "archives/R1-Resultats-748259-cd769d47.zip"
    original = copy_exact(Path(verification["source"]["path"]), exact_zip)
    runtime = {name.removeprefix("HPC-Forest/"): value["sha256"] for name, value in verification["files"].items()}
    assert len(runtime) == 90
    manifest = NEW / "manifestes/R1-runtime-exact-cd769-90.json"
    write(manifest, runtime)
    direct = NEW / "documents/R1-resultats-748259"
    direct.mkdir()
    originals = {}
    for source_name, dest_name in (("runs/coverage-gpt-6-luna-max/autorisation.json", "autorisation-originale.json"),
                                   ("runs/coverage-gpt-6-luna-max/submission.json", "submission-originale.json"),
                                   ("runs/coverage-gpt-6-luna-max/audit.json", "audit-original.json"),
                                   ("matrix-plan.json", "matrix-plan-original.json"),
                                   ("integrite-source-active-verifiee.json", "integrite-source-active-originale.json")):
        destination = direct / dest_name
        originals[dest_name] = {"original": copy_exact(SOURCE / source_name, destination), "package": package_ref(destination)}
    reference = SOURCE.parent / "HPC-Forest-Harnais-Comparaison-r1/contrats-reference.json"
    copy_exact(reference, direct / "contrats-reference-comparaison-fd36.json")
    assert raw_ref(direct / "contrats-reference-comparaison-fd36.json")["sha256"] == "fd36a6c9bdd35845834053d92b83fa58c688c02f0b6443b7a2edfded96956bdf"
    contract = SOURCE / "runs/coverage-gpt-6-luna-max/preuves/results-748259/2020-quicksort/trusted/contract.json"
    if contract.is_file():
        copy_exact(contract, direct / "contrat-748259-2020-quicksort.json")
    copy_exact(verification_path, NEW / "verifications/LOCALISATION-ARCHIVE-R1-CD769.json")
    catalogue = json.loads((OLD / "CATALOGUE.json").read_text(encoding="utf-8"))
    catalogue["schema"] = "hpc-forest-private-r1-r2-reexecution-catalogue-v2"
    catalogue["primary_r1_edition"] = "r1-resultats-748259-cd769"
    catalogue["catalogue_predecessor_preserved"] = raw_ref(OLD / "CATALOGUE.json")
    old_editions = catalogue["editions"]
    catalogue["editions"] = {"r1-resultats-748259-cd769": {
        "label": "R1 reel : archive source liee au groupe Luna MAX job748259",
        "source_snapshot_role": "Exact source ZIP referenced by the actual coverage-gpt-6-luna-max authorization and job748259 submission; no attribution beyond this verified cohort",
        "source_zip": package_ref(exact_zip), "runtime_manifest": package_ref(manifest), "source_file_count": 90,
        "original_source_zip": original, "runtime_manifest_origin": "Complete90-file inventory computed by reading the exact byte-pinned ZIP; no source import or extraction",
        "associated_plan_scope": "hpc-forest-archives-2020-2024-mother-r1",
        "verified_cohort": {"run_name": "coverage-gpt-6-luna-max", "job_id": "748259", "model": "gpt-6-luna", "effort": "max", "session_id": "c08531b8446a447bacb06c4500c0c033"},
        "associated_records": [value["package"] for value in originals.values()],
        "historical_documents_are_not_current_execution_authorizations": True,
    }, **old_editions}
    incident_source = BASE / "outputs/HPC-Forest-Matrice15-Execution-root-03/suivi-lecture-r1"
    incident_destination = NEW / "documents/R2-incident-transport-755862"
    incident_destination.mkdir()
    incident_records = []
    for name, expected in (("SYNTHESE-CAUSE-r1.json", "61d64f8a12eb2ac3764e46bb944882c36f27351a76e0e9ec31665c1bebd3c37f"),
                           ("RAPPORT-COURT-r1.md", None),
                           ("ANCESTORS-CORROBORATION-r1.json", "b61f20435598e1a1e729ae2db0aa55997ec03266a0dc35d4d0be77b6a9889549")):
        source_path = incident_source / name
        if expected is not None:
            assert raw_ref(source_path)["sha256"] == expected
        copy_exact(source_path, incident_destination / name)
        incident_records.append(package_ref(incident_destination / name))
    catalogue["editions"]["r2-matrice15-b79"]["received_incident_records"] = incident_records
    catalogue["editions"]["r2-matrice15-b79"]["future_transport_helper_integrated"] = False
    write(NEW / "CATALOGUE.json", catalogue)
    restorer = (OLD / "preparer_copie.py").read_text(encoding="utf-8")
    assert restorer.count("PINS = {") == 1
    restorer = restorer.replace("PINS = {", 'PINS = {\n    "r1-resultats-748259-cd769": "' + EXPECTED + '",', 1)
    assert restorer.count("hpc-forest-private-r1-r2-reexecution-catalogue-v1") == 1
    restorer = restorer.replace("hpc-forest-private-r1-r2-reexecution-catalogue-v1", "hpc-forest-private-r1-r2-reexecution-catalogue-v2")
    with (NEW / "preparer_copie.py").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(restorer)
    guide = """# Restaurer séparément le vrai R1, sa dérivée de comparaison et R2

Ce paquet local privé conserve trois archives source distinctes et leur inventaire complet. Il succède au paquet `HPC-Forest-Reexecution-R1-R2-r1`, qui reste intact. Les données et PDF de l'article publiés sur le dépôt ne transforment pas ces archives privées en code publié.

| Édition | Rôle exact | Fichiers | SHA du ZIP |
|---|---|---:|---|
| `r1-resultats-748259-cd769` | **R1 réel**, archive référencée par l'autorisation du groupe Luna MAX `coverage-gpt-6-luna-max` et sa soumission du job `748259` | 90 | `cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18` |
| `r1-harnais-9a68` | Dérivée historique de comparaison, distincte du code attribué au job `748259` | 94 | `9a68a83fde4acb6bd247d79e00490e7d36f0c4c59c6c881152101e4c499387eb` |
| `r2-matrice15-b79` | Moteur natif Matrice15 R2, conservé avec ses incidents réels | 127 | `b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4` |

Le choix primaire pour le R1 du job `748259` est désormais `r1-resultats-748259-cd769`. L'autorisation, la soumission, le plan, l'audit et le reçu historique d'intégrité sont copiés à l'identique dans `documents/R1-resultats-748259/`. Ils établissent cette cohorte Luna MAX, session `c08531b8446a447bacb06c4500c0c033`. Le même SHA cité dans d'autres documents ne suffit pas à attribuer cette archive à tous les résultats historiques : il faut vérifier le reçu propre au résultat concerné.

Le manifeste complet de 90 fichiers du vrai R1 est calculé en lisant son ZIP exact, sans exécuter ni reconstruire son code. Les inventaires originaux de la dérivée R1 à 94 fichiers et de R2 à 127 fichiers sont conservés byte à byte. Le manifeste R2 original reste `91684ae8d3d0457d81d049bf6e096c02601fdbdc67fc762fdf697bdc23c35f2b`. Les contrats de référence de comparaison `fd36a6c9…` sont un document de liaison ultérieur, distinct de l'autorisation source originale.

## Vérifier ou restaurer le code

`preparer_copie.py` utilise seulement la bibliothèque standard. Il vérifie le SHA du ZIP, son inventaire complet, chaque membre, les types et chemins ; il refuse les liens, jonctions, doublons et destinations existantes. Il relit ensuite la copie. Il ne lance aucun code du projet, test scientifique, modèle, transfert ou job.

```powershell
$py = 'C:/Users/nicol/Documents/Codex/2026-10-15/cr/work/.venv/Scripts/python.exe'
$outil = 'C:/Users/nicol/Documents/Codex/2026-10-19/je-voudrais-que-tu-commit-et/outputs/HPC-Forest-Reexecution-R1-R2-r2/preparer_copie.py'

& $py -I -B $outil --edition r1-resultats-748259-cd769 --verify-only
& $py -I -B $outil --edition r1-harnais-9a68 --verify-only
& $py -I -B $outil --edition r2-matrice15-b79 --verify-only

# Le parent existe déjà et chaque destination est neuve.
& $py -I -B $outil --edition r1-resultats-748259-cd769 --destination 'C:/chemin/existant/R1-748259-copie-neuve'
& $py -I -B $outil --edition r1-harnais-9a68 --destination 'C:/chemin/existant/R1-comparaison-copie-neuve'
& $py -I -B $outil --edition r2-matrice15-b79 --destination 'C:/chemin/existant/R2-copie-neuve'
```

Chaque destination contient `project/` et un reçu `RESTAURATION.json`. Une restauration interrompue est conservée ; choisir alors une autre destination. Le reçu atteste les octets restaurés et n'autorise aucune campagne.

## Refaire des tests locaux

Dans le `project/` choisi, les commandes de tests utilisent le venv existant et `-o pythonpath=src` pour sélectionner cette copie plutôt qu'un autre checkout éditable. Les tests de moteur ne sont pas exécutés lors de la fabrication de ce paquet.

```powershell
# Pour les tests R2 utilisant sa préparation certifiée externe :
$env:R2MAX_CERTIFIED_PACKAGE = 'C:/Users/nicol/Documents/Codex/2026-10-15/cr/outputs/HPC-Forest-Primes-Natif-Relance-r2g/qualification-zero-modele-r1/paquet-source-lie-r1/certified-preparation'
$testTemp = Join-Path (Split-Path -Parent (Get-Location).Path) ('pytest-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $testTemp) { throw 'Le dossier de tests doit etre neuf' }
& $py -I -B -m pytest -q -p no:cacheprovider -o pythonpath=src --basetemp=$testTemp
& $py -I -B -m ruff check src tests --no-cache
```

Les dépendances, compilateurs, erreurs et éventuels skips restent ceux du test réellement effectué. Un ancien rapport de tests copié ici conserve sa date et son contexte historiques.

## Expériences HPC et incident R2

R2 conserve le code source `b79…`. Le diagnostic du job Astra MAX `755862` corrobore une publication de READY avant les métadonnées process et delivered attendues. Les trois reçus de contexte reçus et copiés à l'identique sont dans `documents/R2-incident-transport-755862/`. Le tar terminal privé a été pris après la clôture : il n'est pas présenté comme un instantané exact à l'instant de l'exception. Cet incident de transport n'est pas corrigé à l'intérieur de l'archive. Le helper de transport envisagé pour une suite n'y est pas intégré ; une correction future doit recevoir sa propre version et son propre SHA. Restaurer R2 reproduit donc cet instantané avec ses limites connues.

Les identifiants de campagne, job, session, cache et mailbox, les claims déjà commencées, les budgets et les échéances des preuves historiques ne se rejouent pas. Aucun document copié ici n'est une autorisation actuelle. Pour une nouvelle expérience, préparer une nouvelle campagne avec des identités neuves et une filiation explicite, fixer source/plan/contrats/évaluateur, refaire ses qualifications et admissions, puis recevoir et auditer les résultats. Si le code scellé exige des anciennes identités ou échéances, créer une nouvelle dérivée contrôlée plutôt que modifier l'archive historique.

La consigne de la campagne active reste un seul pilote nombres premiers validé, puis quinze sujets avec quatre modèles en MAX, sous les admissions correspondantes. Ce paquet de restauration ne relance rien.
"""
    with (NEW / "LIRE-MOI.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(guide)
    write(NEW / "PROVENANCE-PAQUET.json", {"schema": "hpc-forest-private-source-package-provenance-v2", "private_local_only": True,
          "predecessor_preserved": str(OLD), "exact_r1_zip_original": original, "direct_cohort_records": originals,
          "source_code_executed": False, "source_recreated": False, "old_campaign_authorized_to_replay": False,
          "future_transport_helper_integrated": False, "network_calls": 0, "model_calls": 0, "jobs_submitted": 0})
    print(json.dumps({"package": str(NEW), "catalogue": raw_ref(NEW / "CATALOGUE.json"), "guide": raw_ref(NEW / "LIRE-MOI.md"), "source_file_counts": [90, 94, 127]}))


if __name__ == "__main__":
    main()
