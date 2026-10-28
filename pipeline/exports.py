"""Splits a processed batch into the three downloadable sets: passed, flagged, rejected."""
import pandas as pd

FMT = "%Y-%m-%dT%H:%M:%S"
OUT_COLS = ["instance_id", "submitted_at", "farmer_id", "region", "season", "crop", "area_ha",
            "polygon_area_ha", "planting_date", "harvest_date", "days_to_harvest", "yield_kg",
            "yield_kg_ha", "fertilizer_kg_ha", "input_cost", "price_per_kg", "revenue",
            "gross_margin", "lat", "lon", "has_warning"]


def build_exports(raw, clean, issues, rejected):
    iss = pd.DataFrame(issues, columns=["instance_id", "gate", "rule", "severity", "detail"])
    reasons = (iss.dropna(subset=["instance_id"]).assign(r=lambda d: d.rule + " (" + d.detail + ")")
               .groupby("instance_id").r.agg("; ".join))
    warned = set(iss[iss.severity == "warning"].instance_id.dropna())
    accepted = clean.drop(columns=["poly", "pt"], errors="ignore").copy()
    accepted["has_warning"] = accepted.instance_id.isin(warned).astype(int)
    out = accepted.copy()
    out["submitted_at"] = out.submitted_at.dt.strftime(FMT)
    for c in ("planting_date", "harvest_date"):
        out[c] = out[c].dt.strftime("%Y-%m-%d")
    out["reasons"] = out.instance_id.map(reasons).fillna("")
    rj = pd.concat([raw[raw.instance_id.isin(rejected)].drop_duplicates("instance_id", keep="last"),
                    raw[raw.instance_id.isna()]])
    rj = rj.assign(reasons=rj.instance_id.map(reasons).fillna("G0_NO_ID (row without instance ID)"))
    return {"accepted": accepted,
            "passed": out[out.has_warning == 0][OUT_COLS],
            "flagged": out[out.has_warning == 1][OUT_COLS + ["reasons"]],
            "rejected": rj.reset_index(drop=True)}
