"""Turn the raw downloads into tidy tables.

Outputs (data/processed):
    imports.parquet    commodity x origin country x month US import quantity (kg)
    nodes.parquet      the supply nodes kept for modelling
    recalls.parquet    FDA recall records matched to a commodity
    outbreaks.parquet  CDC NORS foodborne outbreaks matched to a commodity

Matching is plain keyword matching, written out in commodities.py, so
anyone can check why a given recall landed on a given commodity.
"""
import json
import re

import numpy as np
import pandas as pd

from ..config import PROCESSED_DIR, RAW_DIR, SERIES_END, SERIES_START
from .commodities import COMMODITIES, FINISHED_FOOD

# A country must supply at least this share of a commodity's imports, and
# ship in most months, to become its own node. Smaller origins are too
# sparse to forecast monthly.
MIN_SHARE = 0.02
MIN_ACTIVE_MONTHS = 0.85
MAX_NODES_PER_COMMODITY = 6

# FDA product descriptions often end with a long ingredient list. Only the
# opening of the description names the product itself.
DESCRIPTION_HEAD = 160


def _period(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce").dt.to_period("M")


def _term_regex(terms):
    # Whole words only (plural allowed), so "clam" does not match "clamshell".
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")(?:s|es)?\b", re.I)


def _match_commodity(text: str) -> str | None:
    """Commodity a recalled product belongs to, or None.

    When the opening of the description names more than one commodity
    ("cinnamon peanut butter") the one mentioned last wins: product names
    put the food itself after its flavours and qualifiers.
    """
    head = text[:DESCRIPTION_HEAD].lower()
    best, best_pos = None, -1
    for c in COMMODITIES:
        hits = list(_term_regex(c.fda_terms).finditer(head))
        if not hits:
            continue
        if any(x in head for x in c.exclude):
            continue
        if not c.processed and any(x in head for x in FINISHED_FOOD):
            continue
        if hits[-1].start() > best_pos:
            best, best_pos = c.key, hits[-1].start()
    return best


# --- UN Comtrade imports ----------------------------------------------------

def load_imports() -> pd.DataFrame:
    folder = RAW_DIR / "comtrade_us_imports"
    files = sorted(folder.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"{folder} is empty - run `python -m foodtrace.data.fetch comtrade`")
    rows = [r for f in files for r in json.loads(f.read_text(encoding="utf-8"))]
    df = pd.DataFrame(rows)

    partners = json.loads((RAW_DIR / "comtrade_partners.json").read_text(encoding="utf-8"))["results"]
    names = {p["PartnerCode"]: p["PartnerDesc"] for p in partners if not p.get("isGroup")}

    # Keep plain country-to-US rows: no world total, no second partner,
    # all customs procedures and transport modes combined.
    df = df[(df["partnerCode"] != 0) & (df["partner2Code"] == 0) &
            (df["customsCode"] == "C00") & (df["motCode"] == 0)].copy()
    df = df[df["partnerCode"].isin(names)]
    df["country"] = df["partnerCode"].map(names)

    hs_to_key = {code: c.key for c in COMMODITIES for code in c.hs_codes}
    df["commodity"] = df["cmdCode"].astype(str).map(hs_to_key)
    df = df[df["commodity"].notna()]

    # Net weight is reported in kg. When it is missing but the quantity unit
    # is itself kg, the quantity is the same figure.
    kg = pd.to_numeric(df["netWgt"], errors="coerce")
    qty_is_kg = df["qtyUnitAbbr"].fillna("").str.lower().eq("kg")
    kg = kg.where(kg.notna() & (kg > 0), pd.to_numeric(df["qty"], errors="coerce").where(qty_is_kg))
    df["qty_kg"] = kg.fillna(0)
    df["value_usd"] = pd.to_numeric(df["primaryValue"], errors="coerce").fillna(0)
    df["period"] = pd.PeriodIndex(df["period"].astype(str), freq="M")
    df = df[(df["period"] >= pd.Period(SERIES_START, freq="M")) &
            (df["period"] <= pd.Period(SERIES_END, freq="M"))]

    out = (df.groupby(["commodity", "country", "period"], as_index=False)
             .agg(qty_kg=("qty_kg", "sum"), value_usd=("value_usd", "sum")))
    return out


