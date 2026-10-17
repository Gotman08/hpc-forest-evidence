# Protocole de comparaison externe

_Version 1.0 · 16 octobre 2026 · Nicolas Marano et Romain Despoullain._

## 🎯 Question et unité d’expérience

On évalue la capacité d’un système à produire un programme correct et plus rapide à partir d’une référence fournie, dans un budget fixé. Le contrat décrit les entrées, sorties et contrôles observables ; il n’impose pas de fonctionnement interne au système.

Une recherche indépendante correspond à **un sujet × une configuration de système × une graine × un contrat figé**. Cinq chronométrages du même exécutable ne constituent pas cinq recherches indépendantes.

| Paramètre | Profil principal |
| --- | --- |
| Départ | Programme de référence figé ; contexte et dossier neufs |
| Graine principale | 23 ; autres graines communes préenregistrées séparément |
| Budget de recherche | 1 800 s et plafond déclaré de 1 500 000 jetons |
| Réserve finale | 120 s préservées dans la gestion du budget |
| Remises externes | Huit programmes au maximum ; 600 s par demande |
| Exécution des programmes | Linux ARM64 ; quatre cœurs CPU alloués ; 16 Gio ; zéro GPU |
| Développement | Trois cas de correction ; une chauffe exclue et trois temps |
| Confirmation | Trois autres cas de correction et l’entrée chronométrée ; une chauffe et cinq temps intercalés |
| Gain admis | Sorties exactes et réduction du temps moyen d’au moins 3 % |

Les remises externes, appels internes, consommations et plafonds sont distincts. Publier la part connue et les compteurs manquants. Un arrêt fondé sur un compteur après appel ne prouve pas à lui seul une borne stricte avant l’inférence suivante. L’infrastructure d’inférence est décrite séparément de la machine exécutant les programmes.

## 📋 Préparer les sujets et la cible

Figer les sources, les exigences, les formats, les cas et leurs SHA-256, les sorties attendues, les options de compilation et les limites avant la recherche. Compiler la référence et vérifier ses sorties sur la vraie cible. Une incompatibilité de référence est un problème de préparation ; elle ne devient pas un échec du système ni une occasion d’assouplir l’oracle.

Le corpus historique admis comprend les quinze sujets suivants. Cette liste ne fournit pas les entrées réservées et ne vaut pas qualification automatique d’une nouvelle cible.

| Édition | Sujets |
| --- | --- |
| 2020 | Produit tropical, quicksort, permutations, graphe |
| 2021 | Graphe, métriques de matrice, Sokoban, Jacobi |
| 2022 | k-NN, somme, N-body, bucket sort |
| 2023 | Count, somme, N-p-bonacci |

