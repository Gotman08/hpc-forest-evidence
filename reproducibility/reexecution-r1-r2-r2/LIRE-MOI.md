# Restaurer séparément le vrai R1, sa dérivée de comparaison et R2

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
