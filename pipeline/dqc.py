"""Gate-based data quality control.

Gate 0 structure -> Gate 1 validity/reconciliation -> Gate 2 geospatial.
A record that fails a gate with an `error` is rejected and does not reach the next gate.
`warning` records are loaded but flagged. Every rule is registered in RULES so the
dashboard can show how often each check fires: a rule that flags a very large share of a
batch is more likely a defect in the check than in the data (see docs/SOP_dqc.md).
"""
import logging

import numpy as np
import pandas as pd

from . import geo

log = logging.getLogger("etl")
SUSPECT_RATE = 0.30

RULES = {
    "G0_NO_ID": ("G0", "error", "Submission has no instance ID"),
    "G0_DUPLICATE": ("G0", "warning", "Instance ID submitted more than once (latest kept)"),
    "G0_MISSING": ("G0", "error", "Required field missing or unparseable"),
    "G1_UNKNOWN_FARMER": ("G1", "error", "Farmer ID not in master list"),
    "G1_REGION_MISMATCH": ("G1", "warning", "Region differs from master list"),
    "G1_CROP_UNKNOWN": ("G1", "error", "Crop not in the approved crop list"),
    "G1_SEASON_FORMAT": ("G1", "error", "Season is not YYYY + A/B (e.g. 2024A)"),
    "G1_AREA_RANGE": ("G1", "error", "Declared area outside 0.05-50 ha"),
    "G1_YIELD_RANGE": ("G1", "error", "Yield per ha outside the plausible range for the crop"),
    "G1_DATE_ORDER": ("G1", "error", "Harvest date is not after planting date"),
    "G1_SEASON_WINDOW": ("G1", "warning", "Planting month outside the season's planting window"),
    "G1_DAYS_RANGE": ("G1", "warning", "Planting-to-harvest period outside 50-330 days"),
    "G1_FERT_HIGH": ("G1", "warning", "Fertiliser above 300 kg/ha"),
    "G1_PRICE_RANGE": ("G1", "warning", "Price far from the crop median (0.2x-5x)"),
    "G1_OUTLIER": ("G1", "warning", "Yield is a robust outlier within its crop and season"),
    "G1_DUP_PLOT": ("G1", "warning", "Same farmer, season, crop and planting date submitted twice"),
    "G2_POLY_MISSING": ("G2", "error", "Plot boundary missing or fewer than 3 distinct points"),
    "G2_POLY_INVALID": ("G2", "error", "Plot boundary is not a valid polygon (e.g. self-intersecting)"),
    "G2_OUT_OF_BOUNDS": ("G2", "error", "Plot lies outside Kenya's bounding box"),
    "G2_AREA_MISMATCH": ("G2", "warning", "Mapped area differs from declared area by more than 30%"),
    "G2_GPS_FAR": ("G2", "warning", "GPS point more than 300 m from the plot boundary"),
}
REQUIRED = ["farmer_id", "region", "season", "crop", "area_ha", "planting_date",
            "harvest_date", "yield_kg", "fertilizer_kg", "price_per_kg", "input_cost"]
YIELD_BOUNDS = {"maize": (200, 9000), "beans": (100, 3500), "sorghum": (100, 5000),
                "potato": (1000, 40000), "wheat": (300, 7000)}
WINDOWS = {"A": {2, 3, 4, 5}, "B": {8, 9, 10, 11}}


def _issue(iid, rule, detail):
    gate, sev, _ = RULES[rule]
    return {"instance_id": iid, "gate": gate, "rule": rule, "severity": sev, "detail": detail}


def _add(issues, df, mask, rule, fn):
    for _, r in df[mask.fillna(False)].iterrows():
        issues.append(_issue(r["instance_id"], rule, fn(r)))


def load_masters(path):
    try:
        return pd.read_csv(path, dtype=str)
    except (FileNotFoundError, TypeError):
        log.warning("Master list not found (%s): reconciliation rules skipped", path)
        return None


def gate0(df, masters):
    iss = []
    miss = df[REQUIRED].isna()
    _add(iss, df, miss.any(axis=1), "G0_MISSING",
         lambda r: "missing: " + ", ".join(c for c in REQUIRED if miss.loc[r.name, c]))
    return iss


