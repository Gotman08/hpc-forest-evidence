"""Reproduce the three numeric R1/R2 figures from the received public JSON."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter
MODELS = ['gpt-6.1-sol', 'gpt-6-luna', 'gpt-6-astra', 'gpt-5.6-terra']
SHORT = ['Sol', 'Luna', 'Astra', 'Terra']
SUBJECTS = ['2023-count', '2020-tropical', '2020-quicksort', '2020-permutations', '2020-graph', '2021-graph', '2021-metrics', '2021-sokoban', '2021-jacobi', '2022-knn', '2022-sum', '2022-nbody', '2022-bucketsort', '2023-sum', '2023-npbonacci']
INK, BLUE, ORANGE, GREY, MISSING = ('#17354a', '#0072B2', '#D55E00', '#596773', '#e6e9ec')

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("comparison.json"))
    parser.add_argument("--output", type=Path, default=Path.cwd()/"figures-r1-r2-reproduites")
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '0c06538d1cc556fadd8cbc7fd7ad3f3238a99f4274765c47b74681c163aa3609'
    assert not args.output.exists(), "Choose a new output directory"
    args.output.mkdir(parents=True)
    plots(json.loads(raw), args.output)
    print("Three figures reproduced as SVG, PDF and PNG")
