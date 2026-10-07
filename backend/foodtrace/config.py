"""Paths and settings shared across the pipeline.

Everything lives under the project root so the folder can be copied to
another machine and run as-is.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"
LEDGER_DB = DATA_DIR / "ledger.sqlite3"

for _d in (RAW_DIR, PROCESSED_DIR, ARTIFACTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _env_file():
    # Optional .env in the project root, e.g. COMTRADE_API_KEY=...
    path = ROOT / ".env"
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and not key.strip().startswith("#"):
                values[key.strip()] = val.strip().strip('"')
    return values


# A free Comtrade key makes the import download take minutes instead of
# hours; without one the keyless preview endpoint is used.
COMTRADE_API_KEY = os.environ.get("COMTRADE_API_KEY") or _env_file().get("COMTRADE_API_KEY", "")

# Monthly import series window. UN Comtrade's US monthly HS6 records carry
# net weight from January 2016 (earlier months have values only), and July
# 2026 was the latest month published when the data was pulled.
SERIES_START = "2016-01"
SERIES_END = "2026-07"

# Proof-of-work difficulty for the provenance ledger (leading hex zeros).
# 3 keeps a full rebuild under a minute on a laptop while still making
# tampering visible and expensive to paper over.
POW_DIFFICULTY = 3
