"""Score the models and run the three analyses from the proposal.

    python -m foodtrace.model.evaluate

Writes artifacts/results.json, which the API serves to the dashboard.

1. Accuracy   - MAE / RMSE / MAPE in kilograms, plus MASE against the
                seasonal-naive forecast (scale-free, so big and small
                nodes count equally).
2. Calibration - NLL, prediction interval coverage (PICP) and width at
                50/80/90/95 %, for the evidential model and MC-dropout.
3. Hypotheses -
   H1  verified vs unverified nodes: does a higher traceability
       (verification) ratio go with lower epistemic uncertainty?
   H2  lead signal: is epistemic uncertainty higher in the months before
       an FDA recall is initiated than in matched quiet months?
   H3  is the H1 gap concentrated in perishable categories?
"""
import json
import math

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from ..config import ARTIFACTS_DIR
from . import features as feat
from .train import LEVELS, student_t_interval

LEAD_MONTHS = 3      # window before a recall initiation
QUIET_GAP = 6        # matched control months must be this far from any event


def to_kg(z, mu, sd):
    return np.expm1(np.clip(z * sd + mu, 0, 40))


def accuracy(df):
    out = {}
    models = {"evidential": "ev_gamma", "mc_dropout": "mc_mean", "gru_point": "point",
              "arima": "arima", "seasonal_naive": "seasonal_naive", "naive": "naive"}
    # MASE denominator per node: mean abs error of seasonal naive (log scale).
    denom = df.assign(e=(df["y"] - df["seasonal_naive"]).abs()).groupby("node_id")["e"].mean()
    for name, col in models.items():
        d = df.dropna(subset=[col])
        pred = to_kg(d[col], d["mu"], d["sd"])
        act = to_kg(d["y"], d["mu"], d["sd"])
        err = pred - act
        # Plain MAPE explodes on the few months where a node imported almost
        # nothing (a 50 t forecast against 3 kg is a 1.6M% error). It is
        # reported on months with at least 10% of the node's typical volume,
        # alongside WAPE (total absolute error / total volume), which has no
        # such problem.
        typical = to_kg(d["y"], d["mu"], d["sd"]).groupby(d["node_id"]).transform("median")
        ok = act >= 0.1 * typical
        abs_log = (d["y"] - d[col]).abs()
        mase = (abs_log.groupby(d["node_id"]).mean() / denom).replace([np.inf], np.nan).mean()
        out[name] = {
            "mae_kg": float(np.mean(np.abs(err))),
            "rmse_kg": float(np.sqrt(np.mean(err ** 2))),
            "mape_pct": float(np.mean(np.abs(err[ok] / act[ok])) * 100),
            "wape_pct": float(np.sum(np.abs(err)) / np.sum(act) * 100),
            "mae_log": float(abs_log.mean()),
            "mase": float(mase),
            "n": int(len(d)),
        }
    return out


def calibration(df):
    y = df["y"].to_numpy()
    g, nu, a, b = (df[c].to_numpy() for c in ("ev_gamma", "ev_nu", "ev_alpha", "ev_beta"))
    scale = np.sqrt(b * (1 + nu) / (nu * a))
    ev_nll = -stats.t.logpdf(y, 2 * a, loc=g, scale=scale)

    mc_m = df["mc_mean"].to_numpy()
    mc_v = (df["mc_aleatoric"] + df["mc_epistemic"]).to_numpy()
    mc_nll = 0.5 * (np.log(2 * math.pi * mc_v) + (y - mc_m) ** 2 / mc_v)

    ar = df.dropna(subset=["arima", "arima_var"])
    ar_nll = 0.5 * (np.log(2 * math.pi * ar["arima_var"]) + (ar["y"] - ar["arima"]) ** 2 / ar["arima_var"])

    res = {"evidential": {"nll": float(np.mean(ev_nll))},
           "mc_dropout": {"nll": float(np.mean(mc_nll))},
           "arima": {"nll": float(np.mean(ar_nll))}}
    for name in res:
        res[name]["levels"] = []
    for lvl in LEVELS:
        lo, hi = student_t_interval(g, nu, a, b, lvl)
        z = stats.norm.ppf(0.5 + lvl / 2)
        for name, (l, h, yy) in {
            "evidential": (lo, hi, y),
            "mc_dropout": (mc_m - z * np.sqrt(mc_v), mc_m + z * np.sqrt(mc_v), y),
            "arima": (ar["arima"] - z * np.sqrt(ar["arima_var"]), ar["arima"] + z * np.sqrt(ar["arima_var"]), ar["y"]),
        }.items():
            l, h, yy = np.asarray(l), np.asarray(h), np.asarray(yy)
            res[name]["levels"].append({"level": lvl,
                                        "picp": float(np.mean((yy >= l) & (yy <= h))),
                                        "width": float(np.mean(h - l))})
    for name in res:
        res[name]["mean_coverage_gap"] = float(np.mean([abs(x["picp"] - x["level"]) for x in res[name]["levels"]]))
    return res


