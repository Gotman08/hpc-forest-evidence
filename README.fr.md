# HPC Forest · Preuves et évaluation

_Protocole public et observations vérifiables sur l’optimisation de programmes._

[English](README.md) · [Protocole](docs/PROTOCOLE.fr.md) · [Résultats](docs/RESULTS.md) · [Vérification](docs/REPRODUCIBILITY.md)

HPC Forest étudie une question concrète : **un système peut-il produire des programmes corrects et plus rapides dans un budget fixé ?** L’évaluation repose sur un programme de départ figé, un contrôle externe des sorties, des temps bruts et une confirmation finale séparée. Un autre système peut suivre ce contrat sans exposer son fonctionnement interne.

Ce dépôt rassemble le protocole, une sélection explicite de données auditées et des vérificateurs publics. Le moteur interne et les entrées réservées à l’évaluateur restent hors de ce dépôt.

## 📊 Résultats disponibles

| Expérience | Observation | Portée |
| --- | --- | --- |
| Contrôleur, séries de huit cycles | 8,740 → 6,487 ms/cycle, soit **25,78 % de temps en moins** | Réponses et scores synthétiques fixes |
| Contrôleur, séries de 32 cycles | 10,133 → 7,499 ms/cycle, soit **25,99 % de temps en moins** | Même expérience de surcoût |
| N-body, 4 096 corps, exécutable figé | **14,38×** entre un et seize cœurs physiques accessibles | Montée en cœurs d’un programme déjà sélectionné |
| Trois autres grands cas CPU | **1,02× à 1,06×** | Courbes presque plates dans la même allocation |

Les [temps bruts](evidence/README.md) et les [calculs](evidence/results.json) sont publiés. Le contrôleur et les courbes CPU appartiennent à deux expériences différentes ; les secondes ne démontrent pas l’utilité du changement de contrôleur. Aucun gain sur la qualité des programmes issus de cette nouvelle comparaison ou sur l’apprentissage des poids n’est encore établi.

## ✅ Recalculer les chiffres

Python **3.11 ou plus récent** suffit, sans dépendance pour les contrôles :

```bash
git clone https://github.com/Gotman08/hpc-forest-evidence.git
cd hpc-forest-evidence
python -m tools.verify
python -m unittest discover -s tests -v
```

Le vérificateur contrôle les empreintes, les liens locaux, la couverture et les calculs de **144 séries / 2 400 cycles mesurés** du contrôleur et **200 temps CPU / 40 configurations**. Il ne lance aucun modèle ou programme mesuré. Le recalcul public ne reproduit pas l’exécution d’origine, dont les binaires et les entrées protégées ne sont pas distribués. Les [limites de reproduction](docs/REPRODUCIBILITY.md) sont explicites.

## 🧪 Comparer un autre système

Le [protocole français](docs/PROTOCOLE.fr.md) décrit les budgets, la compilation, les sorties exactes, les répétitions, la confirmation et les états négatifs. Les [gabarits](templates/README.md) sont vierges : ils ne contiennent pas de résultats inventés. Le [guide de comparaison](docs/COMPARING.md) explique comment préparer une expérience neuve et transmettre les preuves sans dévoiler l’architecture du système.

## 📚 Documentation et statut

- [Résultats et interprétation](docs/RESULTS.md)
- [Protocole complet](docs/PROTOCOL.md)
- [Reproduction et provenance](docs/REPRODUCIBILITY.md)
- [Limites scientifiques](docs/LIMITATIONS.md)
- [Travaux restant à réaliser](docs/ROADMAP.md)
- [Contribuer](CONTRIBUTING.md)

Version **0.1.0**, 16 octobre 2026. Auteurs : **Nicolas Marano et Romain Despoullain**. La [licence MIT](LICENSE) couvre les fichiers originaux de cette publication ; les programmes et énoncés tiers ne sont pas redistribués. Pour citer les observations, utiliser [CITATION.cff](CITATION.cff) avec la révision exacte.
