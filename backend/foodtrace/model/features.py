"""Build model inputs from the processed tables.

Every feature at month t only uses information that was public by the end
of month t: import figures up to t and FDA recalls whose *report date* is
on or before t. Recall initiation dates and CDC outbreaks are kept out of
the inputs entirely - they are what the evaluation tries to anticipate.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import PROCESSED_DIR
from ..data.commodities import BY_KEY

WINDOW = 24          # months of history the encoder sees
SHRINK_K = 5.0       # pseudo-count for the verification-ratio prior

SEQ_FEATURES = [
    "y",                    # standardised log1p(import kg)
    "y_missing",            # 1 when the month had zero recorded imports
    "month_sin", "month_cos",
    "comm_recalls",         # recalls for this commodity reported this month (log1p)
    "node_recalls",         # recalls naming this origin country reported this month (log1p)
    "comm_recalls_12m",     # trailing 12-month commodity recall count (log1p)
    "months_since_recall",  # since last commodity recall report, capped at 24, scaled 0-1
]
STATIC_FEATURES = ["verification_ratio", "perishable", "log_volume"]


@dataclass
class Fold:
    name: str
    train_end: str   # last target month used for training
    val_end: str     # last target month used for early stopping
    test_end: str    # last target month scored


# Rolling-origin evaluation. Series start in 2016-01 and the encoder needs
# 24 months of history, so the first trainable target month is 2018-01.
FOLDS = [
    Fold("2021-22", "2019-12", "2020-12", "2022-12"),
    Fold("2023-26", "2021-12", "2022-12", "2026-07"),
]
MAIN_FOLD = FOLDS[-1]


def load_tables():
    panel = pd.read_parquet(PROCESSED_DIR / "panel.parquet")
    nodes = pd.read_parquet(PROCESSED_DIR / "nodes.parquet")
    recalls = pd.read_parquet(PROCESSED_DIR / "recalls.parquet")
    outbreaks = pd.read_parquet(PROCESSED_DIR / "outbreaks.parquet")
    for df, cols in ((panel, ["period"]), (recalls, ["initiated", "reported"]), (outbreaks, ["period"])):
        for c in cols:
            df[c] = pd.PeriodIndex(df[c].where(df[c].notna() & (df[c] != "NaT")), freq="M")
    return panel, nodes, recalls, outbreaks


def verification_ratios(nodes, recalls, as_of: str) -> pd.DataFrame:
    """Share of a node's FDA recall records that passed all four traceability
    checks, using only recalls reported up to ``as_of``.

    Nodes with few records are pulled toward their commodity's rate, and
    commodities toward the overall rate (simple empirical-Bayes shrinkage),
    so one or two records cannot swing a node to 0 or 1.
    """
    cutoff = pd.Period(as_of, freq="M")
    r = recalls[recalls["reported"].notna() & (recalls["reported"] <= cutoff)]
    global_rate = r["verified"].mean() if len(r) else 0.5
    comm = r.groupby("commodity")["verified"].agg(["sum", "count"])
    comm_rate = (comm["sum"] + SHRINK_K * global_rate) / (comm["count"] + SHRINK_K)

    out = []
    for n in nodes.itertuples():
        p_c = comm_rate.get(n.commodity, global_rate)
        mine = r[(r["commodity"] == n.commodity) & r["origin_countries"].apply(lambda cs: n.country in list(cs))]
        v, k = mine["verified"].sum(), len(mine)
        out.append({"node_id": n.node_id, "n_records": k, "n_verified": int(v),
                    "commodity_rate": p_c,
                    "verification_ratio": (v + SHRINK_K * p_c) / (k + SHRINK_K)})
    return pd.DataFrame(out)


def node_frame(panel, nodes, recalls, ratios, train_end: str) -> dict[str, pd.DataFrame]:
    """Per-node monthly feature table, standardised with training-period stats."""
    cutoff = pd.Period(train_end, freq="M")
    reported = recalls[recalls["reported"].notna()]
    comm_counts = reported.groupby(["commodity", "reported"]).size()
    ratio_by_node = ratios.set_index("node_id")["verification_ratio"]
    frames = {}
    for n in nodes.itertuples():
        g = panel[panel["node_id"] == n.node_id].sort_values("period").reset_index(drop=True)
        logq = np.log1p(g["qty_kg"].to_numpy())
        train_mask = (g["period"] <= cutoff).to_numpy()
        mu, sd = logq[train_mask].mean(), logq[train_mask].std() + 1e-6
        f = pd.DataFrame({"period": g["period"], "qty_kg": g["qty_kg"]})
        f["y"] = (logq - mu) / sd
        f["y_missing"] = (g["qty_kg"] <= 0).astype(float)
        month = g["period"].dt.month.to_numpy()
        f["month_sin"] = np.sin(2 * np.pi * month / 12)
        f["month_cos"] = np.cos(2 * np.pi * month / 12)

        cc = comm_counts.get(n.commodity, pd.Series(dtype=float))
        cc = cc.reindex(g["period"], fill_value=0).to_numpy().astype(float)
        mine = reported[(reported["commodity"] == n.commodity) &
                        reported["origin_countries"].apply(lambda cs: n.country in list(cs))]
        nc = mine.groupby("reported").size().reindex(g["period"], fill_value=0).to_numpy().astype(float)
        f["comm_recalls"] = np.log1p(cc)
        f["node_recalls"] = np.log1p(nc)
        f["comm_recalls_12m"] = np.log1p(pd.Series(cc).rolling(12, min_periods=1).sum().to_numpy())
        since, last = [], None
        for i, c in enumerate(cc):
            if c > 0:
                last = i
            since.append(24 if last is None else min(i - last, 24))
        f["months_since_recall"] = np.array(since) / 24.0

        f["verification_ratio"] = ratio_by_node[n.node_id]
        f["perishable"] = float(BY_KEY[n.commodity].perishable)
        f["log_volume"] = np.log10(g["qty_kg"][train_mask].mean() + 1)
        f.attrs.update(node_id=n.node_id, commodity=n.commodity, country=n.country, mu=mu, sd=sd)
        frames[n.node_id] = f
    # log_volume spans orders of magnitude; centre it so it sits near the other inputs.
    lv = np.array([f["log_volume"].iloc[0] for f in frames.values()])
    for f in frames.values():
        f["log_volume"] = (f["log_volume"] - lv.mean()) / (lv.std() + 1e-6)
    return frames


@dataclass
class Samples:
    x_seq: np.ndarray      # (N, WINDOW, F)
    x_static: np.ndarray   # (N, S)
    y: np.ndarray          # (N,)
    node: np.ndarray       # node_id per sample
    period: np.ndarray     # target month (str)


def make_samples(frames: dict[str, pd.DataFrame], start=None, end=None) -> Samples:
    """Windows whose *target* month falls in (start, end]."""
    xs, ss, ys, nodes, periods = [], [], [], [], []
    lo = pd.Period(start, freq="M") if start else None
    hi = pd.Period(end, freq="M") if end else None
    for node_id, f in frames.items():
        seq = f[SEQ_FEATURES].to_numpy(dtype=np.float32)
        static = f[STATIC_FEATURES].iloc[0].to_numpy(dtype=np.float32)
        y = f["y"].to_numpy(dtype=np.float32)
        per = f["period"]
        for t in range(WINDOW, len(f)):
            p = per.iloc[t]
            if (lo is not None and p <= lo) or (hi is not None and p > hi):
                continue
            xs.append(seq[t - WINDOW:t])
            ss.append(static)
            ys.append(y[t])
            nodes.append(node_id)
            periods.append(str(p))
    return Samples(np.stack(xs), np.stack(ss), np.array(ys, dtype=np.float32),
                   np.array(nodes), np.array(periods))


def fold_data(fold: Fold, tables=None):
    panel, nodes, recalls, outbreaks = tables or load_tables()
    ratios = verification_ratios(nodes, recalls, fold.train_end)
    frames = node_frame(panel, nodes, recalls, ratios, fold.train_end)
    train = make_samples(frames, None, fold.train_end)
    val = make_samples(frames, fold.train_end, fold.val_end)
    test = make_samples(frames, fold.val_end, fold.test_end)
    return frames, ratios, train, val, test