Les sources publiques sont les [énoncés 2020](http://lspd.mackenzie.br/marathon/20/problemset.pdf), [2021](http://lspd.mackenzie.br/marathon/21/problemset.pdf), [2022](http://lspd.mackenzie.br/marathon/22/problemset.pdf) et [2023](http://lspd.mackenzie.br/marathon/23/problemset.pdf). Leur disponibilité actuelle n’est pas présumée. Les adaptations de cible restent distinguées des règles du concours ; aucun classement officiel n’est déduit de ces mesures.

Les exclusions historiques sont Jacobi 2020, primes 2020, Johnson 2021 et path 2023, pour des limites de préparation ou d’observabilité. La correction sur un jeu fini ne certifie pas tout le domaine ni la fidélité à un algorithme imposé. Pour N-body, conserver notamment l’en-tête binaire présent dans la référence ; pour quicksort, le générateur et le contrôle MD5 appartiennent au contrat.

## 🧪 Déroulement et confirmation

1. Créer un essai neuf, avec identifiant, contexte et registre propres, sans gagnant hérité.
2. Fournir la référence et les contraintes publiques au système. Garder les cas et réponses de l’évaluateur dans un environnement réellement inaccessible au système ; un nom de dossier ne garantit aucune isolation.
3. Démarrer les budgets et enregistrer chaque remise, diagnostic autorisé, erreur, doublon, consommation connue et cause d’arrêt. L’opérateur ne conseille pas d’algorithme et ne répare pas de candidat.
4. Conserver les octets et l’empreinte de chaque candidat. Compiler avec les mêmes options que la référence, puis comparer les sorties exactement, y compris en binaire. Le code retour seul ne prouve pas la correction.
5. Après correction réussie, faire la chauffe puis les trois mesures de recherche. Déclarer avant l’essai les retours de développement autorisés et conserver les mêmes droits pour les systèmes comparés.
6. Fermer la recherche et figer les finalistes avant la confirmation réservée. Une confirmation rejetée ne rouvre pas la recherche.
7. Recompiler et contrôler référence/finalistes, puis faire une chauffe par programme. Effectuer cinq tours intercalés, une exécution de chaque programme par tour, dans un ordre mélangé et archivé.
8. Conserver les cinq temps, sorties ou empreintes de sorties, identités des exécutables avant/après, ressources et incidents. Une série manquante reste indisponible ; elle n’est pas remplacée par 0 %.

La convention historique initialise une fois `random.Random(24)` pour la première phase de confirmation et mélange de nouveau à chaque tour. Conserver la liste initiale, la version du générateur et le véritable ordre. Préenregistrer l’alternance A/B d’une nouvelle comparaison.

Mesurer le temps mural de la commande complète. Préciser ce qui est inclus : lancement, calcul et entrées/sorties ; les ouvertures de fichiers et la création de répertoires doivent être situées explicitement par rapport au chronomètre. Compilation et contrôles consomment le budget de recherche même lorsqu’ils sont exclus du temps du programme.

## 📊 Calculs et négatifs

Avec `T0` moyenne des cinq temps de la référence et `T` moyenne du candidat dans la même série : réduction `100 × (1 − T/T0)`, accélération `T0/T`, secondes économisées `T0 − T`. Calculer aussi l’écart-type d’échantillon, diviseur `n − 1`, et la médiane. Garder les valeurs brutes non arrondies.

Une référence conservée après recherche et confirmation exploitables a un gain admis nul. Un programme incorrect, une confirmation absente, un incident technique et un essai non exécuté ont des états séparés. Publier les dénominateurs et les coûts des essais improductifs. Ne pas fusionner les moyennes de plusieurs allocations ni présenter la moyenne des seuls succès comme celle de tous les essais.

Apparier sujet, configuration, graine et contrat pour comparer deux systèmes. Conserver les durées de référence propres aux séries et leurs rapports normalisés. Plusieurs recherches neuves sont nécessaires pour étudier la stabilité ; les répétitions d’un même binaire décrivent seulement sa dispersion de temps.

## 🧭 Diagnostic de montée en cœurs

Ce diagnostic distinct conserve les mêmes octets exécutables, sans nouvelle compilation ou recherche. Qualifier chaque couple programme/entrée, puis allouer seize cœurs physiques distincts, 16 Gio et zéro GPU. Tester 1, 2, 4, 8 et 16 cœurs accessibles, affinités et variables de threads cohérentes, une chauffe puis cinq passages intercalés.

L’accélération propre vaut `S(p) = T(1)/T(p)` et l’efficacité `S(p)/p`. Elle ne se confond pas avec le rapport à un autre programme de référence. CPU/mural indique une occupation moyenne et ne compte pas exactement les threads. Garder les courbes plates et les échecs ; ne pas réoptimiser un candidat pour effacer un résultat décevant.

Les [gabarits vierges](../templates/README.md) et le [guide de comparaison](COMPARING.md) décrivent le dossier de retour. Le fonctionnement interne du système n’est pas demandé ; l’identité de configuration, les droits, budgets, preuves et limites doivent être vérifiables.
