"""Train the evidential model and the neural baselines on every fold.

    python -m foodtrace.model.train            # all folds
    python -m foodtrace.model.train --quick    # one seed, fewer epochs

Writes artifacts/predictions_<fold>.parquet (one row per node-month in the
fold's test window, all models side by side) and, for the main fold, the
model weights plus node scaling stats used by the API.
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
import torch
from scipy import stats

from ..config import ARTIFACTS_DIR
from . import features as feat
from .baselines import arima_forecasts, naive_forecasts
from .nets import (EvidentialNet, GaussianNet, PointNet, evidential_loss, gaussian_nll,
                   nig_moments)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
LAMBDAS = (0.001, 0.01, 0.1)
LEVELS = (0.5, 0.8, 0.9, 0.95)
MC_PASSES = 50


def _tensors(s: feat.Samples):
    return (torch.tensor(s.x_seq, device=DEVICE),
            torch.tensor(s.x_static, device=DEVICE),
            torch.tensor(s.y, device=DEVICE))


def _fit(model, loss_fn, train, val, epochs, lr=1e-3, batch=256, patience=30, seed=0):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model.to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    xs, xc, y = _tensors(train)
    vs, vc, vy = _tensors(val)
    best, best_state, stale = float("inf"), None, 0
    n = len(y)
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n, device=DEVICE)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            loss = loss_fn(model(xs[idx], xc[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            v = loss_fn(model(vs, vc), vy).item()
        if v < best - 1e-4:
            best, stale = v, 0
            best_state = {k: t.detach().clone() for k, t in model.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, best, epoch + 1


def student_t_interval(gamma, nu, alpha, beta, level):
    df = 2 * alpha
    scale = np.sqrt(beta * (1 + nu) / (nu * alpha))
    q = stats.t.ppf(0.5 + level / 2, df)
    return gamma - q * scale, gamma + q * scale


def coverage_gap(y, lo_hi_by_level):
    return float(np.mean([abs(np.mean((y >= lo) & (y <= hi)) - lvl)
                          for lvl, (lo, hi) in lo_hi_by_level.items()]))


def predict_evidential(model, s):
    xs, xc, _ = _tensors(s)
    with torch.no_grad():
        g, nu, a, b = (t.cpu().numpy() for t in model(xs, xc))
    return g, nu, a, b


def predict_mc(model, s, passes=MC_PASSES):
    xs, xc, _ = _tensors(s)
    model.train()   # keep dropout on
    means, vars_ = [], []
    with torch.no_grad():
        for _ in range(passes):
            m, v = model(xs, xc)
            means.append(m.cpu().numpy())
            vars_.append(v.cpu().numpy())
    model.eval()
    means, vars_ = np.stack(means), np.stack(vars_)
    return means.mean(0), vars_.mean(0), means.var(0)


def train_fold(fold: feat.Fold, seeds, epochs, tables):
    frames, ratios, train, val, test = feat.fold_data(fold, tables)
    n_seq, n_static = train.x_seq.shape[-1], train.x_static.shape[-1]
    print(f"[{fold.name}] train {len(train.y)}  val {len(val.y)}  test {len(test.y)}  on {DEVICE}")

    # Pick lambda on the validation window by calibration, not NLL: lower
    # lambda always wins on NLL but gives overconfident intervals.
    lam_scores = {}
    for lam in LAMBDAS:
        m, _, _ = _fit(EvidentialNet(n_seq, n_static),
                       lambda out, y, lam=lam: evidential_loss(y, *out, lam), train, val, epochs, seed=0)
        g, nu, a, b = predict_evidential(m, val)
        lam_scores[lam] = coverage_gap(val.y, {l: student_t_interval(g, nu, a, b, l) for l in LEVELS})
    lam = min(lam_scores, key=lam_scores.get)
    print(f"  lambda calibration gaps {lam_scores} -> {lam}")

    out = pd.DataFrame({"node_id": test.node, "period": test.period, "y": test.y})
    per_seed = []
    for seed in seeds:
        t0 = time.time()
        ev, ev_val, ev_ep = _fit(EvidentialNet(n_seq, n_static),
                                 lambda o, y: evidential_loss(y, *o, lam), train, val, epochs, seed=seed)
        mc, _, mc_ep = _fit(GaussianNet(n_seq, n_static),
                            lambda o, y: gaussian_nll(y, *o), train, val, epochs, seed=seed)
        pt, _, pt_ep = _fit(PointNet(n_seq, n_static),
                            lambda o, y: torch.mean((o - y) ** 2), train, val, epochs, seed=seed)
        g, nu, a, b = predict_evidential(ev, test)
        _, alea, epi = nig_moments(g, nu, a, b)
        mc_mean, mc_alea, mc_epi = predict_mc(mc, test)
        with torch.no_grad():
            xs, xc, _ = _tensors(test)
            pt_pred = pt(xs, xc).cpu().numpy()
        per_seed.append(dict(seed=seed, ev=(g, nu, a, b, alea, epi), mc=(mc_mean, mc_alea, mc_epi), pt=pt_pred))
        print(f"  seed {seed}: epochs ev {ev_ep} mc {mc_ep} point {pt_ep}  ({time.time() - t0:.0f}s)")
        if seed == seeds[0]:
            first = (ev, mc, pt)

    # Seed 0 is the reported model; other seeds feed the stability table.
    s0 = per_seed[0]
    g, nu, a, b, alea, epi = s0["ev"]
    out["ev_gamma"], out["ev_nu"], out["ev_alpha"], out["ev_beta"] = g, nu, a, b
    out["ev_aleatoric"], out["ev_epistemic"] = alea, epi
    out["mc_mean"], out["mc_aleatoric"], out["mc_epistemic"] = s0["mc"]
    out["point"] = s0["pt"]
    for extra in per_seed[1:]:
        out[f"ev_gamma_s{extra['seed']}"] = extra["ev"][0]
        out[f"ev_epistemic_s{extra['seed']}"] = extra["ev"][5]
        out[f"mc_mean_s{extra['seed']}"] = extra["mc"][0]
        out[f"point_s{extra['seed']}"] = extra["pt"]

    out = out.merge(naive_forecasts(frames, test), on=["node_id", "period"], how="left")
    out = out.merge(arima_forecasts(frames, fold), on=["node_id", "period"], how="left")

    scale = pd.DataFrame([{"node_id": k, "mu": f.attrs["mu"], "sd": f.attrs["sd"]} for k, f in frames.items()])
    out = out.merge(scale, on="node_id")
    out["fold"] = fold.name
    out["lambda"] = lam
    out.to_parquet(ARTIFACTS_DIR / f"predictions_{fold.name}.parquet", index=False)
    ratios.to_parquet(ARTIFACTS_DIR / f"verification_{fold.name}.parquet", index=False)

    if fold is feat.MAIN_FOLD:
        ev, mc, pt = first
        torch.save({"state": ev.state_dict(), "n_seq": n_seq, "n_static": n_static,
                    "lambda": lam, "window": feat.WINDOW,
                    "seq_features": feat.SEQ_FEATURES, "static_features": feat.STATIC_FEATURES},
                   ARTIFACTS_DIR / "evidential.pt")
        torch.save({"state": mc.state_dict(), "n_seq": n_seq, "n_static": n_static},
                   ARTIFACTS_DIR / "mc_dropout.pt")
        (ARTIFACTS_DIR / "main_fold.json").write_text(json.dumps(
            {"fold": fold.name, "train_end": fold.train_end, "val_end": fold.val_end,
             "test_end": fold.test_end, "lambda": lam, "lambda_gaps": lam_scores,
             "seeds": list(seeds), "device": str(DEVICE)}, indent=2))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--fold", choices=[f.name for f in feat.FOLDS])
    args = ap.parse_args(argv)
    epochs = 60 if args.quick else 400
    tables = feat.load_tables()
    for fold in feat.FOLDS:
        if args.fold and fold.name != args.fold:
            continue
        seeds = (0,) if args.quick or fold is not feat.MAIN_FOLD else (0, 1, 2)
        train_fold(fold, seeds, epochs, tables)


if __name__ == "__main__":
    main()
