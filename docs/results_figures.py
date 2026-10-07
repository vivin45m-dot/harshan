"""Charts of the evaluation results for the report and slides.

    python docs/results_figures.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
R = json.loads((ROOT / "artifacts" / "results.json").read_text())

COLORS = {"evidential": "#2a78d6", "mc_dropout": "#eb6834", "arima": "#1baf7a"}
NAMES = {"evidential": "Evidential GRU", "mc_dropout": "MC-dropout GRU", "arima": "SARIMA",
         "naive": "Naive", "seasonal_naive": "Seasonal naive", "gru_point": "GRU (point)"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


def calibration():
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ax.plot([0.45, 1], [0.45, 1], ls="--", color="#9a9893", lw=1, label="Perfect calibration")
    for k, c in COLORS.items():
        lv = R["calibration"][k]["levels"]
        ax.plot([l["level"] for l in lv], [l["picp"] for l in lv], marker="o", color=c, lw=2, ms=6,
                label=NAMES[k])
    ax.set_xlabel("Nominal interval")
    ax.set_ylabel("Share of actuals inside the interval")
    ax.set_xlim(0.45, 1); ax.set_ylim(0.45, 1)
    ax.grid(color="#e1e0d9", lw=0.6)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "calibration")


def accuracy():
    acc = R["accuracy"]
    order = sorted(acc, key=lambda k: acc[k]["mase"])
    fig, ax = plt.subplots(figsize=(6, 3.2))
    vals = [acc[k]["mase"] for k in order]
    colors = ["#2a78d6" if k == "evidential" else "#b7b5ae" for k in order]
    ax.barh([NAMES[k] for k in order][::-1], vals[::-1], color=colors[::-1], height=0.6)
    ax.axvline(1.0, color="#52514e", ls="--", lw=1)
    for y, v in enumerate(vals[::-1]):
        ax.text(v + 0.01, y, f"{v:.3f}", va="center", fontsize=9)
    ax.set_xlabel("MASE on the test period (lower is better; 1 = seasonal naive)")
    ax.set_xlim(0, 1.15)
    save(fig, "accuracy")


if __name__ == "__main__":
    calibration()
    accuracy()
