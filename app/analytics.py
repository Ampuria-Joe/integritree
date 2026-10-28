"""Performance analysis on clean_records. All yields are area-weighted (sum kg / sum ha)."""
import numpy as np
import pandas as pd

from app.db import read_df
from pipeline.dqc import RULES, SUSPECT_RATE


def _f(x, d=1):
    return None if x is None or pd.isna(x) else round(float(x), d)


def weighted(df, by):
    g = df.groupby(by).agg(kg=("yield_kg", "sum"), ha=("area_ha", "sum"),
                           margin=("gross_margin", "sum"), n=("instance_id", "count"))
    g["kg_ha"], g["margin_ha"] = g.kg / g.ha, g.margin / g.ha
    return g


def index_by(df, key):
    """Performance index: yield vs the crop's own average (100 = average), area-weighted.
    Needed because maize and potato yields are not comparable in kg/ha."""
    base = weighted(df, "crop")["kg_ha"]
    t = weighted(df, [key, "crop"]).reset_index()
    t["idx"] = t.kg_ha / t.crop.map(base) * 100
    t["w"] = t.idx * t.ha
    s = t.groupby(key)
    return s.w.sum() / s.ha.sum()


def kpis(df):
    if df.empty:
        return {"records": 0}
    return {"records": len(df), "area_ha": _f(df.area_ha.sum(), 0),
            "yield_kg_ha": _f(df.yield_kg.sum() / df.area_ha.sum(), 0),
            "margin_ha": _f(df.gross_margin.sum() / df.area_ha.sum(), 0),
            "flagged_pct": _f(df.has_warning.mean() * 100, 1)}


def trend(df):
    if df.empty:
        return {"seasons": [], "series": {}, "index": []}
    seasons = sorted(df.season.unique())
    t = weighted(df, ["crop", "season"]).kg_ha.unstack("season").reindex(columns=seasons)
    idx = index_by(df, "season").reindex(seasons)
    return {"seasons": seasons, "index": [_f(v) for v in idx],
            "series": {c: [_f(v, 0) for v in row] for c, row in t.iterrows()}}


def regions(df):
    if df.empty:
        return {"labels": []}
    idx = index_by(df, "region").sort_values()
    kg = weighted(df, "region").kg_ha.reindex(idx.index)
    return {"labels": list(idx.index), "index": [_f(v) for v in idx], "kg_ha": [_f(v, 0) for v in kg]}


def margins(df):
    if df.empty:
        return {"labels": []}
    m = weighted(df, "crop").sort_values("margin_ha")
    return {"labels": list(m.index), "margin_ha": [_f(v, 0) for v in m.margin_ha]}


def input_response(df):
    d = df.dropna(subset=["fertilizer_kg_ha", "yield_kg_ha"])
    if len(d) < 10:
        return {"points": [], "fit": None}
    d = d.assign(y_idx=d.yield_kg_ha / d.groupby("crop").yield_kg_ha.transform("mean") * 100)
    slope, icpt = np.polyfit(d.fertilizer_kg_ha, d.y_idx, 1)
    s = d.sample(min(len(d), 400), random_state=1)
    return {"points": [{"x": _f(a), "y_idx": _f(b), "y_kg_ha": _f(c, 0)}
                       for a, b, c in zip(s.fertilizer_kg_ha, s.y_idx, s.yield_kg_ha)],
            "fit": {"slope_idx": float(slope), "intercept_idx": float(icpt),
                    "r": _f(d.fertilizer_kg_ha.corr(d.y_idx), 2), "n": len(d)}}


def insights(df):
    if len(df) < 20:
        return ["Not enough clean records for the current filter to draw conclusions."]
    out, s = [], index_by(df, "season")
    if len(s) > 1:
        out.append(f"{s.idxmin()} was the weakest season at {s.min():.0f}% of each crop's average yield; "
                   f"{s.idxmax()} was the strongest at {s.max():.0f}%.")
    w = weighted(df[df.has_warning == 0], ["crop", "season"])  # unflagged plots only: one tripled yield can fake a trend
    t = w.kg_ha.where(w.n >= 15).unstack("season")  # ignore thin cells: tiny samples give noisy swings
    if t.shape[1] > 1:
        last, prev = t.columns[-1], t.columns[-2]
        ch = ((t[last] / t[prev] - 1) * 100).dropna().sort_values()
        if len(ch):
            out.append(f"Compared with {prev} (unflagged plots only), {ch.index[-1]} yields moved {ch.iloc[-1]:+.0f}% in {last}, "
                       f"and {ch.index[0]} moved {ch.iloc[0]:+.0f}%.")
    r = index_by(df, "region")
    if len(r) > 1:
        out.append(f"{r.idxmax()} leads on yield ({r.max():.0f}% of crop average); {r.idxmin()} trails "
                   f"({r.min():.0f}%), a {r.max() - r.min():.0f}-point gap.")
    fit = input_response(df)["fit"]
    if fit:
        out.append(f"Each extra 10 kg/ha of fertiliser goes with about {fit['slope_idx'] * 10:+.1f} index points of yield "
                   f"(r = {fit['r']}, n = {fit['n']}). This is an association, not proof that fertiliser caused it.")
    neg = df.groupby("crop").gross_margin.apply(lambda x: (x < 0).mean() * 100).sort_values()
    out.append(f"{(df.gross_margin < 0).mean() * 100:.0f}% of plots made a negative gross margin; "
               f"{neg.index[-1]} is the most exposed at {neg.iloc[-1]:.0f}%.")
    return out


def dq_from(total, loaded, flagged, hits):
    """hits: Series rule -> number of records the rule fired on."""
    rules = []
    for rid, (gate, sev, desc) in RULES.items():
        recs = int(hits.get(rid, 0))
        rate = recs / total if total else 0
        rules.append({"rule": rid, "gate": gate, "severity": sev, "description": desc,
                      "records": recs, "rate": round(rate * 100, 1), "suspect": rate > SUSPECT_RATE})
    rules.sort(key=lambda r: (r["gate"], -r["records"]))
    return {"funnel": {"received": total, "loaded": loaded, "rejected": total - loaded, "flagged": flagged},
            "rules": rules}


def dq_summary(db):
    total = int(read_df(db, "SELECT COUNT(*) n FROM raw_submissions").n[0])
    loaded = int(read_df(db, "SELECT COUNT(*) n FROM clean_records").n[0])
    flagged = int(read_df(db, "SELECT COUNT(*) n FROM clean_records WHERE has_warning=1").n[0])
    hits = read_df(db, "SELECT rule, COUNT(DISTINCT instance_id) recs FROM dqc_issues GROUP BY rule").set_index("rule").recs
    return dq_from(total, loaded, flagged, hits)
