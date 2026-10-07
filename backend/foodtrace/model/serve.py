"""Load the trained evidential model and answer forecast queries.

Forecasts for any node-month are produced by running the saved network on
the 24 months before it, exactly as in training, so the API can show
uncertainty for historical months as well as the next unseen month.
"""
import json
from functools import lru_cache

import numpy as np
import pandas as pd
import torch
from scipy import stats

from ..config import ARTIFACTS_DIR
from . import features as feat
from .nets import EvidentialNet, nig_moments

# Thresholds for the traffic-light label. They are percentiles of the
# model's own uncertainty on the validation window, so "high" means high
# relative to what this model normally reports.
EPI_HIGH_PCT = 80
ALEA_HIGH_PCT = 80


class Forecaster:
    def __init__(self):
        ckpt = torch.load(ARTIFACTS_DIR / "evidential.pt", map_location="cpu", weights_only=False)
        self.model = EvidentialNet(ckpt["n_seq"], ckpt["n_static"])
        self.model.load_state_dict(ckpt["state"])
        self.model.eval()
        self.meta = json.loads((ARTIFACTS_DIR / "main_fold.json").read_text())
        tables = feat.load_tables()
        self.panel, self.nodes, self.recalls, self.outbreaks = tables
        self.ratios = feat.verification_ratios(self.nodes, self.recalls, self.meta["train_end"])
        self.frames = feat.node_frame(self.panel, self.nodes, self.recalls, self.ratios, self.meta["train_end"])
        self._history = self._run_all()
        val = self._history[(self._history["period"] > self.meta["train_end"]) &
                            (self._history["period"] <= self.meta["val_end"])]
        self.epi_cut = float(np.percentile(val["epistemic"], EPI_HIGH_PCT))
        self.alea_cut = float(np.percentile(val["aleatoric"], ALEA_HIGH_PCT))
        self._history["status"] = self._history.apply(self._status, axis=1)

    def _run_all(self) -> pd.DataFrame:
        s = feat.make_samples(self.frames)
        with torch.no_grad():
            g, nu, a, b = (t.numpy() for t in self.model(torch.tensor(s.x_seq), torch.tensor(s.x_static)))
        _, alea, epi = nig_moments(g, nu, a, b)
        df = pd.DataFrame({"node_id": s.node, "period": s.period, "y": s.y,
                           "gamma": g, "nu": nu, "alpha": a, "beta": b,
                           "aleatoric": alea, "epistemic": epi})
        scale = pd.DataFrame([{"node_id": k, "mu": f.attrs["mu"], "sd": f.attrs["sd"]}
                              for k, f in self.frames.items()])
        df = df.merge(scale, on="node_id")
        df["forecast_kg"] = np.expm1(df["gamma"] * df["sd"] + df["mu"]).clip(lower=0)
        df["actual_kg"] = np.expm1(df["y"] * df["sd"] + df["mu"]).clip(lower=0)
        for lvl in (0.8, 0.95):
            q = stats.t.ppf(0.5 + lvl / 2, 2 * df["alpha"])
            scale_t = np.sqrt(df["beta"] * (1 + df["nu"]) / (df["nu"] * df["alpha"]))
            tag = int(lvl * 100)
            df[f"lo{tag}_kg"] = np.expm1((df["gamma"] - q * scale_t) * df["sd"] + df["mu"]).clip(lower=0)
            df[f"hi{tag}_kg"] = np.expm1((df["gamma"] + q * scale_t) * df["sd"] + df["mu"]).clip(lower=0)
        df["split"] = np.select(
            [df["period"] <= self.meta["train_end"], df["period"] <= self.meta["val_end"]],
            ["train", "validation"], "test")
        return df

    def _status(self, row):
        if row["epistemic"] >= self.epi_cut:
            return "unreliable"
        if row["aleatoric"] >= self.alea_cut:
            return "volatile"
        return "reliable"

    def next_month(self, node_id):
        """Forecast for the month after the last observed one."""
        f = self.frames[node_id]
        seq = f[feat.SEQ_FEATURES].to_numpy(dtype=np.float32)[-feat.WINDOW:]
        static = f[feat.STATIC_FEATURES].iloc[0].to_numpy(dtype=np.float32)
        with torch.no_grad():
            g, nu, a, b = (t.item() for t in self.model(torch.tensor(seq[None]), torch.tensor(static[None])))
        alea, epi = b / (a - 1), b / (nu * (a - 1))
        mu, sd = f.attrs["mu"], f.attrs["sd"]
        scale_t = np.sqrt(b * (1 + nu) / (nu * a))
        out = {"period": str(f["period"].iloc[-1] + 1), "forecast_kg": float(np.expm1(g * sd + mu)),
               "aleatoric": alea, "epistemic": epi}
        for lvl in (0.8, 0.95):
            q = stats.t.ppf(0.5 + lvl / 2, 2 * a)
            out[f"lo{int(lvl*100)}_kg"] = float(max(np.expm1((g - q * scale_t) * sd + mu), 0))
            out[f"hi{int(lvl*100)}_kg"] = float(np.expm1((g + q * scale_t) * sd + mu))
        out["status"] = self._status(out)
        return out

    def history(self, node_id=None):
        h = self._history
        return h if node_id is None else h[h["node_id"] == node_id]


@lru_cache(maxsize=1)
def get_forecaster() -> Forecaster:
    return Forecaster()
