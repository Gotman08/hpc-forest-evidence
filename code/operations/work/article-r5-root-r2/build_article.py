"""Build a separate r5 article from preserved r4 and a received numeric whitelist."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
DELIVERY = BASE / "outputs/HPC-Forest-Article-R5-R1-R2"
BASELINE = HERE / "base-r4"
MODELS = ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra"]
SHORT = ["Sol", "Luna", "Astra", "Terra"]
SUBJECTS = ["2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph", "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum", "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci"]
INK, BLUE, ORANGE, GREY, MISSING = "#17354a", "#0072B2", "#D55E00", "#596773", "#e6e9ec"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def fr(value, digits=6):
    return f"{value:.{digits}f}".replace(".", ",")


def export(fig, folder, name):
    for extension in ("svg", "pdf", "png"):
        fig.savefig(folder / f"{name}.{extension}", dpi=450, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def plots(data, folder):
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"], "font.size": 10,
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.spines.top": False,
        "axes.spines.right": False, "text.color": INK, "axes.labelcolor": INK, "pdf.fonttype": 42, "svg.fonttype": "none"})
    cells = {(row["subject_id"], row["model"]): row for row in data["cells"]}
    assert len(cells) == 60 and all((subject, model) in cells for subject in SUBJECTS for model in MODELS)
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 5.25), sharey=True, gridspec_kw={"wspace": .12})
    for ax, edition in zip(axes, ("R1", "R2")):
        for y, subject in enumerate(SUBJECTS):
            for x, model in enumerate(MODELS):
                row = cells[subject, model]
                if edition == "R1":
                    retained = row["r1_gain_fraction"] == 0
                    color, label, textcolor = ("#d7e9f2", "1× R", INK) if retained else (BLUE, fr(row["r1_speedup"], 1) + "×", "white")
                else:
                    audited = row["r2_initial_batch_received"]
                    color, label, textcolor = (ORANGE, "LOT", "white") if audited else (MISSING, "NA", GREY)
                ax.add_patch(Rectangle((x-.5, y-.5), 1, 1, facecolor=color, edgecolor="white", linewidth=1.2))
                ax.text(x, y, label, ha="center", va="center", fontsize=8.7, color=textcolor)
        ax.set(xlim=(-.5, 3.5), ylim=(14.5, -.5), xticks=range(4), xticklabels=SHORT)
        ax.xaxis.tick_top(); ax.tick_params(length=0, pad=6)
        ax.set_title("A  R1 · 60 cellules confirmées" if edition == "R1" else "B  R2 · 1 premier lot audité", loc="left", fontsize=10.5, fontweight="bold", pad=24)
        for spine in ax.spines.values(): spine.set_visible(False)
    axes[0].set_yticks(range(15), SUBJECTS)
    axes[1].tick_params(labelleft=False)
    fig.legend(handles=[Patch(color=BLUE, label="R1 : candidat confirmé"), Patch(color="#d7e9f2", label="R1 : référence retenue (R)"),
        Patch(color=ORANGE, label="R2 : premier lot reçu"), Patch(color=MISSING, label="R2 : mesure absente (NA)")],
        ncol=2, frameon=False, loc="lower center", bbox_to_anchor=(.56, -.04), fontsize=8.6)
    fig.subplots_adjust(left=.19, right=.98, top=.86, bottom=.14)
    export(fig, folder, "couverture-r1-r2")

    series = {item["id"]: item for item in data["series"]}
    groups = [("R1 · confirmation", "r1", BLUE, "o"), ("R2 · premier lot audité", "r2_search", ORANGE, "o"),
              ("R2 · finale, source seule", "r2_confirmation", ORANGE, "o")]
    fig, axes = plt.subplots(1, 3, figsize=(8.1, 3.6), sharey=True)
    for index, (ax, (title, prefix, color, marker)) in enumerate(zip(axes, groups)):
        for x, role in enumerate(("reference", "candidate")):
            item = series[prefix + "_" + role]
            points = np.array(item["normalized_samples"], dtype=float)
            c = GREY if role == "reference" else color
            offsets = np.linspace(-.11, .11, len(points))
            hollow = prefix == "r2_confirmation"
            ax.scatter(x + offsets, points, s=28, edgecolor=c, facecolor="white" if hollow else c, linewidth=1, zorder=3)
            sd = item["sample_sd_seconds"] / item["reference_mean_seconds"]
            ax.errorbar(x, item["normalized_mean"], yerr=sd, fmt="_", markersize=16, color=INK, capsize=5, elinewidth=1.3, zorder=4)
        ax.axhline(1, color="#9eacb5", linewidth=.8, linestyle="--")
        ax.set(xticks=[0, 1], xticklabels=["Référence", "Candidat"], xlim=(-.4, 1.4), ylim=(0, 1.12))
        ax.set_title(chr(65+index) + "  " + title + "\n" + "n = " + str(series[prefix+"_candidate"]["n"]) + " par programme", fontsize=9.5, loc="left", fontweight="bold")
        ax.grid(axis="y", color="#e7ecef", linewidth=.6)
        if hollow:
            ax.text(.5, .14, "Remesure indépendante\nnon admise", transform=ax.transAxes, ha="center", color=ORANGE, fontsize=8.5)
    axes[0].set_ylabel("Temps / moyenne de sa propre référence")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:.1f}".replace(".", ",")))
    fig.subplots_adjust(left=.1, right=.99, top=.79, bottom=.2, wspace=.18)
    export(fig, folder, "quicksort-repetitions-r1-r2")

    matched = next(row for row in data["cells"] if row["subject_id"] == "2020-quicksort" and row["model"] == "gpt-6-luna")
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 3.0), gridspec_kw={"width_ratios": [1.15, 1]})
    values = [matched["r1_known_exact_tokens"], matched["r2_known_exact_tokens"]]
    axes[0].barh([1, 0], values, color=[BLUE, ORANGE], height=.5)
    axes[0].set(yticks=[1, 0], yticklabels=["R1 · recherche close\n10 appels / 8 programmes", "R2 · données reçues\n2 appels / 1 programme"], xlabel="Jetons exacts connus · Luna / quicksort")
    axes[0].set_xlim(0, max(values)*1.28)
    axes[0].ticklabel_format(axis="x", style="plain")
    axes[0].set_xticks([0, 100000, 200000, 300000])
    axes[0].xaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.0f}".replace(",", " ")))
    for y, value in zip([1, 0], values):
        axes[0].text(value+max(values)*.025, y, f"{value:,}".replace(",", " "), va="center", fontsize=9)
    axes[0].set_title("A  Coûts observés", loc="left", fontweight="bold", fontsize=11)
    axes[0].grid(axis="x", alpha=.15)
    axes[1].axis("off")
    axes[1].set_title("B  Portée de la comparaison", loc="left", fontweight="bold", fontsize=11)
    for y, number, label, color in [(.77, "60/60", "cellules R1 confirmées", BLUE), (.48, "1/60", "premier lot R2 reçu et audité", ORANGE), (.19, "0", "paire finale R1/R2 admise", GREY)]:
        axes[1].text(.02, y, number, transform=axes[1].transAxes, fontsize=21, color=color, fontweight="bold", va="center")
        axes[1].text(.4, y, label, transform=axes[1].transAxes, fontsize=9.5, va="center")
    fig.subplots_adjust(left=.2, right=.98, bottom=.25, top=.82, wspace=.35)
    export(fig, folder, "cout-et-couverture-r1-r2")


def prose(data):
    s = {row["id"]: row for row in data["series"]}
    rows = []
    for label, key, status in [("R1 · confirmation", "r1", "Confirmation R1 reçue"), ("R2 · premier lot", "r2_search", "Lot reçu et audité"), ("R2 · finale produite", "r2_confirmation", "Source seule ; performance indépendante non admise")]:
        r, c = s[key+"_reference"], s[key+"_candidate"]
        rows.append(f"| {label} | {r['n']}/{c['n']} | {fr(1000*r['mean_seconds'], 4)} | {fr(1000*c['mean_seconds'], 4)} | {fr(r['mean_seconds']/c['mean_seconds'], 4)} | {status} |")
    section = """### 3.9. Première réception R2 et comparaison avec R1