def select_nodes(imports: pd.DataFrame) -> pd.DataFrame:
    periods = pd.period_range(SERIES_START, SERIES_END, freq="M")
    rows = []
    for key, g in imports.groupby("commodity"):
        total = g["qty_kg"].sum()
        by_country = g.groupby("country").agg(qty=("qty_kg", "sum"),
                                              active=("qty_kg", lambda s: (s > 0).sum()))
        by_country["share"] = by_country["qty"] / total
        by_country["active_frac"] = by_country["active"] / len(periods)
        keep = by_country[(by_country["share"] >= MIN_SHARE) &
                          (by_country["active_frac"] >= MIN_ACTIVE_MONTHS)]
        keep = keep.sort_values("qty", ascending=False).head(MAX_NODES_PER_COMMODITY)
        for country, r in keep.iterrows():
            rows.append({"commodity": key, "country": country,
                         "share": r["share"], "active_frac": r["active_frac"],
                         "total_kg": r["qty"]})
    nodes = pd.DataFrame(rows)
    partners = json.loads((RAW_DIR / "comtrade_partners.json").read_text(encoding="utf-8"))["results"]
    iso3 = {p["PartnerDesc"]: p["PartnerCodeIsoAlpha3"] for p in partners if not p.get("isGroup")}
    nodes["iso3"] = nodes["country"].map(iso3)
    # Comtrade reports Taiwan under partner 490 "Other Asia, nes"; give it
    # Taiwan's ISO code so the map can place it.
    nodes.loc[nodes["country"] == "Other Asia, nes", "iso3"] = "TWN"
    nodes["node_id"] = nodes["commodity"] + ":" + nodes["country"].str.lower().str.replace(r"[^a-z]+", "_", regex=True)
    return nodes


def node_panel(imports: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """Complete monthly grid for each node; months with no recorded imports are 0 kg."""
    periods = pd.period_range(SERIES_START, SERIES_END, freq="M")
    frames = []
    for n in nodes.itertuples():
        g = imports[(imports["commodity"] == n.commodity) & (imports["country"] == n.country)]
        s = g.set_index("period")["qty_kg"].reindex(periods, fill_value=0.0)
        frames.append(pd.DataFrame({"node_id": n.node_id, "commodity": n.commodity,
                                    "country": n.country, "period": periods, "qty_kg": s.values}))
    return pd.concat(frames, ignore_index=True)


# --- FDA recalls -----------------------------------------------------------

# The checks follow the Key Data Elements of the FDA Food Traceability Rule
# (FSMA section 204, 21 CFR Part 1 Subpart S): a traceability lot code,
# a date, the quantity with its unit, and where the food came from and went.
LOT_PATTERN = re.compile(r"\b(?:lot|batch|upc|sku|code|plu)\b|\b\d{6,}\b", re.I)
DATE_PATTERN = re.compile(r"\b(?:best\s*by|best\s*before|use\s*by|sell\s*by|exp\w*|pack(?:ed)?\s*(?:on|date)|"
                          r"harvest\w*|bb)\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", re.I)
QTY_PATTERN = re.compile(r"\d[\d,.]*\s*(?:lbs?|pounds?|kg|kilograms?|cases?|cartons?|units?|boxes|bags?|"
                         r"bottles?|jars?|cans?|containers?|packages?|pallets?|bins?|crates?|trays?|pieces?|oz)\b", re.I)
US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
             "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR").split()
STATE_NAMES = ("alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii "
               "idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan "
               "minnesota mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania "
               "tennessee texas utah vermont virginia washington wisconsin wyoming canada mexico").split()
PLACE_PATTERN = re.compile(r"\b(?:" + "|".join(US_STATES) + r")\b|\b(?:" + "|".join(STATE_NAMES) +
                           r"|new york|new jersey|new mexico|new hampshire|north carolina|south carolina|"
                           r"north dakota|south dakota|rhode island|west virginia|puerto rico)\b")


def traceability_checks(rec: dict) -> dict:
    """The five record-completeness checks that define a 'verified' record.

    lot          - code_info carries a lot, batch, UPC or similar identifier
    date         - code_info carries a pack / harvest / best-by style date
    quantity     - product_quantity gives a number with a unit
    distribution - distribution_pattern names specific states or countries
                   ("nationwide" alone does not say where the product went)
    origin       - the recalling firm has a full street address
    """
    code = (rec.get("code_info") or "") + " " + (rec.get("more_code_info") or "")
    dist = rec.get("distribution_pattern") or ""
    return {
        "chk_lot": bool(LOT_PATTERN.search(code)),
        "chk_date": bool(DATE_PATTERN.search(code)),
        "chk_quantity": bool(QTY_PATTERN.search(rec.get("product_quantity") or "")),
        "chk_distribution": bool(PLACE_PATTERN.search(dist) or PLACE_PATTERN.search(dist.lower())),
        "chk_origin": all((rec.get(k) or "").strip() for k in ("address_1", "city", "postal_code")),
    }


