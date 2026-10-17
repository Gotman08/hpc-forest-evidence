"""Render the published observations; optional matplotlib dependency."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

plt.switch_backend("Agg")

ROOT = Path(__file__).resolve().parents[1]


def save(fig, name):
    target = ROOT / "docs/assets"
    target.mkdir(parents=True, exist_ok=True)
    fig.savefig(target / f"{name}.png", dpi=180, facecolor="white", metadata={"Software": "HPC Forest evidence tools"})
    fig.savefig(target / f"{name}.svg", facecolor="white", metadata={"Date": None, "Creator": "HPC Forest evidence tools"})
    svg = target / f"{name}.svg"
    svg.write_bytes(b"\n".join(line.rstrip() for line in svg.read_bytes().splitlines()) + b"\n")
    plt.close(fig)


def main():
    data = json.loads((ROOT / "evidence/results.json").read_text(encoding="utf-8"))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 17,
                         "axes.labelcolor": "#334155", "text.color": "#0f172a", "svg.hashsalt": "hpc-forest-evidence-v1"})
    fig, ax = plt.subplots(figsize=(10.5, 4.7), layout="constrained")
    for variant, offset, color in (("system-A", -0.18, "#64748b"), ("system-B", 0.18, "#0f766e")):
        rows = [r for r in data["controller"]["summary"] if r["variant"] == variant]
        bars = ax.bar([i + offset for i in range(len(rows))], [r["wall_ms_mean"] for r in rows],
                      width=0.34, color=color, label=variant,
                      yerr=[r["wall_ms_stdev"] for r in rows], capsize=4)
        ax.bar_label(bars, labels=[f"{r['wall_ms_mean']:.3f}" for r in rows], padding=10, fontsize=11)
    ax.set(xticks=[0, 1], xticklabels=["8 cycles per series", "32 cycles per series"],
           ylim=(0, 12.3), ylabel="Controller wall time per cycle (ms)")
    ax.set_title("Controller overhead on fixed response traces", loc="left", pad=36, fontweight="bold")
    ax.text(0, 1.04, "15 measured series per bar · error bars: sample standard deviation",
            transform=ax.transAxes, fontsize=10, color="#475569")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.14)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left")
    fig.supxlabel("No model calls or evaluated HPC programs in this experiment.", fontsize=10, color="#475569")
    save(fig, "controller-overhead")

    fig, ax = plt.subplots(figsize=(10.5, 4.9), layout="constrained")
    colors = {"2022-nbody": "#0f766e", "2022-knn": "#475569", "2022-sum": "#d97706", "2022-bucketsort": "#7c3aed"}
    labels = {"2022-nbody": "N-body · 4,096 bodies", "2022-knn": "k-NN · 98,070 points",
              "2022-sum": "Sum · matrix side 1,024", "2022-bucketsort": "Bucket sort · 65,536 strings"}
    for subject in colors:
        rows = [r for r in data["cpu_scaling"]["comparisons"] if r["subject"] == subject]
        ax.plot([r["cores"] for r in rows], [r["own_core_speedup"] for r in rows],
                marker="o", linewidth=2.4, markersize=5, color=colors[subject], label=labels[subject])
    ideal_cores = [1, 2, 4, 8, 16]
    ax.plot(ideal_cores, ideal_cores, color="#94a3b8", linestyle="--", linewidth=1.2,
            label="Ideal linear scaling (guide)")
    ax.set_xscale("log", base=2)
    ax.set(xticks=[1, 2, 4, 8, 16], xticklabels=[1, 2, 4, 8, 16], ylim=(0, 17),
           xlabel="Physical CPU cores made accessible", ylabel="Same-program speedup: T(1) / T(p)")
    ax.set_title("Core scaling of frozen selected programs", loc="left", pad=36, fontweight="bold")
    ax.text(0, 1.04, "All four largest cases in one allocation · five timings per configuration",
            transform=ax.transAxes, fontsize=10, color="#475569")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.14)
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    ax.annotate("14.38×", xy=(16, 14.376946408492195), xytext=(-56, -3), textcoords="offset points",
                color="#0f766e", fontweight="bold")
    fig.supxlabel("Separate experiment; these curves do not evaluate the controller change above.", fontsize=10, color="#475569")
    save(fig, "cpu-scaling")


if __name__ == "__main__":
    main()