def gate1(df, masters):
    iss = []
    if masters is not None:
        known = df.farmer_id.isin(masters.farmer_id)
        _add(iss, df, ~known, "G1_UNKNOWN_FARMER", lambda r: f"{r.farmer_id} not in master list")
        mreg = df.farmer_id.map(masters.set_index("farmer_id").region)
        _add(iss, df, known & (mreg != df.region), "G1_REGION_MISMATCH",
             lambda r: f"form: {r.region}; master: {mreg[r.name]}")
    _add(iss, df, ~df.crop.isin(YIELD_BOUNDS), "G1_CROP_UNKNOWN", lambda r: f"crop='{r.crop}'")
    _add(iss, df, ~df.season.str.fullmatch(r"\d{4}[AB]"), "G1_SEASON_FORMAT", lambda r: f"season='{r.season}'")
    _add(iss, df, ~df.area_ha.between(0.05, 50), "G1_AREA_RANGE", lambda r: f"area_ha={r.area_ha}")
    lo = df.crop.map(lambda c: YIELD_BOUNDS.get(c, (0, np.inf))[0])
    hi = df.crop.map(lambda c: YIELD_BOUNDS.get(c, (0, np.inf))[1])
    _add(iss, df, (df.yield_kg_ha < lo) | (df.yield_kg_ha > hi), "G1_YIELD_RANGE",
         lambda r: f"{r.crop} {r.yield_kg_ha:.0f} kg/ha")
    bad_order = df.harvest_date <= df.planting_date
    _add(iss, df, bad_order, "G1_DATE_ORDER", lambda r: f"{r.planting_date:%F} -> {r.harvest_date:%F}")
    month = df.planting_date.dt.month
    in_window = [m in WINDOWS.get(s[-1], set()) for m, s in zip(month, df.season.fillna("?"))]
    _add(iss, df, ~pd.Series(in_window, index=df.index) & ~bad_order, "G1_SEASON_WINDOW",
         lambda r: f"planted {r.planting_date:%b} for season {r.season}")
    _add(iss, df, ~bad_order & ~df.days_to_harvest.between(50, 330), "G1_DAYS_RANGE",
         lambda r: f"{r.days_to_harvest:.0f} days")
    _add(iss, df, df.fertilizer_kg_ha > 300, "G1_FERT_HIGH", lambda r: f"{r.fertilizer_kg_ha:.0f} kg/ha")
    med = df.groupby("crop").price_per_kg.transform("median")
    n = df.groupby("crop").price_per_kg.transform("count")
    _add(iss, df, (n >= 5) & ((df.price_per_kg < 0.2 * med) | (df.price_per_kg > 5 * med)),
         "G1_PRICE_RANGE", lambda r: f"price {r.price_per_kg} vs median")
    g = df.groupby(["crop", "season"]).yield_kg_ha
    m, cnt = g.transform("median"), g.transform("count")
    mad = (df.yield_kg_ha - m).abs().groupby([df.crop, df.season]).transform("median")
    z = 0.6745 * (df.yield_kg_ha - m) / mad.replace(0, np.nan)
    _add(iss, df, (cnt >= 8) & (z.abs() > 3.5), "G1_OUTLIER",
         lambda r: f"{r.crop} {r.season}: {r.yield_kg_ha:.0f} kg/ha, robust z={z[r.name]:.1f}")
    _add(iss, df, df.duplicated(["farmer_id", "season", "crop", "planting_date"], keep="first"),
         "G1_DUP_PLOT", lambda r: f"{r.farmer_id} {r.season} {r.crop}")
    return iss


def gate2(df, masters):
    iss = []
    for r in df.itertuples():
        p, pt, iid = r.poly, r.pt, r.instance_id
        if not geo.present(p):
            iss.append(_issue(iid, "G2_POLY_MISSING", "no usable plot_boundary"))
            continue
        if not p.is_valid:
            from shapely.validation import explain_validity
            iss.append(_issue(iid, "G2_POLY_INVALID", explain_validity(p)))
            continue
        c = p.centroid
        if not geo.in_bbox(c.x, c.y):
            iss.append(_issue(iid, "G2_OUT_OF_BOUNDS", f"centroid {c.y:.4f},{c.x:.4f}"))
            continue
        if r.area_ha > 0 and abs(r.polygon_area_ha - r.area_ha) / r.area_ha > 0.30:
            iss.append(_issue(iid, "G2_AREA_MISMATCH",
                              f"declared {r.area_ha:.2f} ha, mapped {r.polygon_area_ha:.2f} ha"))
        if geo.present(pt) and geo.distance_m(pt, p) > 300:
            iss.append(_issue(iid, "G2_GPS_FAR", f"{geo.distance_m(pt, p):.0f} m from plot"))
    return iss


def run_gates(df, masters=None):
    """Returns (records that passed all gates, list of issue dicts)."""
    issues = []
    df = df.reset_index(drop=True)
    for _ in df.index[df.instance_id.isna()]:
        issues.append(_issue(None, "G0_NO_ID", "row without instance ID"))
    df = df[df.instance_id.notna()]
    counts = df.instance_id.value_counts()
    for iid, n in counts[counts > 1].items():
        issues.append(_issue(iid, "G0_DUPLICATE", f"{n} copies; latest kept"))
    alive = df.sort_values("submitted_at").drop_duplicates("instance_id", keep="last")
    for fn in (gate0, gate1, gate2):
        alive = alive.reset_index(drop=True)
        new = fn(alive, masters)
        issues += new
        bad = {i["instance_id"] for i in new if i["severity"] == "error"}
        log.info("%s: %d issues, %d rejected", fn.__name__, len(new), len(bad))
        alive = alive[~alive.instance_id.isin(bad)]
    return alive.reset_index(drop=True), issues