La nouvelle matrice R2 vise les mêmes quinze identifiants de sujets et les quatre modèles en effort MAX, soit soixante cellules. Cet objectif n'est pas une couverture déjà mesurée. À l'arrêté documentaire de cette édition, R1 possède soixante confirmations historiques ; R2 possède un seul premier lot reçu et audité, Luna/MAX sur quicksort2020. Les cinquante-neuf autres cases restent NA pour la performance reçue. Un incident de préparation, une admission expirée ou une cellule non exécutée ne reçoit ni temps nul ni gain nul. La figure8 rend ce décalage de couverture explicite ; les onze références conservées de R1 valent un facteur1, sans être transformées en données manquantes.

![Figure 8 — Couverture des quinze sujets et quatre modèles MAX. À gauche, les soixante confirmations R1, avec facteur descriptif propre à leur référence ; R désigne les onze références retenues. À droite, LOT marque uniquement le premier lot R2 reçu et audité ; NA signifie absence de mesure R2 reçue. Le candidat final produit par la source R2 ne constitue pas encore un gain indépendant admis. Les cellules ne constituent pas des réplications entre modèles.](edition-professionnelle/figures/comparaison-r1-r2/couverture-r1-r2.png)

Le seul rapprochement chronométrique disponible porte sur Luna/MAX et quicksort2020. Les répétitions R1 proviennent du job748259 ; elles ne sont pas remplacées par celles de la cohorte source-only749843, qui constitue une autre expérience. Les trois temps de recherche R2 et leur référence contemporaine sont reçus et audités. Les cinq temps finaux R2 sont présents dans l'archive reçue et gardent le statut « source seule » : la confirmation annoncée par le programme ne remplace pas la remesure indépendante des performances. Le tableau8 et la figure9 conservent ces trois séries séparées.

