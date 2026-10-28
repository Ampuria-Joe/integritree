from flask import Blueprint, current_app, jsonify, render_template, request

from . import analytics as an
from .db import read_df

bp = Blueprint("main", __name__)


def _db():
    return current_app.config["DB_PATH"]


def _df():
    where, params = [], []
    for k in ("season", "crop", "region"):  # whitelist: column names never come from the request
        if request.args.get(k):
            where.append(f"{k}=?")
            params.append(request.args[k])
    sql = "SELECT * FROM clean_records" + (" WHERE " + " AND ".join(where) if where else "")
    return read_df(_db(), sql, params)


@bp.get("/")
def dashboard():
    return render_template("dashboard.html")


@bp.get("/health")
def health():
    return {"status": "ok"}


@bp.get("/api/filters")
def filters():
    d = read_df(_db(), "SELECT DISTINCT season, crop, region FROM clean_records")
    return jsonify({k: sorted(d[k].dropna().unique().tolist()) for k in ("season", "crop", "region")})


@bp.get("/api/kpis")
def kpis():
    return jsonify(an.kpis(_df()))


@bp.get("/api/insights")
def insights():
    return jsonify(an.insights(_df()))


@bp.get("/api/trend")
def trend():
    return jsonify(an.trend(_df()))


@bp.get("/api/regions")
def regions():
    return jsonify(an.regions(_df()))


@bp.get("/api/margins")
def margins():
    return jsonify(an.margins(_df()))


@bp.get("/api/input-response")
def input_response():
    return jsonify(an.input_response(_df()))


@bp.get("/api/dq")
def dq():
    return jsonify(an.dq_summary(_db()))


@bp.get("/api/runs")
def runs():
    return jsonify(read_df(_db(), "SELECT * FROM etl_runs ORDER BY run_id DESC LIMIT 10").to_dict("records"))


@bp.get("/api/records")
def records():
    d = _df().sort_values("submitted_at", ascending=False)
    page = max(int(request.args.get("page", 0)), 0)
    cols = ["submitted_at", "farmer_id", "region", "season", "crop", "area_ha", "yield_kg_ha", "gross_margin", "has_warning"]
    chunk = d.iloc[page * 15:(page + 1) * 15][cols].round(1)
    return jsonify({"total": len(d), "rows": chunk.astype(object).where(chunk.notna(), None).to_dict("records")})
