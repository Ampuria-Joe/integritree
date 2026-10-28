"""Extract step: ODK Central OData API (incremental) or a local ODK CSV export."""
import logging
import os

import pandas as pd
import requests

from . import transform

log = logging.getLogger("etl")
CONTRACT = ["instance_id", "submitted_at", "farmer_id", "region", "season", "crop", "area_ha",
            "planting_date", "harvest_date", "yield_kg", "fertilizer_kg", "input_cost",
            "price_per_kg", "plot_boundary", "plot_gps"]


def fetch_central(since=None):
    base, pid, form = os.environ["ODK_URL"].rstrip("/"), os.environ["ODK_PROJECT_ID"], os.environ["ODK_FORM_ID"]
    s = requests.Session()
    s.auth = (os.environ["ODK_EMAIL"], os.environ["ODK_PASSWORD"])
    url = f"{base}/v1/projects/{pid}/forms/{form}.svc/Submissions"
    params = {"$top": 1000, "$skip": 0}
    if since:
        params["$filter"] = f"__system/submissionDate gt {since}Z"
    rows = []
    while True:
        r = s.get(url, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json()["value"]
        rows += batch
        if len(batch) < params["$top"]:
            break
        params["$skip"] += params["$top"]
    return pd.json_normalize(rows)


def prepare(df):
    """Normalise column names and enforce the schema contract (fail loudly, never load partial data)."""
    df = transform.normalise_columns(df)
    missing = [c for c in CONTRACT if c not in df.columns]
    if missing:
        raise ValueError(f"Source is missing expected columns: {missing}")
    return df


def extract(source="csv", csv_path=None, since=None):
    df = fetch_central(since) if source == "central" else pd.read_csv(csv_path, dtype=str)
    df = prepare(df)
    if since and source == "csv" and not df.empty:
        df = df[transform.parse_ts(df["submitted_at"]) > pd.Timestamp(since)]
    log.info("Extracted %d new submissions (since=%s)", len(df), since)
    return df[CONTRACT].reset_index(drop=True)
