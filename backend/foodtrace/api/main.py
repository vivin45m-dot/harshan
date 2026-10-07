"""HTTP API for the dashboard.

    uvicorn foodtrace.api.main:app --port 8000

All responses are plain JSON built from the processed public datasets, the
trained model and the ledger database.
"""
import json
import math
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import ARTIFACTS_DIR, LEDGER_DB, POW_DIFFICULTY, ROOT
from ..data.commodities import BY_KEY
from ..ledger import store
from ..model.serve import get_forecaster

app = FastAPI(title="FoodTrace forecasting API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_ledger = None


def ledger():
    global _ledger
    if _ledger is None:
        if not LEDGER_DB.exists():
            raise HTTPException(503, "Ledger has not been built yet")
        _ledger = store.connect()
        _ledger.execute("""CREATE TABLE IF NOT EXISTS tamper_log (
            record_id INTEGER PRIMARY KEY, original_payload TEXT NOT NULL)""")
    return _ledger


def clean(obj):
    """Make pandas/numpy output JSON-safe (NaN -> None)."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def records(df: pd.DataFrame):
    return clean(json.loads(df.to_json(orient="records", date_format="iso")))


# --- overview --------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/overview")
def overview():
    fc = get_forecaster()
    h = fc.history()
    last = h["period"].max()
    latest = h[h["period"] == last]
    results_path = ARTIFACTS_DIR / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    con = ledger()
    blocks = con.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
    recs = con.execute("SELECT kind, COUNT(*) n FROM records GROUP BY kind").fetchall()
    return clean({
        "nodes": int(fc.nodes.shape[0]),
        "commodities": int(fc.nodes["commodity"].nunique()),
        "countries": int(fc.nodes["country"].nunique()),
        "first_month": str(fc.panel["period"].min()),
        "last_month": last,
        "status_counts": latest["status"].value_counts().to_dict(),
        "recalls": int(len(fc.recalls)),
        "recalls_verified_share": float(fc.recalls["verified"].mean()),
        "outbreaks": int(len(fc.outbreaks)),
        "ledger": {"blocks": blocks, "records": {r["kind"]: r["n"] for r in recs}},
        "split": {k: fc.meta[k] for k in ("train_end", "val_end", "test_end")},
        "headline": results.get("accuracy", {}).get("evidential"),
    })


# --- nodes -----------------------------------------------------------------

@app.get("/api/nodes")
def nodes(month: str | None = None):
    fc = get_forecaster()
    h = fc.history()
    month = month or h["period"].max()
    snap = h[h["period"] == month][["node_id", "forecast_kg", "actual_kg", "aleatoric", "epistemic", "status"]]
    if snap.empty:
        raise HTTPException(404, f"No forecasts for {month}")
    df = fc.nodes.merge(fc.ratios[["node_id", "verification_ratio", "n_records"]], on="node_id")
    df = df.merge(snap, on="node_id", how="left")
    df["label"] = df["commodity"].map(lambda k: BY_KEY[k].label)
    df["perishable"] = df["commodity"].map(lambda k: BY_KEY[k].perishable)
    return {"month": month, "epi_cut": fc.epi_cut, "alea_cut": fc.alea_cut, "nodes": records(df)}


@app.get("/api/commodities")
def commodities():
    fc = get_forecaster()
    node_counts = fc.nodes.groupby("commodity").size()
    rec = fc.recalls.groupby("commodity")["verified"].agg(["size", "mean"])
    out = []
    for key in sorted(node_counts.index, key=lambda k: BY_KEY[k].label):
        c = BY_KEY[key]
        out.append({"key": key, "label": c.label, "hs_codes": list(c.hs_codes),
                    "perishable": c.perishable, "nodes": int(node_counts[key]),
                    "recalls": int(rec["size"].get(key, 0)),
                    "verified_share": float(rec["mean"].get(key, float("nan")))})
    return clean(out)


@app.get("/api/months")
def months():
    fc = get_forecaster()
    return sorted(fc.history()["period"].unique().tolist())


@app.get("/api/nodes/{node_id}")
def node_detail(node_id: str):
    fc = get_forecaster()
    if node_id not in fc.frames:
        raise HTTPException(404, "Unknown node")
    n = fc.nodes.set_index("node_id").loc[node_id]
    ratio = fc.ratios.set_index("node_id").loc[node_id]
    hist = fc.history(node_id)[["period", "split", "actual_kg", "forecast_kg", "lo80_kg", "hi80_kg",
                                "lo95_kg", "hi95_kg", "aleatoric", "epistemic", "status"]]
    rec = fc.recalls[fc.recalls["commodity"] == n["commodity"]].copy()
    rec["names_this_origin"] = rec["origin_countries"].apply(lambda cs: n["country"] in list(cs))
    rec = rec.sort_values("initiated", ascending=False)
    ob = fc.outbreaks[fc.outbreaks["commodity"] == n["commodity"]]
    ob_month = (ob.groupby(ob["period"].astype(str))
                  .agg(outbreaks=("illnesses", "size"), illnesses=("illnesses", "sum"))
                  .reset_index().rename(columns={"period": "month"}))
    cols = ["recall_number", "classification", "recalling_firm", "product_description", "reason_for_recall",
            "distribution_pattern", "product_quantity", "code_info", "recall_initiation_date", "report_date",
            "chk_lot", "chk_date", "chk_quantity", "chk_distribution", "chk_origin", "verified",
            "names_this_origin", "status"]
    rec_out = rec[cols].copy()
    rec_out["initiated"] = rec["initiated"].astype(str)
    rec_out["reported"] = rec["reported"].astype(str)
    return clean({
        "node_id": node_id,
        "commodity": n["commodity"], "label": BY_KEY[n["commodity"]].label,
        "perishable": BY_KEY[n["commodity"]].perishable,
        "hs_codes": list(BY_KEY[n["commodity"]].hs_codes),
        "country": n["country"], "iso3": n["iso3"], "share": float(n["share"]),
        "verification": {"ratio": float(ratio["verification_ratio"]), "records": int(ratio["n_records"]),
                         "verified_records": int(ratio["n_verified"]),
                         "commodity_rate": float(ratio["commodity_rate"])},
        "next": fc.next_month(node_id),
        "history": records(hist),
        "recalls": records(rec_out.head(200)),
        "recall_count": int(len(rec)),
        "outbreaks_by_month": records(ob_month),
        "thresholds": {"epistemic": fc.epi_cut, "aleatoric": fc.alea_cut},
    })


# --- results ---------------------------------------------------------------

@app.get("/api/results")
def results():
    path = ARTIFACTS_DIR / "results.json"
    if not path.exists():
        raise HTTPException(503, "Run `python -m foodtrace.model.evaluate` first")
    out = json.loads(path.read_text())
    summary = ARTIFACTS_DIR / "node_summary.csv"
    if summary.exists():
        out["node_summary"] = records(pd.read_csv(summary))
    for scope in ("node", "commodity"):
        p = ARTIFACTS_DIR / f"lead_pairs_{scope}.csv"
        if p.exists():
            out.setdefault("lead_pairs", {})[scope] = records(pd.read_csv(p))
    return clean(out)


# --- ledger ----------------------------------------------------------------

@app.get("/api/ledger/blocks")
def ledger_blocks(offset: int = 0, limit: int = Query(50, le=500)):
    con = ledger()
    rows = con.execute("""
        SELECT b.idx, b.period, b.prev_hash, b.merkle, b.record_count, b.nonce, b.hash,
               SUM(r.kind='shipment') shipments, SUM(r.kind='recall') recalls, SUM(r.kind='outbreak') outbreaks
        FROM blocks b LEFT JOIN records r ON r.block_idx = b.idx
        GROUP BY b.idx ORDER BY b.idx DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
    total = con.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
    return {"total": total, "difficulty": POW_DIFFICULTY, "blocks": [dict(r) for r in rows]}


@app.get("/api/ledger/blocks/{idx}")
def ledger_block(idx: int, kind: str | None = None):
    con = ledger()
    b = con.execute("SELECT * FROM blocks WHERE idx=?", (idx,)).fetchone()
    if not b:
        raise HTTPException(404, "No such block")
    q = "SELECT * FROM records WHERE block_idx=?"
    args = [idx]
    if kind:
        q += " AND kind=?"
        args.append(kind)
    recs = []
    tampered = {r[0] for r in con.execute("SELECT record_id FROM tamper_log")}
    for r in con.execute(q + " ORDER BY position", args):
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        d["hash"] = store.chain.record_hash(store.row_to_record(r))
        d["tampered"] = r["id"] in tampered
        recs.append(d)
    return {"block": dict(b), "records": recs}


@app.get("/api/ledger/verify")
def ledger_verify():
    problems = store.verify_all(ledger())
    return {"valid": not problems, "problems": [p.__dict__ for p in problems]}


@app.get("/api/ledger/search")
def ledger_search(ref: str):
    con = ledger()
    rows = con.execute("SELECT id, block_idx, kind, commodity, node_id, period, source_ref, verified "
                       "FROM records WHERE source_ref LIKE ? LIMIT 50", (f"%{ref}%",)).fetchall()
    return [dict(r) for r in rows]


class Tamper(BaseModel):
    record_id: int
    field: str
    value: str | float | int | bool | None


@app.post("/api/ledger/tamper")
def ledger_tamper(t: Tamper):
    """Edit a stored record *without* re-mining, to show the chain catching it."""
    con = ledger()
    row = con.execute("SELECT payload FROM records WHERE id=?", (t.record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No such record")
    payload = json.loads(row["payload"])
    if t.field not in payload:
        raise HTTPException(400, f"Record has no field '{t.field}'")
    con.execute("INSERT OR IGNORE INTO tamper_log VALUES (?, ?)", (t.record_id, row["payload"]))
    payload[t.field] = t.value
    con.execute("UPDATE records SET payload=? WHERE id=?", (store.chain.canonical(payload), t.record_id))
    con.commit()
    return ledger_verify()


@app.post("/api/ledger/restore")
def ledger_restore():
    con = ledger()
    for rid, original in con.execute("SELECT record_id, original_payload FROM tamper_log").fetchall():
        con.execute("UPDATE records SET payload=? WHERE id=?", (original, rid))
    con.execute("DELETE FROM tamper_log")
    con.commit()
    return ledger_verify()


# --- built dashboard -------------------------------------------------------

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