def load_recalls(countries: list[str]) -> pd.DataFrame:
    raw = json.loads((RAW_DIR / "fda_food_enforcement.json").read_text(encoding="utf-8"))["results"]
    country_re = {c: re.compile(r"\b" + re.escape(c) + r"\b", re.I) for c in countries}
    rows = []
    for rec in raw:
        desc = rec.get("product_description") or ""
        key = _match_commodity(desc)
        if not key:
            continue
        text = " ".join(rec.get(k) or "" for k in ("product_description", "code_info", "reason_for_recall"))
        mentioned = [c for c, rx in country_re.items() if rx.search(text)]
        firm_country = (rec.get("country") or "").strip().title()
        if firm_country and firm_country != "United States" and firm_country in country_re:
            mentioned.append(firm_country)
        checks = traceability_checks(rec)
        rows.append({
            "recall_number": rec.get("recall_number"),
            "event_id": rec.get("event_id"),
            "commodity": key,
            "origin_countries": sorted(set(mentioned)),
            "classification": rec.get("classification"),
            "status": rec.get("status"),
            "recalling_firm": rec.get("recalling_firm"),
            "firm_state": rec.get("state"),
            "firm_country": firm_country,
            "product_description": desc,
            "reason_for_recall": rec.get("reason_for_recall"),
            "distribution_pattern": rec.get("distribution_pattern"),
            "product_quantity": rec.get("product_quantity"),
            "code_info": rec.get("code_info"),
            "recall_initiation_date": rec.get("recall_initiation_date"),
            "report_date": rec.get("report_date"),
            **checks,
        })
    df = pd.DataFrame(rows)
    df["initiated"] = _period(df["recall_initiation_date"])
    df["reported"] = _period(df["report_date"])
    chk = [c for c in df.columns if c.startswith("chk_")]
    df["trace_score"] = df[chk].mean(axis=1)
    df["verified"] = df[chk].all(axis=1)
    return df


# --- CDC NORS outbreaks ----------------------------------------------------

def load_outbreaks() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "cdc_nors_outbreaks.csv", dtype=str)
    df = df[df["Primary Mode"] == "Food"].copy()
    text = (df["Food Vehicle"].fillna("") + " ; " + df["Food Contaminated Ingredient"].fillna("")).str.lower()
    df["commodity"] = None
    for c in COMMODITIES:
        rx = _term_regex(c.nors_terms)
        hit = text.str.contains(rx) & df["commodity"].isna()
        if c.exclude:
            hit &= ~text.str.contains("|".join(map(re.escape, c.exclude)))
        df.loc[hit, "commodity"] = c.key
    df = df[df["commodity"].notna()].copy()
    df["year"] = df["Year"].astype(int)
    df["month"] = pd.to_numeric(df["Month"], errors="coerce")
    df = df[df["month"].notna()]
    df["period"] = pd.PeriodIndex.from_fields(year=df["year"], month=df["month"].astype(int), freq="M")
    for col in ("Illnesses", "Hospitalizations", "Deaths"):
        df[col.lower()] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    keep = ["commodity", "period", "State", "Etiology", "Etiology Status", "Setting",
            "Food Vehicle", "Food Contaminated Ingredient", "IFSAC Category",
            "illnesses", "hospitalizations", "deaths"]
    out = df[keep].rename(columns=lambda c: c.lower().replace(" ", "_"))
    out = out.reset_index(drop=True)
    out["outbreak_id"] = "NORS-" + out["period"].astype(str) + "-" + out.index.astype(str).str.zfill(5)
    return out


def main():
    imports = load_imports()
    nodes = select_nodes(imports)
    panel = node_panel(imports, nodes)
    recalls = load_recalls(sorted(nodes["country"].unique()))
    outbreaks = load_outbreaks()

    for name, df in [("imports", imports), ("nodes", nodes), ("panel", panel),
                     ("recalls", recalls), ("outbreaks", outbreaks)]:
        df = df.copy()
        for col in df.columns:
            if isinstance(df[col].dtype, pd.PeriodDtype):
                df[col] = df[col].astype(str)
        df.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
        print(f"{name:10s} {len(df):7d} rows")

    # Random sample of matches for a manual precision check (fill in "correct").
    audit = recalls.sample(min(100, len(recalls)), random_state=7)[
        ["recall_number", "commodity", "product_description"]].assign(correct="")
    audit.to_csv(PROCESSED_DIR / "recall_match_audit.csv", index=False)

    print(f"\n{nodes['commodity'].nunique()} commodities, {len(nodes)} nodes, "
          f"{panel['period'].nunique()} months")
    print(f"recalls matched: {len(recalls)}  verified: {recalls['verified'].mean():.1%}")
    print(f"outbreaks matched: {len(outbreaks)}")


if __name__ == "__main__":
    main()
