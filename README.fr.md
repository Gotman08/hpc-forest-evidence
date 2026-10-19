# HPC Forest · Preuves et évaluation

_Protocole public et observations vérifiables sur l’optimisation de programmes._

[English](README.md) · [Protocole](docs/PROTOCOLE.fr.md) · [Résultats](docs/RESULTS.md) · [Vérification](docs/REPRODUCIBILITY.md)

## Données reçues et article · 19 octobre 2026

L’édition r5 courante de l’[article de recherche](docs/article/ARTICLE.pdf) et des [annexes techniques](docs/article/ANNEXES-TECHNIQUES.pdf) intègre les observations R2 reçues dans le résumé, la section 3.9 et l’annexe L, avec trois nouvelles figures R1/R2. L’[article en HTML](docs/article/ARTICLE.html), les [annexes en HTML](docs/article/ANNEXES-TECHNIQUES.html) et les [données numériques](docs/article/donnees-r1-r2/comparison.json) sont disponibles, avec un arrêté des sources au 19 octobre 2026 à 11:40:35,931 UTC. Le jeu couvre 60 cellules R1 historiques et une cellule R2 dont les temps finaux sont confirmés par les sources ; 59 cellules R2 n’ont pas de mesure scientifique. Il contient **zéro gain R2 scientifiquement admis et zéro paire R1/R2 admise**. Les comparaisons de temps et de coûts sont descriptives : les recherches diffèrent et la pause d’audit a consommé le budget de temps existant.

L’[article r4 exact (19 pages)](docs/article/history/r4/ARTICLE.pdf), les [annexes r4 (308 pages)](docs/article/history/r4/ANNEXES-TECHNIQUES.pdf), leurs sources et les 275 figures d’origine restent disponibles à leur arrêté technique de 08:40 UTC. L’[inventaire historique](evidence/received-2026-10-19/README.md) conserve l’ensemble des mesures historiques admises, confirmations, registres de recherche et projections des coûts réconciliés. Son arrêté scientifique reste le 18 octobre 2026 à 05:03:23.898140 UTC.

L’[inventaire r4 et sa provenance](evidence/received-2026-10-19-r4/README.md), séparés, décrivent l’état opérationnel reçu et la [matrice de soixante cellules](evidence/received-2026-10-19-r4/matrix15.csv) : quinze sujets × quatre modèles en MAX, graine 23. Onze gains R1 mesurés à zéro conservent le programme de référence (speedup 1) ; tous les résultats R2 restent `NA`, sans aucune paire R1/R2. Les transports échoués et la validation locale n’ajoutent aucun résultat scientifique ; A4 reste une préparation à cet arrêté.

La paire de programmes Sol MAX sur les nombres premiers a été remesurée sur une allocation distincte : 43,8546 ms pour la référence contre 4,9124 ms pour le candidat (8,9273×), douze entrées certifiées et cinq paires de mesures. La portée reste ce benchmark fini et la même implémentation de l’évaluateur. Les échecs et les coûts inconnus restent distingués. Voir les [observations actualisées et la suite de campagne](docs/RECEIVED-2026-10-19.md).

La [qualification des quinze références sans modèle](evidence/qualification-2026-10-19/README.md) est également reçue et vérifiée : 75 durées de confirmation issues d'une allocation ARM de 65 secondes. Ces mesures de référence ne constituent aucun résultat de modèle R2 ni gain d'optimisation.

Le [premier lot natif R2](evidence/native-first-batch-2026-10-19/README.md), avec un arrêté à 11:11:41,348 UTC, décrit Luna MAX sur 2020-quicksort : trois durées initiales de recherche, une référence contemporaine, deux appels livrés et 32 765 jetons exacts. L’audit privé CLI et l’acceptation ARM de la libération sont reçus. Cet instantané initial daté ne contient aucune confirmation finale ni gain scientifique admis. Ses octets et l’instantané r4 antérieur restent inchangés ; l’article courant ajoute séparément les cinq plus cinq temps finaux confirmés par les sources, sans les présenter comme preuve indépendante de performance.

