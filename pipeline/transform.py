"""Standardise raw ODK columns/values and derive performance indicators."""
import json
import re

import numpy as np
import pandas as pd

from . import geo

RENAME = {"key": "instance_id", "instanceid": "instance_id", "__id": "instance_id",
          "submissiondate": "submitted_at"}
CROP_MAP = {"maize": "maize", "corn": "maize", "beans": "beans", "bean": "beans",
            "common beans": "beans", "sorghum": "sorghum", "potato": "potato",
            "potatoes": "potato", "irish potato": "potato", "wheat": "wheat"}
NUMERIC = ["area_ha", "yield_kg", "fertilizer_kg", "input_cost", "price_per_kg"]


def normalise_columns(df):
    """Handles ODK CSV exports ('group-field') and OData ('group.field' / 'group/field')."""
    cols = {}
    for c in df.columns:
        k = re.split(r"[./]", c)[-1].lower()
        cols[c] = RENAME.get(k, k)
    return df.rename(columns=cols)


def parse_ts(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_convert(None)


def to_pairs(v):
    """geopoint/geoshape (ODK text or GeoJSON dict) -> [(lon, lat), ...] or None."""
    try:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("{"):
                v = json.loads(s)
            else:
                pts = []
                for part in s.split(";"):
                    f = part.split()
                    if len(f) >= 2:
                        pts.append((float(f[1]), float(f[0])))  # ODK order is lat lon alt acc
                return pts or None
        if isinstance(v, dict):
            c = v.get("coordinates")
            if c is None:
                return None
            if v.get("type") == "Point":
                return [(c[0], c[1])]
            if v.get("type") == "Polygon":
                c = c[0]
            return [(p[0], p[1]) for p in c]
    except (ValueError, TypeError, IndexError):
        return None
    return None


def standardise(df):
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
    df = df.replace("", np.nan)
    low = lambda f: (lambda v: f(v) if isinstance(v, str) else v)
    df["crop"] = df["crop"].map(low(lambda s: CROP_MAP.get(s.lower(), s.lower())))
    df["region"] = df["region"].map(low(str.title))
    df["season"] = df["season"].map(low(str.upper))
    df["farmer_id"] = df["farmer_id"].map(low(str.upper))
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("planting_date", "harvest_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["submitted_at"] = parse_ts(df["submitted_at"])
    return df


def _centre(poly, pt):
    if pt is not None and geo.present(pt):
        return pt
    if geo.present(poly) and poly.is_valid:
        return (poly.centroid.x, poly.centroid.y)
    return (np.nan, np.nan)


def derive(df):
    df = df.copy()
    ha = df["area_ha"].where(df["area_ha"] > 0)
    df["yield_kg_ha"] = df["yield_kg"] / ha
    df["fertilizer_kg_ha"] = df["fertilizer_kg"] / ha
    df["revenue"] = df["yield_kg"] * df["price_per_kg"]
    df["gross_margin"] = df["revenue"] - df["input_cost"]
    df["days_to_harvest"] = (df["harvest_date"] - df["planting_date"]).dt.days
    df["poly"] = [geo.to_poly(to_pairs(v)) for v in df["plot_boundary"]]
    df["pt"] = [(p[0] if p else None) for p in (to_pairs(v) for v in df["plot_gps"])]
    df["polygon_area_ha"] = [geo.area_ha(p) if geo.present(p) and p.is_valid else np.nan for p in df["poly"]]
    ll = [_centre(p, q) for p, q in zip(df["poly"], df["pt"])]
    df["lon"] = [a for a, _ in ll]
    df["lat"] = [b for _, b in ll]
    return df
