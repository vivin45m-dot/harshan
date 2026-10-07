"""SQLite persistence for the provenance chain.

    python -m foodtrace.ledger.store build     # (re)build from processed data
    python -m foodtrace.ledger.store verify

Records come only from the processed public datasets: each monthly import
figure, each matched FDA recall and each matched CDC outbreak becomes one
ledger record in the block for its month.
"""
import json
import sqlite3
import sys
import time

import pandas as pd

from ..config import LEDGER_DB, POW_DIFFICULTY, PROCESSED_DIR
from . import chain

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    idx INTEGER PRIMARY KEY,
    period TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    merkle TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    nonce INTEGER NOT NULL,
    hash TEXT NOT NULL,
    mined_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    block_idx INTEGER NOT NULL REFERENCES blocks(idx),
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,
    commodity TEXT NOT NULL,
    node_id TEXT,
    period TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    verified INTEGER,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_block ON records(block_idx);
CREATE INDEX IF NOT EXISTS records_node ON records(node_id);
CREATE INDEX IF NOT EXISTS records_ref ON records(source_ref);
"""


def connect(path=LEDGER_DB):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _ledger_record(kind, commodity, node_id, period, source_ref, verified, payload):
    # This dict is exactly what gets hashed, so field order and types must
    # be reproducible from what is stored in the table.
    return {
        "kind": kind,
        "commodity": commodity,
        "node_id": node_id,
        "period": period,
        "source_ref": source_ref,
        "verified": verified,
        "payload": payload,
    }


def collect_records() -> dict[str, list[dict]]:
    panel = pd.read_parquet(PROCESSED_DIR / "panel.parquet")
    recalls = pd.read_parquet(PROCESSED_DIR / "recalls.parquet")
    outbreaks = pd.read_parquet(PROCESSED_DIR / "outbreaks.parquet")
    nodes = pd.read_parquet(PROCESSED_DIR / "nodes.parquet")
    node_lookup = {(r.commodity, r.country): r.node_id for r in nodes.itertuples()}
    first, last = panel["period"].min(), panel["period"].max()

    by_period: dict[str, list[dict]] = {}

    for r in panel.itertuples():
        by_period.setdefault(r.period, []).append(_ledger_record(
            "shipment", r.commodity, r.node_id, r.period,
            f"COMTRADE/{r.node_id}/{r.period}", None,
            {"qty_kg": float(r.qty_kg), "origin": r.country, "source": "UN Comtrade, US imports by HS6"}))

    for r in recalls.itertuples():
        period = r.reported
        if not isinstance(period, str) or not (first <= period <= last):
            continue
        origins = list(r.origin_countries)
        node_ids = [node_lookup[(r.commodity, c)] for c in origins if (r.commodity, c) in node_lookup]
        by_period.setdefault(period, []).append(_ledger_record(
            "recall", r.commodity, node_ids[0] if len(node_ids) == 1 else None, period,
            r.recall_number, bool(r.verified),
            {"event_id": r.event_id, "classification": r.classification,
             "firm": r.recalling_firm, "firm_state": r.firm_state,
             "product": r.product_description, "reason": r.reason_for_recall,
             "distribution": r.distribution_pattern, "quantity": r.product_quantity,
             "code_info": r.code_info, "initiated": r.recall_initiation_date,
             "reported": r.report_date, "origins": origins, "node_ids": node_ids,
             "checks": {"lot": bool(r.chk_lot), "quantity": bool(r.chk_quantity),
                        "distribution": bool(r.chk_distribution), "origin": bool(r.chk_origin)}}))

    for r in outbreaks.itertuples():
        if not (first <= r.period <= last):
            continue
        by_period.setdefault(r.period, []).append(_ledger_record(
            "outbreak", r.commodity, None, r.period, r.outbreak_id, None,
            {"state": r.state, "etiology": r.etiology, "status": r.etiology_status,
             "setting": r.setting, "food_vehicle": r.food_vehicle,
             "ingredient": r.food_contaminated_ingredient, "ifsac": r.ifsac_category,
             "illnesses": int(r.illnesses), "hospitalizations": int(r.hospitalizations),
             "deaths": int(r.deaths)}))
    return dict(sorted(by_period.items()))


def build(difficulty=POW_DIFFICULTY):
    if LEDGER_DB.exists():
        LEDGER_DB.unlink()
    con = connect()
    prev = chain.GENESIS_PREV
    t0 = time.time()
    total = 0
    for idx, (period, records) in enumerate(collect_records().items()):
        block = chain.build_block(idx, period, prev, records, difficulty)
        con.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?)",
                    (block.index, block.period, block.prev_hash, block.merkle,
                     block.record_count, block.nonce, block.hash, time.time()))
        con.executemany(
            "INSERT INTO records (block_idx, position, kind, commodity, node_id, period, source_ref, verified, payload)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(idx, pos, r["kind"], r["commodity"], r["node_id"], r["period"], r["source_ref"],
              None if r["verified"] is None else int(r["verified"]), chain.canonical(r["payload"]))
             for pos, r in enumerate(records)])
        prev = block.hash
        total += len(records)
    con.commit()
    print(f"ledger: {idx + 1} blocks, {total} records, mined in {time.time() - t0:.1f}s")
    return con


def row_to_record(row) -> dict:
    v = row["verified"]
    return _ledger_record(row["kind"], row["commodity"], row["node_id"], row["period"],
                          row["source_ref"], None if v is None else bool(v), json.loads(row["payload"]))


def load_blocks(con) -> list[chain.Block]:
    blocks = []
    recs: dict[int, list] = {}
    for row in con.execute("SELECT * FROM records ORDER BY block_idx, position"):
        recs.setdefault(row["block_idx"], []).append(row_to_record(row))
    for b in con.execute("SELECT * FROM blocks ORDER BY idx"):
        blocks.append(chain.Block(b["idx"], b["period"], b["prev_hash"], b["merkle"],
                                  b["record_count"], b["nonce"], b["hash"], recs.get(b["idx"], [])))
    return blocks


def verify_all(con, difficulty=POW_DIFFICULTY):
    return chain.verify(load_blocks(con), difficulty)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "build":
        con = build()
    else:
        con = connect()
    problems = verify_all(con)
    print("chain valid" if not problems else f"{len(problems)} problems: {problems[:3]}")
