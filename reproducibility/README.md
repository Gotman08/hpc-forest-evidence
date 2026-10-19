# Sauvegarde complète et restauration

Cette publication répond à la demande du propriétaire d'inclure l'ensemble du code et des données disponibles, au-delà des projections scientifiques auparavant publiées. Elle conserve les sources, scripts, tests et fixtures, variantes historiques, archives reçues, résultats bruts, registres, journaux, échecs, préparations, articles, annexes, figures et documents d'origine des deux workspaces HPC-Forest inventoriés.

Les [sources R1/R2 et outils principaux](../code/README.md) sont aussi consultables directement. Le [guide historique exact](reexecution-r1-r2-r2/LIRE-MOI.md), les trois archives de sources et leurs manifestes restent disponibles sans réécriture des preuves anciennes. Un ancien champ « privé » décrit l'état lors de sa création ; la présente publication autorisée lui succède.

## Vérifier la capture

Depuis la racine du dépôt, avec Python 3.11 ou plus récent :

```bash
python -m tools.full_snapshot verify
```

L'[inventaire intégral](../archive/full-2026-10-19/INVENTORY.json) référence des catalogues paginés par empreinte. Chaque chemin d'origine est associé à une racine logique et au SHA-256 du fichier. Les fichiers identiques partagent un objet, sans perdre leurs chemins. Les gros objets sont répartis en morceaux d'au plus 40 Mio, avec empreintes de chaque morceau et du fichier complet. Cela conserve les grands archives et jeux d'entrée sans dépendance Git LFS.

La vérification lit les données sans réseau, modèle, compilation ou exécution d'un programme archivé. Elle refuse les chemins dangereux, liens actifs, morceaux absents ou modifiés, objets orphelins et compteurs incohérents.

Le corpus a été collecté fichier par fichier dans les workspaces en pause, avec contrôle des métadonnées de chaque fichier et vérification des contenus capturés. Il ne constitue pas un instantané atomique du système de fichiers. Les horodatages, permissions, installations logicielles et comptes d'origine ne sont pas recréés par la restauration.

## Restaurer dans un nouveau dossier

Le dossier parent doit exister et la destination doit être absente :

```bash
python -m tools.full_snapshot restore --destination /chemin/absolu/nouveau-dossier
```

Sous Windows, utiliser par exemple `C:/Travail/HPC-Forest-restaure`, avec `C:/Travail` déjà présent. Pour choisir une racine logique, ajouter `--root-id current-outputs` ou un autre identifiant de l'inventaire ; plusieurs options peuvent être données.

Le restaurateur vérifie d'abord la capture, puis réécrit les fichiers dans des sous-dossiers portant les identifiants logiques. Il refuse une destination existante et ne modifie pas les originaux. Les liens sont conservés comme descripteurs dans `LINKS.json`, sans activation. Une opération échouée laisse son dossier partiel à examiner ; elle ne supprime ni ne remplace de fichiers.

Les métadonnées Git embarquées sont des preuves historiques, conservées comme les autres données. Les chemins absolus, caches de worker, commandes, hooks et identifiants de job éventuellement présents dans les matériaux restaurés ne sont pas automatiquement portables ni autorisés à être rejoués.

## Périmètre et exclusions

Les fichiers d'authentification et identifiants d'accès réels ne sont pas publiés. Les environnements Python installés, exécutables Codex tiers copiés et caches techniques recensés sont exclus ; les scripts, spécifications de dépendances et fixtures synthétiques restent conservés. Les exclusions sont inventoriées avec leur motif. Aucun autre projet personnel ni profil utilisateur n'est parcouru par ce périmètre.

Le contrôle couvre aussi les archives imbriquées et les objets Git historiques. Un fichier ou conteneur contenant un identifiant réel reste privé dans son état d'origine : ses copies sont exclues par SHA-256, sans réécrire les preuves primaires. Le reçu de filtrage distingue cette exclusion des fixtures contenant des valeurs neutres.

Les matériaux tiers gardent leurs notices et conditions : voir [NOTICE](../NOTICE.md). Les anciens fichiers et les PDF figés ne sont pas réécrits pour modifier une licence ou leur statut scientifique.

## État de la recherche

Les essais restent en pause. Restaurer, vérifier et publier ne lance aucune campagne. La matrice native conserve une cellule avec temps finaux annoncés par les sources, deux incidents et 57 cellules non lancées, ainsi que zéro paire R1/R2 scientifiquement admise. L'intégralité des fichiers reçus n'implique pas que la campagne soit terminée ou que tous les résultats aient été validés.

Pour préparer une nouvelle expérience après reprise explicite, distinguer les trois éditions de code et créer de nouveaux identifiants, dossiers et budgets. La restauration ne renouvelle aucun ancien délai et ne réactive aucune autorisation consommée. Les cas rendus publics ne constituent plus des cas inconnus pour une future confirmation.
