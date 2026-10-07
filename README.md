# FoodTrace: calibrated uncertainty for food import forecasting

A demand forecast that says how much it can be trusted.

FoodTrace forecasts monthly US imports of 24 food commodities from their main origin
countries, using a deep evidential regression network. Each forecast comes with two kinds
of uncertainty from a single forward pass:

- **aleatoric**: the series itself is noisy (normal volatility, so plan a buffer)
- **epistemic**: the model is outside what it has learned (don't trust the number)

Every import figure, FDA recall and CDC outbreak the model uses is stored in a SHA-256
proof-of-work ledger, so any edit to the underlying records is detectable. The project
then tests whether nodes with more complete traceability records get lower epistemic
uncertainty, and whether uncertainty rises in the months before a recall.

All data is real and public:

| Source | What | Used for |
|---|---|---|
| [UN Comtrade](https://comtradeapi.un.org) | US monthly imports by HS6 code × origin, kg, 2016-01 → 2026-07 | demand series |
| [openFDA food enforcement](https://open.fda.gov/apis/food/enforcement/) | 29k FDA recall records | model inputs (by publication date), traceability scores, evaluation events |
| [CDC NORS](https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/NORS/5xkq-dg7x) | foodborne outbreaks with the implicated food | ledger and node context |

## Quick start (Windows)

Requires Node.js 20+ for the dashboard. Everything else (Python 3.12, PyTorch and all
packages) is installed **inside this folder** by the setup script; nothing goes to C:.

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1     # once, ~5-15 min
powershell -ExecutionPolicy Bypass -File run.ps1       # opens http://127.0.0.1:8000
```

On a machine without an NVIDIA GPU, setup installs the CPU build of PyTorch
automatically (or pass `-Cpu`). The trained model and processed data are already in the
repository, so `run.ps1` works without re-downloading anything.

To rebuild everything from the public sources:

```powershell
powershell -ExecutionPolicy Bypass -File pipeline.ps1                 # download, process, train, evaluate
powershell -ExecutionPolicy Bypass -File pipeline.ps1 -SkipDownload   # reuse data\raw
```

The Comtrade download needs no API key but is rate-limited, so a full download takes a
few hours. It resumes where it stopped.

## Layout

```
backend/foodtrace/
  config.py            paths and settings
  data/
    commodities.py     the 24 commodities: HS codes and matching terms
    fetch.py           downloads from Comtrade, openFDA, CDC
    process.py         cleaning, node selection, recall/outbreak matching, FSMA 204 checks
  ledger/
    chain.py           blocks, Merkle roots, proof of work, verification
    store.py           SQLite storage; builds the chain from processed data
  model/
    features.py        24-month input windows, verification ratio, train/val/test folds
    nets.py            GRU encoder; evidential, Gaussian (MC-dropout) and point heads; losses
    baselines.py       naive, seasonal naive, SARIMA
    train.py           training with early stopping, lambda selection by calibration
    evaluate.py        accuracy, calibration, hypothesis tests -> artifacts/results.json
    serve.py           loads the model for the API
  api/main.py          FastAPI endpoints (also serves the built dashboard)
backend/tests/         pytest suite
frontend/              React 19 + Vite + Leaflet + Recharts dashboard
artifacts/             trained weights, predictions, results.json
data/processed/        cleaned tables (parquet)
```

## The model in one paragraph

For each node and month, a two-layer GRU reads the previous 24 months (standardised log
imports, calendar month, and counts of FDA recalls already *published* for that
commodity). Static inputs (the node's verification ratio, perishability and typical
volume) join after the GRU. The head outputs (γ, ν, α, β) of a Normal-Inverse-Gamma
distribution; the forecast is γ, aleatoric uncertainty is β/(α−1), and epistemic
uncertainty is β/(ν(α−1)). Training minimises the NIG negative log-likelihood plus
λ·|y−γ|·(2ν+α), with λ chosen on the validation year by interval calibration. There is no
node-ID embedding, so the model can't simply memorise each node, which keeps epistemic
uncertainty meaningful.

## What "verified" means

There is no public record of which food shipments went through a blockchain. Instead, each
real FDA recall record is checked against the Key Data Elements of the FDA Food
Traceability Rule (FSMA §204): lot code, date, quantity with unit, named distribution
locations, and a full firm address. A record passing all five is *verified*. A node's
verification ratio is the verified share of its recall records (using only recalls
published before the training cut-off), shrunk toward the commodity rate when it has
few records.

## Evaluation

Rolling-origin, split by time:

| Fold | Train targets | Validation | Test |
|---|---|---|---|
| 2021-22 | 2018-01 → 2019-12 | 2020 | 2021-01 → 2022-12 |
| 2023-26 (main) | 2018-01 → 2021-12 | 2022 | 2023-01 → 2026-07 |

Baselines: naive, seasonal naive, SARIMA(1,0,1)(1,0,0)₁₂, the same GRU with a point head,
and MC-dropout (50 passes). Metrics: MAE, RMSE, MAPE, MASE, NLL, interval coverage
(PICP) and width at 50/80/90/95%. Hypothesis tests: Mann-Whitney U and OLS with HC3
errors (verification vs epistemic), and Wilcoxon signed-rank (pre-recall vs quiet months).

## Results (main fold, test period 2023-01 → 2026-07)

73 supply nodes (23 commodities × 30 origin countries), 127 months, 3,139 test forecasts.
2,660 FDA recalls matched to a commodity, 13.5% of them passing all five traceability checks.

| Model | MASE | WAPE | NLL | 90% interval coverage |
|---|---|---|---|---|
| **Evidential GRU** | **0.773** | 15.9% | **1.129** | **91.8%** |
| SARIMA | 0.794 | 15.8% | 1.813 | 83.5% |
| MC-dropout GRU | 0.868 | 16.9% | 1.630 | 87.6% |
| Naive | 0.920 | 21.3% | | |
| Seasonal naive | 1.000 | 21.0% | | |
| GRU, point only | 1.024 | 22.4% | | |

- **Calibration** is where the evidential model clearly wins: its intervals hold close to their
  nominal coverage (51 / 81 / 92 / 96% at 50 / 80 / 90 / 95%), while MC-dropout and SARIMA are
  too narrow at the upper levels.
- **Traceability vs epistemic uncertainty: not supported.** Verified and unverified nodes have
  similar epistemic uncertainty (median 2.41 vs 2.57, Mann-Whitney p = 0.48), and the
  regression with controls finds no effect either.
- **Uncertainty before recalls: partly supported.** Over 245 commodity-level recall events,
  the evidential model's epistemic uncertainty in the 3 months before a recall was higher than in
  the same node's quiet months in 57% of cases (Wilcoxon p = 0.010); MC-dropout showed no such
  rise (p = 0.18). This result moved when the recall-matching rules were tightened, so it should
  be read as suggestive, not settled. Too few recalls name an origin country (5) to test it per node.

Every number here is produced by `foodtrace.model.evaluate` and saved in `artifacts/results.json`.
`data/processed/recall_match_audit.csv` holds 100 random recall matches for a manual precision check.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```