def node_summary(df, ratios, frames):
    g = df.groupby("node_id").agg(epistemic=("ev_epistemic", "mean"),
                                  aleatoric=("ev_aleatoric", "mean"),
                                  mc_epistemic=("mc_epistemic", "mean")).reset_index()
    g = g.merge(ratios, on="node_id")
    meta = []
    for node_id, f in frames.items():
        q = f.loc[f["period"] <= pd.Period(feat.MAIN_FOLD.train_end, freq="M"), "qty_kg"]
        lq = np.log1p(q)
        meta.append({"node_id": node_id, "commodity": f.attrs["commodity"], "country": f.attrs["country"],
                     "volatility": float(lq.diff().abs().mean()),
                     "zero_share": float((q <= 0).mean()),
                     "log_volume": float(np.log10(q.mean() + 1))})
    g = g.merge(pd.DataFrame(meta), on="node_id")
    from ..data.commodities import BY_KEY
    g["perishable"] = g["commodity"].map(lambda k: BY_KEY[k].perishable)
    median = g["verification_ratio"].median()
    g["verified_group"] = np.where(g["verification_ratio"] > median, "verified", "unverified")
    return g


def h1_verification(nodes):
    v = nodes.loc[nodes["verified_group"] == "verified", "epistemic"]
    u = nodes.loc[nodes["verified_group"] == "unverified", "epistemic"]
    mw = stats.mannwhitneyu(v, u, alternative="less")
    # Rank-biserial effect size: -1..1, negative = verified nodes lower.
    rbc = 1 - 2 * mw.statistic / (len(v) * len(u))
    d = nodes.assign(log_epi=np.log(nodes["epistemic"]))
    ols = smf.ols("log_epi ~ verification_ratio + volatility + zero_share + log_volume + C(commodity)",
                  data=d).fit(cov_type="HC3")
    ols_simple = smf.ols("log_epi ~ verification_ratio + volatility + zero_share + log_volume",
                         data=d).fit(cov_type="HC3")
    def coef(m):
        return {"coef": float(m.params["verification_ratio"]),
                "p": float(m.pvalues["verification_ratio"]),
                "ci": [float(x) for x in m.conf_int().loc["verification_ratio"]],
                "r2": float(m.rsquared), "n": int(m.nobs)}
    return {
        "median_split": float(nodes["verification_ratio"].median()),
        "verified": {"n": int(len(v)), "median_epistemic": float(v.median())},
        "unverified": {"n": int(len(u)), "median_epistemic": float(u.median())},
        "mann_whitney_u": float(mw.statistic), "p_one_sided": float(mw.pvalue),
        "rank_biserial": float(-rbc),
        "regression_controls": coef(ols_simple),
        "regression_with_commodity_fe": coef(ols),
        "spearman": dict(zip(("rho", "p"), map(float, stats.spearmanr(nodes["verification_ratio"], nodes["epistemic"])))),
    }


def h3_by_perishability(nodes):
    out = {}
    for flag, sub in nodes.groupby("perishable"):
        v = sub.loc[sub["verified_group"] == "verified", "epistemic"]
        u = sub.loc[sub["verified_group"] == "unverified", "epistemic"]
        key = "perishable" if flag else "shelf_stable"
        if len(v) < 3 or len(u) < 3:
            out[key] = {"n_verified": int(len(v)), "n_unverified": int(len(u)), "note": "too few nodes to test"}
            continue
        mw = stats.mannwhitneyu(v, u, alternative="less")
        out[key] = {"n_verified": int(len(v)), "n_unverified": int(len(u)),
                    "median_verified": float(v.median()), "median_unverified": float(u.median()),
                    "p_one_sided": float(mw.pvalue),
                    "rank_biserial": float(-(1 - 2 * mw.statistic / (len(v) * len(u))))}
    return out


