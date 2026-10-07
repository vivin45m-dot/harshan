"""Classical baselines, scored on the same standardised log scale as the nets."""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from . import features as feat


def naive_forecasts(frames, test: feat.Samples) -> pd.DataFrame:
    """Last month (naive) and same month last year (seasonal naive)."""
    rows = []
    wanted = set(zip(test.node, test.period))
    for node_id, f in frames.items():
        y = f["y"].to_numpy()
        per = f["period"].astype(str).to_numpy()
        for t in range(12, len(f)):
            if (node_id, per[t]) in wanted:
                rows.append({"node_id": node_id, "period": per[t],
                             "naive": y[t - 1], "seasonal_naive": y[t - 12]})
    return pd.DataFrame(rows)


def arima_forecasts(frames, fold: feat.Fold) -> pd.DataFrame:
    """SARIMA(1,0,1)(1,0,0,12) per node, fitted on the training window.

    Test-period forecasts are one step ahead: the fitted parameters are
    kept fixed and the filter is simply run forward over the new months, so
    ARIMA sees exactly the same history as the neural models.
    """
    train_end = pd.Period(fold.train_end, freq="M")
    val_end = pd.Period(fold.val_end, freq="M")
    test_end = pd.Period(fold.test_end, freq="M")
    rows = []
    for node_id, f in frames.items():
        y = f["y"].to_numpy()
        per = f["period"]
        train_n = int((per <= train_end).sum())
        mask = ((per > val_end) & (per <= test_end)).to_numpy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                res = SARIMAX(y[:train_n], order=(1, 0, 1), seasonal_order=(1, 0, 0, 12),
                              trend="c").fit(disp=False, maxiter=200)
                full = res.apply(y[:int((per <= test_end).sum())])
                pred = full.get_prediction(dynamic=False)
                mean, var = pred.predicted_mean, pred.var_pred_mean
            except Exception:
                mean = np.full(len(y), np.nan)
                var = np.full(len(y), np.nan)
        for t in np.where(mask)[0]:
            rows.append({"node_id": node_id, "period": str(per.iloc[t]),
                         "arima": mean[t], "arima_var": var[t]})
    return pd.DataFrame(rows)
