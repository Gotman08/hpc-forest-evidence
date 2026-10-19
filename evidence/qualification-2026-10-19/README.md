# Qualification des quinze références · 19 octobre 2026

La qualification ARM des quinze programmes de référence est terminée et reçue. Le job Slurm 755488 a duré 65 secondes, avec quatre CPU, 16 Gio et aucun GPU. Il n'a lancé aucun modèle.

[Les données numériques exactes](baselines.json) contiennent cinq durées positives de confirmation par sujet, leur moyenne, leur écart-type d'échantillon et les empreintes des reçus privés. Les 75 durées concernent les commandes de benchmark sur les entrées officielles ; elles ne constituent pas des mesures individuelles par entrée. Le lecteur local a vérifié les contrats, les sources, les binaires ARM64, les contextes et les flux originaux, les deux évaluations par registre et l'absence d'essais de recherche.

Cette qualification établit que les références peuvent être évaluées dans cette allocation. Elle ne mesure aucun gain produit par un modèle et ne compte pas comme une cellule de la matrice native R2. Les quinze sujets et les quatre modèles MAX restent une campagne distincte.

La réception conserve 1400 fichiers privés restaurés avec les mêmes empreintes avant et après lecture. Une première édition du lecteur refusait à tort trente reflogs Git comme journaux de commandes orphelins. Le refus est conservé. La seconde édition distingue les racines exactes des journaux de commandes ; ses 85 tests incluent le rejet de vrais journaux et sidecars orphelins, même après recalcul des empreintes. Elle a relu la même archive reçue, sans répéter le job.

La projection publique contient les nombres et empreintes, sans chemins de machines, code du moteur, entrées protégées ou flux bruts. Les binaires externes Python et shell n'ont pas été reçus et audités indépendamment ; leurs empreintes sont des observations du processus. Les flux combinés ne prouvent pas une attribution indépendante à chaque entrée. Les résultats ne proviennent pas d'une seconde implémentation de l'évaluateur.

`python -m tools.verify` recalcule les moyennes et écarts-types et refuse les champs inattendus ou les revendications de gain. La vérification publique contrôle l'intégrité et l'arithmétique de cette projection ; elle n'exécute aucun programme reçu.