def h2_lead(all_preds, recalls, nodes_meta):
    """Before-event vs quiet-month epistemic uncertainty, within the same node.

    An event is an FDA recall whose initiation month falls in a fold's test
    window. It is linked to a node when the recall names the node's origin
    country; otherwise to every node of the commodity ('commodity-level').
    For each event the mean epistemic uncertainty over the LEAD_MONTHS
    before initiation is compared with the same node's mean over months at
    least QUIET_GAP away from any recall of that commodity. Each node's
    uncertainty is first divided by its own median so nodes are comparable.
    """
    p = all_preds.copy()
    p["period"] = pd.PeriodIndex(p["period"], freq="M")
    p["epi_rel"] = p["ev_epistemic"] / p.groupby("node_id")["ev_epistemic"].transform("median")
    p["mc_rel"] = p["mc_epistemic"] / p.groupby("node_id")["mc_epistemic"].transform("median")
    country = nodes_meta.set_index("node_id")["country"]
    commodity = nodes_meta.set_index("node_id")["commodity"]
    rec = recalls[recalls["initiated"].notna()]

    results = {}
    for scope in ("node", "commodity"):
        pairs = []
        for node_id, g in p.groupby("node_id"):
            g = g.set_index("period").sort_index()
            c_rec = rec[rec["commodity"] == commodity[node_id]]
            if scope == "node":
                ev = c_rec[c_rec["origin_countries"].apply(lambda cs: country[node_id] in list(cs))]
            else:
                ev = c_rec
            event_months = sorted(set(ev["initiated"]) & set(g.index))
            if not event_months:
                continue
            all_rec_months = set(c_rec["initiated"]) | set(c_rec["reported"].dropna())
            quiet = [m for m in g.index
                     if all(abs((m - e).n) >= QUIET_GAP for e in all_rec_months)]
            if len(quiet) < 3:
                continue
            base_ev = g.loc[quiet, "epi_rel"].mean()
            base_mc = g.loc[quiet, "mc_rel"].mean()
            for e in event_months:
                before = [e - k for k in range(1, LEAD_MONTHS + 1) if (e - k) in g.index]
                if len(before) < LEAD_MONTHS:
                    continue
                pairs.append({"node_id": node_id, "event_month": str(e),
                              "pre_ev": g.loc[before, "epi_rel"].mean(), "quiet_ev": base_ev,
                              "pre_mc": g.loc[before, "mc_rel"].mean(), "quiet_mc": base_mc})
        df = pd.DataFrame(pairs)
        # Fewer than 10 event windows is too few for a signed-rank test to mean much.
        if len(df) < 10:
            results[scope] = {"n_events": int(len(df)), "note": "too few events to test"}
            continue
        df = df.drop_duplicates(["node_id", "event_month"])
        out = {"n_events": int(len(df)), "n_nodes": int(df["node_id"].nunique())}
        for model in ("ev", "mc"):
            diff = df[f"pre_{model}"] - df[f"quiet_{model}"]
            w = stats.wilcoxon(diff, alternative="greater")
            out[model] = {"median_pre": float(df[f"pre_{model}"].median()),
                          "median_quiet": float(df[f"quiet_{model}"].median()),
                          "median_ratio": float((df[f"pre_{model}"] / df[f"quiet_{model}"]).median()),
                          "share_higher_before": float((diff > 0).mean()),
                          "wilcoxon_p_one_sided": float(w.pvalue)}
        results[scope] = out
        df.to_csv(ARTIFACTS_DIR / f"lead_pairs_{scope}.csv", index=False)
    return results


def seed_stability(df):
    seeds = [c.split("_s")[-1] for c in df.columns if c.startswith("ev_gamma_s")]
    if not seeds:
        return None
    def mae(col):
        return float((df["y"] - df[col]).abs().mean())
    rows = {"evidential": [mae("ev_gamma")] + [mae(f"ev_gamma_s{s}") for s in seeds],
            "mc_dropout": [mae("mc_mean")] + [mae(f"mc_mean_s{s}") for s in seeds],
            "gru_point": [mae("point")] + [mae(f"point_s{s}") for s in seeds]}
    return {k: {"mae_log_mean": float(np.mean(v)), "mae_log_sd": float(np.std(v)), "runs": len(v)}
            for k, v in rows.items()}


def main():
    tables = feat.load_tables()
    panel, nodes, recalls, outbreaks = tables
    main_fold = feat.MAIN_FOLD
    preds = {f.name: pd.read_parquet(ARTIFACTS_DIR / f"predictions_{f.name}.parquet") for f in feat.FOLDS}
    df = preds[main_fold.name]
    ratios = pd.read_parquet(ARTIFACTS_DIR / f"verification_{main_fold.name}.parquet")
    frames = feat.node_frame(panel, nodes, recalls, ratios, main_fold.train_end)

    node_table = node_summary(df, ratios, frames)
    all_preds = pd.concat(preds.values(), ignore_index=True)

    results = {
        "main_fold": json.loads((ARTIFACTS_DIR / "main_fold.json").read_text()),
        "data": {"nodes": int(len(nodes)), "commodities": int(nodes["commodity"].nunique()),
                 "countries": int(nodes["country"].nunique()),
                 "months": int(panel["period"].nunique()),
                 "first_month": str(panel["period"].min()), "last_month": str(panel["period"].max()),
                 "recalls_matched": int(len(recalls)),
                 "recalls_verified_share": float(recalls["verified"].mean()),
                 "outbreaks_matched": int(len(outbreaks))},
        "accuracy": accuracy(df),
        "accuracy_by_fold": {k: accuracy(v) for k, v in preds.items()},
        "calibration": calibration(df),
        "seed_stability": seed_stability(df),
        "h1_verification": h1_verification(node_table),
        "h2_lead": h2_lead(all_preds, recalls, nodes),
        "h3_perishability": h3_by_perishability(node_table),
    }
    node_table.to_csv(ARTIFACTS_DIR / "node_summary.csv", index=False)
    (ARTIFACTS_DIR / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({k: results[k] for k in ("accuracy", "h1_verification", "h2_lead")}, indent=1)[:6000])


if __name__ == "__main__":
    main()
