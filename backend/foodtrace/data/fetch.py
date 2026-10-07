"""Download the three public datasets into data/raw.

    python -m foodtrace.data.fetch            # everything
    python -m foodtrace.data.fetch fda nors   # just some

Downloads are skipped when the file is already there; pass --force to
refresh. Nothing here edits the data - files are stored exactly as the
agencies serve them so the processing step can always be re-run.
"""
import argparse
import io
import json
import time
import zipfile

import requests

from ..config import COMTRADE_API_KEY, RAW_DIR, SERIES_END, SERIES_START
from .commodities import COMMODITIES

FDA_BULK = "https://download.open.fda.gov/food/enforcement/food-enforcement-0001-of-0001.json.zip"
NORS_CSV = "https://data.cdc.gov/api/views/5xkq-dg7x/rows.csv?accessType=DOWNLOAD"
COMTRADE_PREVIEW = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
COMTRADE_DATA = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
COMTRADE_PARTNERS = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
US_REPORTER = 842

session = requests.Session()
session.headers["User-Agent"] = "harshancapstone-foodtrace/1.0 (university project)"


def _get(url, tries=12, **kw):
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=120, **kw)
            if r.status_code == 429 or (r.status_code == 403 and "quota" in r.text.lower()):
                # Rate limited or short-term quota hit: back off harder than
                # for a network blip. The public quota recovers within minutes.
                wait = int(r.headers.get("Retry-After") or 0) or 30 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"  retrying in {wait}s ({exc})", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url} after {tries} tries")


def fetch_fda(force=False):
    out = RAW_DIR / "fda_food_enforcement.json"
    if out.exists() and not force:
        print(f"fda: already have {out.name}")
        return
    print("fda: downloading openFDA food enforcement bulk file")
    r = _get(FDA_BULK)
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        name = zf.namelist()[0]
        out.write_bytes(zf.read(name))
    n = len(json.loads(out.read_text(encoding="utf-8"))["results"])
    print(f"fda: saved {n} recall records")


def fetch_nors(force=False):
    out = RAW_DIR / "cdc_nors_outbreaks.csv"
    if out.exists() and not force:
        print(f"nors: already have {out.name}")
        return
    print("nors: downloading CDC NORS outbreak table")
    r = _get(NORS_CSV)
    out.write_bytes(r.content)
    print(f"nors: saved {r.content.count(b'\n') - 1} outbreak rows")


def _months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_comtrade(force=False, end=None):
    """US monthly imports by HS6 code and partner country (UN Comtrade).

    The public preview endpoint needs no key but serves one month per call,
    at most 500 rows, and has an hourly quota - when it is used up the API
    says how long to wait and we sleep. Each month is saved as its own file,
    so re-running only fetches the months still missing.
    """
    folder = RAW_DIR / "comtrade_us_imports"
    folder.mkdir(exist_ok=True)
    ref = RAW_DIR / "comtrade_partners.json"
    if not ref.exists() or force:
        ref.write_bytes(_get(COMTRADE_PARTNERS).content)

    end = end or SERIES_END
    codes = sorted({code for c in COMMODITIES for code in c.hs_codes})
    if COMTRADE_API_KEY:
        _fetch_comtrade_keyed(folder, codes, end, force)
        return
    for period in _months(SERIES_START, end):
        out = folder / f"{period}.json"
        if out.exists() and not force:
            continue
        # One request per month: all codes together come to roughly 350
        # rows, under the 500-row cap (larger months are split automatically).
        rows = _comtrade_month(period, codes)
        out.write_text(json.dumps(rows), encoding="utf-8")
        print(f"comtrade: {period} -> {len(rows)} rows", flush=True)


def _fetch_comtrade_keyed(folder, codes, end, force):
    """Same data through the subscription endpoint (free key from
    comtradedeveloper.un.org). It accepts up to 12 periods and returns up to
    100k rows per call, so a whole year comes back in one request."""
    missing = [p for p in _months(SERIES_START, end) if force or not (folder / f"{p}.json").exists()]
    headers = {"Ocp-Apim-Subscription-Key": COMTRADE_API_KEY}
    for i in range(0, len(missing), 12):
        batch = missing[i:i + 12]
        params = {"reporterCode": US_REPORTER, "flowCode": "M",
                  "cmdCode": ",".join(codes), "period": ",".join(batch)}
        payload = _get(COMTRADE_DATA, params=params, headers=headers).json()
        if payload.get("error"):
            raise RuntimeError(f"comtrade: {payload['error']}")
        by_period = {p: [] for p in batch}
        for row in payload.get("data") or []:
            by_period.setdefault(str(row["period"]), []).append(row)
        for p in batch:
            if not by_period[p]:
                print(f"comtrade: {p} came back empty, leaving it for the next run")
                continue
            (folder / f"{p}.json").write_text(json.dumps(by_period[p]), encoding="utf-8")
            print(f"comtrade: {p} -> {len(by_period[p])} rows", flush=True)
        time.sleep(1.0)


def _comtrade_month(period, codes):
    params = {"reporterCode": US_REPORTER, "flowCode": "M",
              "cmdCode": ",".join(codes), "period": period}
    for attempt in range(6):
        payload = _get(COMTRADE_PREVIEW, params=params).json()
        data = payload.get("data") or []
        if data or attempt == 5:
            break
        # An empty answer usually means the endpoint is throttling us.
        time.sleep(3 + 3 * attempt)
    time.sleep(1.0)
    if payload.get("count", 0) >= 500 and len(codes) > 1:
        # Preview responses are capped at 500 rows; split and ask again.
        mid = len(codes) // 2
        return _comtrade_month(period, codes[:mid]) + _comtrade_month(period, codes[mid:])
    return data


SOURCES = {"fda": fetch_fda, "nors": fetch_nors, "comtrade": fetch_comtrade}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sources", nargs="*", default=list(SOURCES), choices=list(SOURCES))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    for name in args.sources:
        SOURCES[name](force=args.force)


if __name__ == "__main__":
    main()
