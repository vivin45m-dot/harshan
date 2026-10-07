"""Draw the architecture, use-case and class diagrams as PNG + SVG.

    python docs/diagrams.py

Plain matplotlib so the figures can be regenerated without extra tools.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)

INK = "#1f1f1d"
MUTED = "#6b6a66"
BLUE = "#2a78d6"
BLUE_SOFT = "#e3eefb"
ORANGE_SOFT = "#fdebe2"
GREEN_SOFT = "#e2f5ec"
GREY_SOFT = "#f2f1ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})


def box(ax, x, y, w, h, title, lines=(), fill=GREY_SOFT, edge=INK, title_size=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fill, ec=edge, lw=1.1))
    ax.text(x + w / 2, y + h - 0.22, title, ha="center", va="top", fontsize=title_size, weight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.62 - i * 0.32, line, ha="center", va="top", fontsize=8.6, color=MUTED)


def arrow(ax, a, b, text=None, style="-|>", color=INK, rad=0.0, dashed=False):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=1.1,
                                 linestyle="--" if dashed else "-",
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.12, text, ha="center", fontsize=8, color=MUTED,
                bbox=dict(fc="white", ec="none", pad=1))


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / f"{name}.png")


def architecture():
    fig, ax = plt.subplots(figsize=(13, 9.6))
    ax.set_xlim(0, 13); ax.set_ylim(0, 9.6); ax.axis("off")

    for y, label in [(8.95, "1  Data ingestion"), (7.5, "2  Processing"), (6.05, "3  Features & provenance"),
                     (4.25, "4  Evidential model"), (1.6, "5  Serving & evaluation")]:
        ax.text(0.3, y, label, fontsize=9.5, color=BLUE, weight="bold")

    box(ax, 0.3, 7.75, 3.8, 1.05, "UN Comtrade API", ["US imports by HS6 x origin, kg, monthly"], fill=BLUE_SOFT)
    box(ax, 4.6, 7.75, 3.8, 1.05, "openFDA enforcement", ["29k food recall records"], fill=BLUE_SOFT)
    box(ax, 8.9, 7.75, 3.8, 1.05, "CDC NORS", ["foodborne outbreaks + food vehicle"], fill=BLUE_SOFT)

    box(ax, 0.3, 6.35, 12.4, 1.0, "Processing  (data/process.py)",
        ["node selection (commodity x origin) · recall & outbreak matching · FSMA 204 traceability checks"])

    box(ax, 0.3, 4.55, 7.6, 1.35, "Feature store  (model/features.py)",
        ["24-month windows · recalls known at time t · verification ratio",
         "time-based folds: train / validation / test"])
    box(ax, 8.6, 4.55, 4.1, 1.35, "Provenance ledger", ["SHA-256 proof of work, Merkle root",
                                                        "SQLite, one block per month"], fill=ORANGE_SOFT)

    box(ax, 0.3, 2.75, 3.3, 1.3, "GRU encoder", ["2 layers, 64 units", "+ static node inputs"], fill=GREEN_SOFT)
    box(ax, 4.3, 2.75, 3.6, 1.3, "Evidential head", ["(γ, ν, α, β)  Normal-Inverse-Gamma",
                                                      "NLL + λ·|y−γ|·(2ν+α)"], fill=GREEN_SOFT)
    box(ax, 8.6, 2.75, 3.4, 1.3, "Baselines", ["naive, seasonal naive, SARIMA", "GRU point, MC-dropout"])

    box(ax, 0.3, 0.2, 3.6, 1.2, "Evaluation harness", ["MAE/RMSE/MASE, NLL, PICP", "Mann-Whitney, OLS, Wilcoxon"])
    box(ax, 4.7, 0.2, 3.6, 1.2, "React dashboard", ["Leaflet supply map, forecast bands", "ledger explorer"],
        fill=BLUE_SOFT)
    box(ax, 9.1, 0.2, 3.6, 1.2, "FastAPI service", ["/api/nodes  /api/results", "/api/ledger/*  verify, tamper"],
        fill=BLUE_SOFT)

    for x in (2.2, 6.5, 10.8):
        arrow(ax, (x, 7.75), (x, 7.35))
    arrow(ax, (4.1, 6.35), (4.1, 5.9))
    arrow(ax, (10.65, 6.35), (10.65, 5.9))
    arrow(ax, (1.95, 4.55), (1.95, 4.05))
    arrow(ax, (3.6, 3.4), (4.3, 3.4))
    arrow(ax, (7.2, 4.55), (9.4, 4.05))
    arrow(ax, (5.2, 2.75), (2.6, 1.4), text="predictions")
    arrow(ax, (9.2, 2.75), (3.3, 1.4))
    arrow(ax, (7.0, 2.75), (9.7, 1.4), text="γ, aleatoric, epistemic")
    arrow(ax, (12.45, 4.55), (12.2, 1.4), dashed=True, text="verify")
    arrow(ax, (8.3, 0.8), (9.1, 0.8), style="<|-|>", text="JSON")
    ax.set_title("FoodTrace system architecture", fontsize=13, weight="bold", loc="left", color=INK)
    save(fig, "architecture")


def actor(ax, x, y, name):
    ax.add_patch(plt.Circle((x, y + 0.55), 0.16, fc="white", ec=INK, lw=1.2))
    ax.plot([x, x], [y + 0.39, y - 0.05], color=INK, lw=1.2)
    ax.plot([x - 0.28, x + 0.28], [y + 0.22, y + 0.22], color=INK, lw=1.2)
    ax.plot([x, x - 0.22], [y - 0.05, y - 0.4], color=INK, lw=1.2)
    ax.plot([x, x + 0.22], [y - 0.05, y - 0.4], color=INK, lw=1.2)
    ax.text(x, y - 0.62, name, ha="center", va="top", fontsize=9.5, weight="bold")


def use_case():
    fig, ax = plt.subplots(figsize=(12, 8.4))
    ax.set_xlim(0, 12); ax.set_ylim(0, 8.4); ax.axis("off")
    ax.add_patch(FancyBboxPatch((2.7, 0.3), 6.6, 7.6, boxstyle="round,pad=0.02,rounding_size=0.1",
                                fc="white", ec=INK, lw=1.2))
    ax.text(6.0, 7.65, "FoodTrace", ha="center", fontsize=11.5, weight="bold")

    cases = {
        "browse": (6.0, 6.95, "Browse supply map"),
        "forecast": (6.0, 6.15, "View node forecast\n& uncertainty"),
        "recalls": (6.0, 5.3, "Inspect recall history\n& traceability checks"),
        "eval": (6.0, 4.45, "Review evaluation\n& hypothesis results"),
        "verify": (6.0, 3.6, "Verify ledger integrity"),
        "tamper": (6.0, 2.75, "Run tamper demonstration"),
        "pipeline": (6.0, 1.9, "Refresh data & retrain"),
        "fetch": (6.0, 1.05, "Download public datasets"),
    }
    for key, (x, y, label) in cases.items():
        ax.add_patch(Ellipse((x, y), 3.5, 0.68, fc=BLUE_SOFT, ec=INK, lw=1))
        ax.text(x, y, label, ha="center", va="center", fontsize=8.8)

    actor(ax, 1.2, 6.1, "Supply chain\nanalyst")
    actor(ax, 1.2, 3.4, "Risk / credit\nofficer")
    actor(ax, 10.8, 3.4, "Auditor")
    actor(ax, 10.8, 1.2, "Data\nadministrator")

    def link(a, key, side):
        x, y, _ = cases[key]
        ax.plot([a[0], x + (-1.75 if side == "L" else 1.75)], [a[1], y], color=INK, lw=0.9)

    for k in ("browse", "forecast", "recalls"):
        link((1.5, 6.35), k, "L")
    for k in ("forecast", "eval"):
        link((1.5, 3.65), k, "L")
    for k in ("verify", "tamper", "recalls"):
        link((10.5, 3.65), k, "R")
    for k in ("pipeline",):
        link((10.5, 1.45), k, "R")
    # include relationship
    arrow(ax, (6.0, 1.56), (6.0, 1.39), style="-|>", dashed=True)
    ax.text(6.35, 1.47, "«include»", fontsize=8, color=MUTED, va="center")
    arrow(ax, (7.2, 3.08), (7.2, 3.27), style="-|>", dashed=True)
    ax.text(7.35, 3.17, "«include»", fontsize=8, color=MUTED, va="center")
    ax.set_title("Use case diagram", fontsize=13, weight="bold", loc="left")
    save(fig, "use_case")


def uml_class(ax, x, y, w, name, attrs, methods, fill=GREY_SOFT):
    line_h = 0.27
    h_name, h_attr, h_meth = 0.45, line_h * len(attrs) + 0.15, line_h * len(methods) + 0.15
    top = y
    ax.add_patch(plt.Rectangle((x, top - h_name), w, h_name, fc=fill, ec=INK, lw=1.1))
    ax.text(x + w / 2, top - h_name / 2, name, ha="center", va="center", weight="bold", fontsize=9.8)
    ax.add_patch(plt.Rectangle((x, top - h_name - h_attr), w, h_attr, fc="white", ec=INK, lw=1.1))
    for i, a in enumerate(attrs):
        ax.text(x + 0.1, top - h_name - 0.1 - i * line_h, a, va="top", fontsize=8.1, family="DejaVu Sans Mono")
    ax.add_patch(plt.Rectangle((x, top - h_name - h_attr - h_meth), w, h_meth, fc="white", ec=INK, lw=1.1))
    for i, m in enumerate(methods):
        ax.text(x + 0.1, top - h_name - h_attr - 0.1 - i * line_h, m, va="top", fontsize=8.1,
                family="DejaVu Sans Mono")
    return (x, top, w, h_name + h_attr + h_meth)


def class_diagram():
    fig, ax = plt.subplots(figsize=(14.5, 10))
    ax.set_xlim(0, 14.5); ax.set_ylim(0, 10); ax.axis("off")

    def bottom(c):
        return c[1] - c[3]

    com = uml_class(ax, 0.2, 9.6, 3.4, "Commodity",
                    ["key: str", "label: str", "hs_codes: tuple", "fda_terms: tuple", "nors_terms: tuple",
                     "perishable: bool"], [], fill=BLUE_SOFT)
    samp = uml_class(ax, 0.2, 6.6, 3.4, "Samples",
                     ["x_seq: ndarray (N,24,F)", "x_static: ndarray", "y: ndarray", "node: ndarray",
                      "period: ndarray"], ["make_samples(frames)"], fill=BLUE_SOFT)
    fold = uml_class(ax, 0.2, 3.0, 3.4, "Fold",
                     ["name: str", "train_end: str", "val_end: str", "test_end: str"], [], fill=BLUE_SOFT)

    enc = uml_class(ax, 4.5, 9.6, 3.3, "Encoder", ["gru: GRU(2 layers)", "mix: Sequential"],
                    ["forward(x_seq, x_static)"], fill=GREEN_SOFT)
    ev = uml_class(ax, 4.5, 7.75, 3.3, "EvidentialNet", ["encoder: Encoder", "head: Linear(64, 4)"],
                   ["forward() -> γ, ν, α, β"], fill=GREEN_SOFT)
    ga = uml_class(ax, 4.5, 5.95, 3.3, "GaussianNet", ["encoder: Encoder", "head: Linear(64, 2)"],
                   ["forward() -> mean, var"], fill=GREEN_SOFT)
    pt = uml_class(ax, 4.5, 4.15, 3.3, "PointNet", ["encoder: Encoder", "head: Linear(64, 1)"],
                   ["forward() -> ŷ"], fill=GREEN_SOFT)
    fc = uml_class(ax, 4.5, 2.35, 3.3, "Forecaster",
                   ["model: EvidentialNet", "frames: dict", "epi_cut, alea_cut: float"],
                   ["next_month(node_id)", "history(node_id)"], fill=GREEN_SOFT)

    blk = uml_class(ax, 8.9, 9.6, 3.0, "Block",
                    ["index: int", "period: str", "prev_hash: str", "merkle: str", "record_count: int",
                     "nonce: int", "hash: str", "records: list"],
                    ["header()", "compute_hash()", "mine(difficulty)"], fill=ORANGE_SOFT)
    prob = uml_class(ax, 8.9, 5.2, 3.0, "Problem",
                     ["block_index: int", "period: str", "kind: str", "detail: str"], [], fill=ORANGE_SOFT)
    store = uml_class(ax, 12.3, 9.6, 2.0, "LedgerStore", ["con: sqlite3"],
                      ["build()", "load_blocks()", "verify_all()"], fill=ORANGE_SOFT)
    api = uml_class(ax, 8.9, 2.35, 5.4, "FastAPI app", [],
                    ["overview()  nodes(month)  node_detail(id)", "results()  commodities()",
                     "ledger_blocks()  ledger_verify()", "ledger_tamper(t)  ledger_restore()"], fill=BLUE_SOFT)

    def lbl(x, y, t, ha="left"):
        ax.text(x, y, t, fontsize=8, color=MUTED, ha=ha, va="center",
                bbox=dict(fc="white", ec="none", pad=1))

    # composition: every network owns one Encoder (shared trunk on the right)
    trunk = 8.25
    right = 4.5 + 3.3
    for c in (ev, ga, pt):
        y = c[1] - 0.22
        ax.plot([right, trunk], [y, y], color=INK, lw=1.1)
        ax.plot([right + 0.07], [y], marker="D", ms=7, color=INK)
    ax.plot([trunk, trunk], [pt[1] - 0.22, enc[1] - 0.22], color=INK, lw=1.1)
    arrow(ax, (trunk, enc[1] - 0.22), (right, enc[1] - 0.22))
    lbl(trunk + 0.05, 6.6, "has 1")

    # data side
    arrow(ax, (1.9, fold[1]), (1.9, bottom(samp)), dashed=True)
    lbl(1.95, (fold[1] + bottom(samp)) / 2, "splits")
    arrow(ax, (1.9, samp[1]), (1.9, bottom(com)), dashed=True)
    lbl(1.95, (samp[1] + bottom(com)) / 2, "one series per node of")
    arrow(ax, (3.6, samp[1] - 0.3), (4.5, samp[1] - 0.3), dashed=True)
    lbl(4.05, samp[1] - 0.08, "trains", ha="center")

    # serving
    ax.plot([4.5, 4.2, 4.2], [fc[1] - 0.22, fc[1] - 0.22, ev[1] - 1.1], color=INK, lw=1.1, ls="--")
    arrow(ax, (4.2, ev[1] - 1.1), (4.5, ev[1] - 1.1), dashed=True)
    lbl(4.15, 3.2, "loads", ha="right")
    arrow(ax, (8.9, fc[1] - 0.6), (right, fc[1] - 0.6), dashed=True)
    lbl(8.35, fc[1] - 0.38, "calls", ha="center")

    # ledger side
    arrow(ax, (12.3, store[1] - 0.22), (11.9, store[1] - 0.22))
    lbl(12.1, store[1] + 0.05, "1..*", ha="center")
    arrow(ax, (10.4, bottom(blk)), (10.4, prob[1]), dashed=True)
    lbl(10.45, (bottom(blk) + prob[1]) / 2, "verify() returns")
    arrow(ax, (13.3, api[1]), (13.3, bottom(store)), dashed=True)
    lbl(13.35, 5.0, "reads")
    ax.set_title("Class diagram", fontsize=13, weight="bold", loc="left")
    save(fig, "class_diagram")


if __name__ == "__main__":
    architecture()
    use_case()
    class_diagram()