*Tableau 8 — Cas Luna/MAX/quicksort2020. n indique les répétitions de référence/candidat, pas le nombre de recherches indépendantes. Le rapport Réf./cand. est descriptif et calculé au sein de chaque série ; aucun rapport de performance entre allocations R1 et R2 n'est estimé.*

| Série | n réf./cand. | Réf. moyenne (ms) | Cand. moyenne (ms) | Réf./cand. | Niveau de preuve |
|---|---|---|---|---|---|
""" + "\n".join(rows) + """

![Figure 9 — Répétitions de Luna/MAX/quicksort2020, normalisées par la moyenne de la référence de leur propre série. Chaque point est un chronométrage ; le trait et la barre représentent la moyenne et l'écart-type descriptif. A : confirmation R1 reçue, cinq temps par programme. B : premier lot R2 reçu et audité, trois temps par programme. C : finale produite par R2, cinq temps par programme, cercles ouverts et performance indépendante non admise. Ces répétitions ne fournissent ni intervalle entre recherches ni preuve causale d'un avantage de R1 ou de R2.](edition-professionnelle/figures/comparaison-r1-r2/quicksort-repetitions-r1-r2.png)

Les temps absolus restent liés à leurs allocations et à leurs conditions. Une normalisation facilite la lecture de chaque référence sans rendre les expériences équivalentes. Les budgets nominaux ne suffisent pas à égaliser l'effort effectivement dépensé : l'audit du premier lot R2 a consommé une partie de l'horloge originale, sans remise à zéro, tandis que la recherche R1 était déjà close. Aucun gagnant causal R1/R2 n'est déduit de ces observations et aucune paire finale n'est actuellement admise comme telle.

