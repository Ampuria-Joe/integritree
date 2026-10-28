"""ETL run: extract -> standardise -> derive -> DQC gates -> idempotent load, with run log + alerts."""
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from app.db import connect
from . import odk_client, transform
from .dqc import load_masters, run_gates

log = logging.getLogger("etl")
FMT = "%Y-%m-%dT%H:%M:%S"
CLEAN_COLS = ["instance_id", "submitted_at", "farmer_id", "region", "season", "crop", "area_ha",
              "polygon_area_ha", "planting_date", "harvest_date", "days_to_harvest", "yield_kg",
              "yield_kg_ha", "fertilizer_kg_ha", "input_cost", "price_per_kg", "revenue",
              "gross_margin", "lat", "lon", "has_warning", "run_id"]


def _now():
    return datetime.now(timezone.utc).strftime(FMT)


def alert(msg):
    log.error(msg)
    url = os.environ.get("ALERT_WEBHOOK")  # Slack/Teams-style incoming webhook
    if url:
        try:
            req = urllib.request.Request(url, json.dumps({"text": msg}).encode(),
                                         {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            log.exception("Could not send alert")


def process(raw, masters=None):
    """Pure transform + DQC (no database). Returns clean, issues, ids, warned ids, rejected ids."""
    df = transform.derive(transform.standardise(raw))
    clean, issues = run_gates(df, masters)
    ids = list(df.instance_id.dropna().unique())
    warned = {i["instance_id"] for i in issues if i["severity"] == "warning"}
    return clean, issues, ids, warned, set(ids) - set(clean.instance_id)


def run(db_path, source="csv", csv_path=None, full=False, ref_csv=None):
    conn = connect(db_path)
    run_id = conn.execute("INSERT INTO etl_runs(started_at, source, status) VALUES(?,?,'running')",
                          (_now(), source)).lastrowid
    conn.commit()
    stats = dict(rows_extracted=0, rows_loaded=0, rows_rejected=0, rows_warned=0)
    try:
        since = None if full else conn.execute(
            "SELECT MAX(watermark) FROM etl_runs WHERE status='success'").fetchone()[0]
        raw = odk_client.extract(source, csv_path, since)
        stats["rows_extracted"], wm, msg = len(raw), since, "no new submissions"
        if not raw.empty:
            wm = transform.parse_ts(raw["submitted_at"]).max().strftime(FMT)
            conn.executemany(
                "INSERT OR REPLACE INTO raw_submissions VALUES(?,?,?,?)",
                [(r["instance_id"], r["submitted_at"], run_id, json.dumps(r, default=str))
                 for r in raw.astype(object).where(raw.notna(), None).to_dict("records")
                 if r["instance_id"]])
            clean, issues, ids, warned, rejected = process(raw, load_masters(ref_csv))
            out = clean.copy()
            out["has_warning"] = out.instance_id.isin(warned).astype(int)
            out["run_id"] = run_id
            out["submitted_at"] = out.submitted_at.dt.strftime(FMT)
            for c in ("planting_date", "harvest_date"):
                out[c] = out[c].dt.strftime("%Y-%m-%d")
            out = out[CLEAN_COLS].astype(object)
            out = out.where(out.notna(), None)
            conn.executemany("DELETE FROM dqc_issues WHERE instance_id=?", [(i,) for i in ids])
            conn.executemany("DELETE FROM clean_records WHERE instance_id=?", [(i,) for i in rejected])
            conn.executemany(f"INSERT OR REPLACE INTO clean_records VALUES({','.join('?' * len(CLEAN_COLS))})",
                             [tuple(r) for r in out.itertuples(index=False)])
            conn.executemany("INSERT INTO dqc_issues(run_id,instance_id,gate,rule,severity,detail) VALUES(?,?,?,?,?,?)",
                             [(run_id, i["instance_id"], i["gate"], i["rule"], i["severity"], i["detail"]) for i in issues])
            stats.update(rows_loaded=len(out), rows_rejected=len(rejected),
                         rows_warned=len(warned & set(out.instance_id)))
            msg = "ok"
        conn.execute("UPDATE etl_runs SET finished_at=?, status='success', rows_extracted=?, rows_loaded=?,"
                     " rows_rejected=?, rows_warned=?, watermark=?, message=? WHERE run_id=?",
                     (_now(), *stats.values(), wm, msg, run_id))
        conn.commit()
        log.info("Run %s finished: %s", run_id, stats)
        return {"run_id": run_id, **stats}
    except Exception as e:
        conn.rollback()
        conn.execute("UPDATE etl_runs SET finished_at=?, status='failed', message=? WHERE run_id=?",
                     (_now(), str(e)[:500], run_id))
        conn.commit()
        alert(f"ODK ETL run {run_id} FAILED: {e}")
        raise
    finally:
        conn.close()