Le [supplément d’incidents techniques](evidence/native-incidents-2026-10-19/README.md), observé à 12:34:58,457867 UTC, consigne séparément l’échec Sol/count avant tout appel modèle et l’allocation Astra/count échouée après deux appels annoncés par les sources, pour 30 919 jetons exacts annoncés. Le modèle et l’effort MAX restent des métadonnées déclarées ; aucun audit privé CLI indépendant n’est revendiqué pour Astra. L’inventaire distingue une cellule avec temps finaux confirmés par les sources, deux cellules avec incident et 57 cellules non lancées, soit 59 mesures comparatives incluses manquantes et zéro paire admise. L’article r5 et son jeu numérique figé restent inchangés.

HPC Forest étudie une question concrète : **un système peut-il produire des programmes corrects et plus rapides dans un budget fixé ?** L’évaluation repose sur un programme de départ figé, un contrôle externe des sorties, des temps bruts et une confirmation finale séparée. Un autre système peut suivre ce contrat sans exposer son fonctionnement interne.

Ce dépôt rassemble le protocole, une sélection explicite de données auditées et des vérificateurs publics. Le moteur interne et les entrées réservées à l’évaluateur restent hors de ce dépôt.

## Résultats disponibles

| Expérience | Observation | Portée |
| --- | --- | --- |
| Contrôleur, séries de huit cycles | 8,740 → 6,487 ms/cycle, soit **25,78 % de temps en moins** | Réponses et scores synthétiques fixes |
| Contrôleur, séries de 32 cycles | 10,133 → 7,499 ms/cycle, soit **25,99 % de temps en moins** | Même expérience de surcoût |
| N-body, 4 096 corps, exécutable figé | **14,38×** entre un et seize cœurs physiques accessibles | Montée en cœurs d’un programme déjà sélectionné |
| Trois autres grands cas CPU | **1,02× à 1,06×** | Courbes presque plates dans la même allocation |

Les [temps bruts](evidence/README.md) et les [calculs](evidence/results.json) sont publiés. Le contrôleur et les courbes CPU appartiennent à deux expériences différentes ; les secondes ne démontrent pas l’utilité du changement de contrôleur. Aucun gain sur la qualité des programmes issus de cette nouvelle comparaison ou sur l’apprentissage des poids n’est encore établi.

## Recalculer les chiffres

Python **3.11 ou plus récent** suffit, sans dépendance pour les contrôles :

```bash
git clone https://github.com/Gotman08/hpc-forest-evidence.git
cd hpc-forest-evidence
python -m tools.verify
python -m unittest discover -s tests -v
```

Le vérificateur contrôle les empreintes, les liens locaux, la couverture et les calculs de **144 séries / 2 400 cycles mesurés** du contrôleur et **200 temps CPU / 40 configurations**, ainsi que les **60 cellules et 26 temps** de la comparaison courante. Il ne lance aucun modèle ou programme mesuré. Le recalcul public ne reproduit pas l’exécution d’origine, dont les binaires et les entrées protégées ne sont pas distribués. Les [limites de reproduction](docs/REPRODUCIBILITY.md) sont explicites.

## Comparer un autre système

Le [protocole français](docs/PROTOCOLE.fr.md) décrit les budgets, la compilation, les sorties exactes, les répétitions, la confirmation et les états négatifs. Les [gabarits](templates/README.md) sont vierges : ils ne contiennent pas de résultats inventés. Le [guide de comparaison](docs/COMPARING.md) explique comment préparer une expérience neuve et transmettre les preuves sans dévoiler l’architecture du système.

## Documentation et statut

- [Résultats et interprétation](docs/RESULTS.md)
- [Protocole complet](docs/PROTOCOL.md)
- [Reproduction et provenance](docs/REPRODUCIBILITY.md)
- [Limites scientifiques](docs/LIMITATIONS.md)
- [Travaux restant à réaliser](docs/ROADMAP.md)
- [Contribuer](CONTRIBUTING.md)

Première version **0.1.0**, 16 octobre 2026 ; les données reçues et l’article r5 du 19 octobre s’y ajoutent dans la révision courante. La suite porte sur quinze sujets et quatre modèles, tous en MAX, après le pilote nombres premiers et la qualification des références terminés. L’article courant distingue une cellule R2 confirmée par les sources des 59 cellules sans mesure et des comparaisons scientifiquement admises, dont le nombre reste zéro. Auteurs : **Nicolas Marano et Romain Despoullain**. La [licence MIT](LICENSE) couvre les fichiers originaux de cette publication ; les programmes et énoncés tiers ne sont pas redistribués. Pour citer les observations, utiliser [CITATION.cff](CITATION.cff) avec la révision exacte.