Les deux appels R2 audités représentent32765jetons exacts connus. La figure10 met cette réception à côté du coût connu du seul cas R1 concordant, en conservant la différence de périmètre et de stade. Elle ne mesure ni prix d'API, ni coût d'inférence matériel, ni efficacité par jeton. Les échantillons, statistiques, facteurs R1 et cases NA sont livrés dans l'annexeL et dans les fichiers CSV/JSON de cette édition.

![Figure 10 — Jetons exacts connus du cas Luna/MAX/quicksort2020 et portée documentaire de la comparaison. Le coût R1 correspond à une recherche close ; celui de R2 aux deux appels reçus et audités. Les périmètres et l'effort de recherche diffèrent : les barres ne classent pas une efficacité par jeton. Le panneauB rappelle les soixante confirmations R1, l'unique premier lot R2 audité et l'absence de paire finale R1/R2 admise.](edition-professionnelle/figures/comparaison-r1-r2/cout-et-couverture-r1-r2.png)

"""
    section = section.replace("Les temps absolus restent liés", "Les horodatages archivés placent le point d'arrêt du premier lot à 10 h 49 min 24,357 s UTC et le reçu de libération à 11 h 10 min 38,431 s UTC, soit un intervalle d'environ 21 min 14 s. Cet intervalle entre dates de fichiers ne mesure pas un temps CPU ni une attente opérateur exacte. L'audit a consommé l'horloge existante ; la source a ensuite arrêté la recherche faute de fenêtre d'admission restante. R1 a exploré huit programmes et dix appels natifs, contre un programme et deux appels reçus pour R2. La fenêtre minimale d'admission d'une génération R2 est de 600 s. Ces écarts d'effort réalisé et de contrôleur persistent malgré des plafonds nominaux communs.\n\nLes temps absolus restent liés")
    section = section.replace("quicksort2020", "quicksort 2020").replace("job748259", "job 748259").replace("source-only749843", "source-only 749843").replace("figure8", "figure 8").replace("tableau8", "tableau 8").replace("figure9", "figure 9").replace("figure10", "figure 10").replace("panneauB", "panneau B").replace("l'annexeL", "l'annexe L").replace("représentent32765jetons", "représentent 32 765 jetons").replace("facteur1", "facteur 1")
    return section


def annex(data):
    out = ["\n\n## L. Comparaison R1/R2 : couverture, échantillons et limites\n",
        "Cette annexe prolonge les résultats historiques sans les remplacer. Les données R2 reçues décrivent un premier lot audité et une finale produite par la source ; aucun nouveau gain indépendant R2 ni paire finale R1/R2 n'est admis. Les soixante identités partagent les quinze sujets et quatre modèles MAX enregistrés, mais l'ordre temporel, les conditions et l'effort effectif diffèrent. NA signifie une mesure absente ; un facteur1 signifie que R1 conserve sa référence.\n",
        "Les fichiers [matrice CSV](donnees-r1-r2/comparison-matrix.csv), [données et niveaux de preuve JSON](donnees-r1-r2/comparison.json), [temps individuels CSV](donnees-r1-r2/timing-samples.csv) et [provenance](donnees-r1-r2/provenance.json) accompagnent les figures [couverture SVG](edition-professionnelle/figures/comparaison-r1-r2/couverture-r1-r2.svg), [chronométrages SVG](edition-professionnelle/figures/comparaison-r1-r2/quicksort-repetitions-r1-r2.svg) et [coûts SVG](edition-professionnelle/figures/comparaison-r1-r2/cout-et-couverture-r1-r2.svg). Les sources vectorielles PDF de chaque figure portent le même nom.\n",
        "### L.1. Matrice complète\n", "| Sujet | Modèle MAX | Facteur R1 | Sélection R1 | Réception R2 |\n|---|---|---|---|---|\n"]
    cells = {(row["subject_id"], row["model"]): row for row in data["cells"]}
    for subject in SUBJECTS:
        for model, label in zip(MODELS, SHORT):
            row = cells[subject, model]
            out.append(f"| {subject} | {label} | {fr(row['r1_speedup'], 6)} | {'Référence retenue' if row['r1_gain_fraction'] == 0 else 'Candidat confirmé'} | {'Premier lot audité ; finale source seule' if row['r2_initial_batch_received'] else 'NA'} |\n")
    out.extend(["\n### L.2. Répétitions exactes du cas concordant\n", "Les temps ci-dessous sont en secondes. La confirmation R1, le premier lot R2 et la finale R2 sont conservés comme séries distinctes. Les références R1 sont celles de748259 ; aucune répétition de749843source-only n'est substituée. Les champs JSON gardent la précision numérique complète, la provenance et le niveau de preuve.\n", "| Série | Programme | Répétition | Temps (s) |\n|---|---|---|---|\n"])
    names = {"r1_reference": ("R1 · confirmation", "Référence"), "r1_candidate": ("R1 · confirmation", "Candidat"), "r2_search_reference": ("R2 · lot audité", "Référence"), "r2_search_candidate": ("R2 · lot audité", "Candidat"), "r2_confirmation_reference": ("R2 · finale source seule", "Référence"), "r2_confirmation_candidate": ("R2 · finale source seule", "Candidat")}
    for item in data["series"]:
        for i, value in enumerate(item["samples_seconds"], 1):
            label, role = names[item["id"]]
            out.append(f"| {label} | {role} | {i} | {fr(value, 12)} |\n")
    out.extend(["\n### L.3. Coûts, incidents et niveau de preuve\n", "Les deux appels R2 déjà audités totalisent32765jetons exacts ; aucun compteur inconnu n'est complété par une réservation. Le coût connu du cas R1 concordant vaut261707jetons. La comparaison concerne un cas R1 clos et une réception R2 partielle, avec audit dans l'horloge d'origine : elle n'établit aucune efficacité relative par jeton.\n", "L'incident Sol/MAX/count755766 s'est produit avant admission et avant appel de modèle. Il est conservé comme incident technique, sans temps de candidat ni résultat algorithmique. Les autres cellules sans mesure reçue restent NA, même lorsqu'une préparation technique existe. Les statuts de jobs ne sont pas utilisés comme substituts à des résultats de performance.\n", "Le statut source seule de la finale R2 conserve les cinq temps et les déclarations du programme sans promouvoir une remesure indépendante. Les empreintes publiques du dataset et les références numériques permettent d'inspecter cette distinction. Les textes de modèles, arguments CLI, chemins privés de skills, recensements de processus et implémentations privées ne sont pas ajoutés à cette édition.\n"])
    matched = data["matched_cell"]
    out.extend(["\n### L.4. Conditions et chronologie du cas concordant\n", "Le modèle, l'effort MAX, la graine23, le contrat de vérification, les commandes déclarées, les plafonds communs et l'empreinte du compilateur concordent. Les nœuds, les allocations, les identifiants de protocole et les implémentations de contrôleur diffèrent. Le premier lot R2 a été interrompu pour audit dans son horloge d'origine ; aucune durée ni consommation n'a été remise à zéro. Les dates du point d'arrêt et du reçu de libération ci-dessous sont des métadonnées archivées de fichiers et ne constituent pas une mesure exacte de temps d'attente ou de CPU.\n", "| Rubrique | R1 / R2 |\n|---|---|\n",
        f"| Jobs et nœuds | R1 : {matched['r1_job_id']} / {matched['r1_compute_node']} ; R2 : {matched['r2_job_id']} / {matched['r2_compute_node']} |\n",
        f"| Archive source R1 historique | `{matched['r1_actual_historical_source_archive_sha256']}` |\n",
        f"| Archive source R2 | `{matched['r2_source_archive_sha256']}` |\n",
        f"| Protocole R1 | `{matched['r1_protocol_id']}` |\n", f"| Protocole R2 | `{matched['r2_protocol_id']}` |\n",
        "| Effort réalisé | R1 : huit programmes, dix appels natifs ; R2 : un programme, deux appels reçus |\n",
        "| Point d'arrêt archivé R2 | 19 octobre2026, 10:49:24.356543 UTC |\n", "| Reçu de libération archivé R2 | 19 octobre2026, 11:10:38.431345 UTC |\n",
        "| Intervalle de métadonnées | 1274,074801683426 s ; aucune interprétation comme CPU ou attente opérateur exacte |\n",
        "| Fin des admissions de recherche | Événement source 11:10:38.447683 UTC : No remaining search admission |\n",
        "| Échéances initiales conservées | Recherche 11:13:04.369661 UTC ; campagne 11:15:04.369661 UTC |\n",
        "| Fenêtre minimale d'une nouvelle génération R2 | 600 s ; ce contrôle diffère du contrôleur historique |\n",
        "| Conclusion autorisée | Description des séries et de leur couverture ; aucune supériorité causale R1/R2 |\n"])
    return "\n".join(out).replace("|\n\n|", "|\n|").replace("facteur1", "facteur 1").replace("de748259", "de 748259").replace("de749843source-only", "de 749843 source-only").replace("totalisent32765jetons", "totalisent 32 765 jetons").replace("vaut261707jetons", "vaut 261 707 jetons").replace("count755766", "count 755766").replace("graine23", "graine 23").replace("octobre2026", "octobre 2026")


def build(dataset, expected_sha, edition):
    assert sha(dataset) == expected_sha
    data = json.loads(dataset.read_bytes())
    assert len(data["cells"]) == 60 and len(data["series"]) == 6
    assert sum(row["r1_gain_fraction"] == 0 for row in data["cells"]) == 11
    assert sum(row["r2_initial_batch_received"] for row in data["cells"]) == 1
    assert not any(row["scientifically_admitted_pair"] or row["r2_scientifically_admitted_gain"] for row in data["cells"])
    out = DELIVERY / edition
    assert not out.exists()
    out.mkdir(parents=True)
    shutil.copytree(BASELINE / "edition-professionnelle", out / "edition-professionnelle")
    history = out / "history/r4"; history.mkdir(parents=True)
    for name in ("ARTICLE.md", "ARTICLE.pdf", "ARTICLE.html", "ANNEXES-TECHNIQUES.md", "ANNEXES-TECHNIQUES.pdf", "ANNEXES-TECHNIQUES.html", "provenance.json"):
        shutil.copyfile(BASELINE / name, history / name)
    shutil.copytree(BASELINE / "edition-professionnelle", history / "edition-professionnelle")
    shutil.copytree(dataset.parent, out / "donnees-r1-r2")
    save(out / "donnees-r1-r2/provenance.json", {"schema": "hpc-forest-r1-r2-public-provenance-v1", "comparison_sha256": expected_sha,
        "source_cutoff_utc": data["source_cutoff_utc"], "provenance": data["provenance"], "boundaries": data["boundaries"]})
    # Publish only deterministic numeric plotting code, without private renderer,
    # host paths, operational payloads or experimental engine implementation.
    source_text = Path(__file__).read_text(encoding="utf8")
    tree = ast.parse(source_text)
    public_code = '"""Reproduce the three numeric R1/R2 figures from the received public JSON."""\nimport argparse\nimport hashlib\nimport json\nfrom pathlib import Path\nimport matplotlib\nmatplotlib.use("Agg")\nimport matplotlib.pyplot as plt\nimport numpy as np\nfrom matplotlib.patches import Patch, Rectangle\nfrom matplotlib.ticker import FuncFormatter\n'
    for name in ("MODELS", "SHORT", "SUBJECTS"):
        public_code += name + " = " + repr(globals()[name]) + "\n"
    public_code += "INK, BLUE, ORANGE, GREY, MISSING = " + repr((INK, BLUE, ORANGE, GREY, MISSING)) + "\n\n"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"fr", "export", "plots"}:
            public_code += ast.get_source_segment(source_text, node) + "\n\n"
    public_code += '\nif __name__ == "__main__":\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("comparison.json"))\n    parser.add_argument("--output", type=Path, default=Path.cwd()/"figures-r1-r2-reproduites")\n    args = parser.parse_args()\n    raw = args.dataset.read_bytes()\n    assert hashlib.sha256(raw).hexdigest() == ' + repr(expected_sha) + '\n    assert not args.output.exists(), "Choose a new output directory"\n    args.output.mkdir(parents=True)\n    plots(json.loads(raw), args.output)\n    print("Three figures reproduced as SVG, PDF and PNG")\n'
    save(out / "donnees-r1-r2/rebuild-figures.py", public_code)
    save(out / "donnees-r1-r2/REPRODUCTION.md", "# Reproduction des figures numériques\n\nLe script utilise uniquement les champs publics de comparison.json. Aucun modèle, code expérimental ou job n'est invoqué. Python avec Matplotlib et NumPy est requis.\n\n`python rebuild-figures.py --output figures-r1-r2-reproduites`\n\nLe dossier de sortie doit être nouveau. L'empreinte du JSON reçu est vérifiée avant toute génération. Les trois figures sont enregistrées en SVG, PDF vectoriel et PNG450dpi. Les écarts-types sont descriptifs, les séries restent séparées et les mesures absentes ne deviennent jamais zéro.\n")
    figures = out / "edition-professionnelle/figures/comparaison-r1-r2"; figures.mkdir()
    plots(data, figures)
    article = (BASELINE / "ARTICLE.md").read_text(encoding="utf8")
    title_date = "Rapport de recherche expérimental · Version du 19 octobre 2026 · Données scientifiques admises arrêtées à 18/10/2026 à 05 h 03 UTC · Suivi technique et remesure R2h : 19/10/2026 à 08 h 40 UTC"
    assert title_date in article
    article = article.replace(title_date, title_date + " · Édition éditoriale r5 : comparaison R1/R2 partielle, arrêté documentaire " + data["source_cutoff_utc"])
    abstract_delta = "Cette édition ajoute une comparaison documentaire R1/R2 : soixante confirmations R1, un premier lot R2 reçu et audité, et cinquante-neuf cellules sans mesure R2 reçue. Les répétitions du cas Luna/MAX/quicksort sont montrées séparément par série et par niveau de preuve. La finale produite par R2 reste une observation de source, sans nouveau gain indépendant admis ni classement causal entre protocoles."
    article = article.replace("**Mots-clés :**", abstract_delta + "\n\n**Mots-clés :**", 1)
    table_lines = article.splitlines()
    for i, line in enumerate(table_lines):
        if line.startswith("|") and "Véritable Codex" in line and "R3" in line:
            cells = line.split("|")
            cells[1] = " R3 corrigé R4b / R5 "
            table_lines[i] = "|".join(cells)
            table_lines.insert(i, "| R2 · matrice quinze sujets / quatre modèles MAX | Un premier lot reçu et audité | Finale source seule ; 59 NA ; aucun gain indépendant R2 admis |")
            break
    else:
        raise ValueError("Expected historical Table1 protocol row absent")
    article = "\n".join(table_lines) + "\n"
    article = article.replace("## 4. Discussion", prose(data) + "## 4. Discussion", 1)
    old = "La priorité suivante est R2 : terminer les nombres premiers pour Sol, Luna, Astra et Terra MAX, puis étendre les quatre modèles aux quinze sujets de R1, soit soixante cellules neuves."
    assert old in article
    start = article.index(old); end = article.index("\n\n", start)
    article = article[:start] + "La priorité humaine actuelle est la matrice des quinze sujets avec les quatre modèles en MAX. Les nombres premiers constituent un unique pilote technique déjà reçu et audité, hors de cette matrice ; ils ne sont pas répétés pour couvrir tous les modèles. La nouvelle réception R2 concerne Luna/MAX/quicksort ; les trois temps initiaux sont audités et les cinq temps finaux produits restent source seule pour la performance indépendante. Les cinquante-neuf autres cellules ne possèdent pas encore de mesures reçues à l'arrêté de cette édition. La figure8 et l'annexeL rendent cette couverture visible, avec zéro paire finale R1/R2 admise et sans assimiler NA à un gain nul.".replace("figure8", "figure 8").replace("l'annexeL", "l'annexe L") + article[end:]
    conclusion = "La transition R1/R2 est désormais documentée par une matrice de couverture et les répétitions du seul cas reçu. Cette visibilité ne transforme pas une réception partielle en comparaison achevée : les différences d'allocation, de protocole et d'effort effectif, ainsi que l'absence de remesure indépendante de la finale R2, interdisent d'en déduire un avantage causal. Les données manquantes et les références retenues restent explicitement distinctes."
    article = article.replace("## Disponibilité des données et transparence", conclusion + "\n\n## Disponibilité des données et transparence", 1)
    old_availability = "Les données sont livrées avec le dossier de recherche local ; aucun dépôt public ou identifiant pérenne n’est revendiqué dans cette version."
    article = article.replace(old_availability, "Les éditions précédentes et les données publiques sont accessibles dans le [dépôt HPC-Forest](https://github.com/Gotman08/hpc-forest-evidence). Les données de cette comparaison accompagnent la présente livraison : [matrice CSV](donnees-r1-r2/comparison-matrix.csv), [échantillons CSV](donnees-r1-r2/timing-samples.csv) et [JSON avec niveaux de preuve](donnees-r1-r2/comparison.json).")
    appendix = (BASELINE / "ANNEXES-TECHNIQUES.md").read_text(encoding="utf8")
    appendix = appendix.replace("L’article n’affirme pas qu’un dépôt public existe.", "Les données et éditions publiques sont accessibles dans le [dépôt HPC-Forest](https://github.com/Gotman08/hpc-forest-evidence) ; la comparaison R1/R2 et ses niveaux de preuve sont détaillés en annexe L.")
    appendix += annex(data)
    article = article.replace("comparison-matrix.csv", "matrix15-comparison.csv")
    appendix = appendix.replace("comparison-matrix.csv", "matrix15-comparison.csv")
    save(out / "ARTICLE.md", article); save(out / "ANNEXES-TECHNIQUES.md", appendix)
    renderer_path = HERE / "rendre_original.py"
    spec = importlib.util.spec_from_file_location("r5_preserved_renderer", renderer_path)
    renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
    # Use PDF's standard Flate image streams. The installed ReportLab pure-Python
    # ASCII85 fallback failed on a historical appendix image in draft r1.
    from reportlab import rl_config
    rl_config.useA85 = False
    renderer.ROOT = out; renderer.HERE = out / "edition-professionnelle"
    renderer.main()
    preserved = json.loads((HERE / "BASELINE-MANIFEST.json").read_bytes())
    for row in preserved["preserved_files"]:
        if row["path"].endswith(".png"):
            assert sha(out / row["path"]) == row["sha256"]
    save(out / "provenance-r5.json", {"schema": "hpc-forest-article-r5-r1-r2-v1", "editorial_edition": "r5-root-r2",
        "source_cutoff_utc": data["source_cutoff_utc"], "dataset_sha256": expected_sha, "r4_preserved": True,
        "historical_figure_count_unchanged": 275, "new_numeric_figures": 3, "new_scientific_gain_admitted": False,
        "admitted_r1_r2_pairs": 0, "source_only_final_r2_performance_independently_admitted": False,
        "renderer_original_sha256": sha(renderer_path), "generator_sha256": sha(Path(__file__)),
        "models_or_jobs_started": 0, "private_implementation_or_cli_payload_added": False})
    print(json.dumps({"delivery": str(out), "article_pdf_sha256": sha(out/"ARTICLE.pdf"), "appendix_pdf_sha256": sha(out/"ANNEXES-TECHNIQUES.pdf")}))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True); parser.add_argument("--dataset-sha256", required=True)
    parser.add_argument("--edition", default="edition-r5-r1")
    args = parser.parse_args()
    build(args.dataset.resolve(), args.dataset_sha256, args.edition)
