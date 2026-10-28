"""Integritree: Seasonal Performance Pipeline Intelligence (Streamlit front end)."""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app import analytics as an
from pipeline import odk_client
from pipeline.dqc import SUSPECT_RATE
from pipeline.etl import process
from pipeline.exports import build_exports
from pipeline.synth import generate

st.set_page_config(page_title="Integritree", page_icon="assets/icon.png", layout="wide")
COLORS = {"maize": "#D9A21B", "beans": "#B4472F", "sorghum": "#7A5C8C", "potato": "#3B6E9E", "wheat": "#1F6B4F"}
MAX_MB, MAX_ROWS = 25, 50_000


def run_all(raw, masters):
    clean, issues, ids, warned, rejected = process(raw, masters)
    ex = build_exports(raw, clean, issues, rejected)
    received = len(ids) + int(raw.instance_id.isna().sum())
    iss = pd.DataFrame(issues, columns=["instance_id", "gate", "rule", "severity", "detail"])
    hits = iss.groupby("rule").instance_id.agg(lambda s: s.nunique() if s.notna().any() else len(s))
    dq = an.dq_from(received, len(clean), int((ex["accepted"].has_warning == 1).sum()), hits)
    return {**ex, "raw": raw, "dq": dq, "reconciled": masters is not None}


@st.cache_data(show_spinner="Preparing sample data…")
def demo():
    d = Path(tempfile.mkdtemp())
    b1, b2 = generate(d)
    raw = odk_client.prepare(pd.concat([pd.read_csv(b1, dtype=str), pd.read_csv(b2, dtype=str)]))
    return run_all(raw, pd.read_csv(d / "reference" / "farmers_master.csv", dtype=str))


def read_upload(f):
    """Raises ValueError with a plain-language reason when the file does not meet the standard."""
    if f.size > MAX_MB * 1024 * 1024:
        raise ValueError(f"File is larger than {MAX_MB} MB.")
    try:
        df = pd.read_csv(f, dtype=str)
    except Exception:
        raise ValueError("This file could not be read as a CSV.")
    if df.empty:
        raise ValueError("The file has no rows.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"The file has more than {MAX_ROWS:,} rows.")
    return odk_client.prepare(df)  # rejects when required columns are missing


def csv(df):
    return df.to_csv(index=False).encode()


base = demo()
st.logo("assets/logo.svg", size="large")
st.title("Integritree")
st.caption("Seasonal Performance Pipeline Intelligence")

# ---- filters first
sources = {"Sample data": base}
if "upload" in st.session_state:
    sources["Your upload"] = st.session_state["upload"]
c0, c1, c2, c3 = st.columns(4)
choice = c0.selectbox("Data source", list(sources), index=len(sources) - 1)
data = sources[choice]
acc = data["accepted"]

# ---- side menu: upload, validate, download
with st.sidebar:
    st.header("Check your data")
    st.download_button("1. Download CSV template", csv(base["raw"].head(3)), "integritree_template.csv", "text/csv", width="stretch")
    with st.expander("Required columns"):
        st.code(", ".join(odk_client.CONTRACT), language=None)
    up = st.file_uploader("2. Upload ODK export (CSV)", type="csv")
    mas = st.file_uploader("Optional: farmer master list (farmer_id, region)", type="csv")
    st.caption(f"Accepted only if every required column is present (max {MAX_MB} MB). Rows failing the quality gates are held back with reasons.")
    if st.button("3. Validate and analyse", type="primary", width="stretch", disabled=up is None):
        try:
            raw = read_upload(up)
            masters = None
            if mas is not None:
                masters = pd.read_csv(mas, dtype=str)
                if not {"farmer_id", "region"} <= set(masters.columns):
                    raise ValueError("The master list needs farmer_id and region columns.")
            res = run_all(raw, masters)
            if res["accepted"].empty:
                top = pd.DataFrame(res["dq"]["rules"]).query("severity == 'error' and records > 0").sort_values("records", ascending=False).head(3)
                raise ValueError("Every row failed the quality gates. Most common reasons: " + "; ".join(f"{r} ({n})" for r, n in zip(top.rule, top.records)))
            st.session_state["upload"] = res
            st.session_state["upload_msg"] = f"Accepted: {len(res['accepted']):,} of {res['dq']['funnel']['received']:,} rows passed."
            st.rerun()
        except ValueError as e:
            st.error(f"File rejected. {e}")
    if "upload" in st.session_state:
        st.success(st.session_state.get("upload_msg", "Upload loaded."))
        if st.button("Clear upload and return to sample data", width="stretch"):
            del st.session_state["upload"]
            st.rerun()

    st.divider()
    st.header("Download data")
    st.caption(f"Complete {choice.lower()}; the filters do not apply.")
    st.download_button(f"Passed ({len(data['passed']):,})", csv(data["passed"]), "integritree_passed.csv", "text/csv", width="stretch")
    st.download_button(f"Flagged ({len(data['flagged']):,})", csv(data["flagged"]), "integritree_flagged.csv", "text/csv", width="stretch")
    st.download_button(f"Rejected ({len(data['rejected']):,})", csv(data["rejected"]), "integritree_rejected.csv", "text/csv", width="stretch")
    st.caption("Passed and flagged records feed the charts. Flagged and rejected files include the reasons.")
opt = lambda col: [""] + sorted(acc[col].dropna().unique())
fs = c1.selectbox("Season", opt("season"), format_func=lambda v: v or "All seasons")
fc = c2.selectbox("Crop", opt("crop"), format_func=lambda v: v or "All crops")
fr = c3.selectbox("Region", opt("region"), format_func=lambda v: v or "All regions")
df = acc
for col, v in (("season", fs), ("crop", fc), ("region", fr)):
    if v:
        df = df[df[col] == v]

# ---- key figures
k = an.kpis(df)
if not k["records"]:
    st.warning("No records match these filters.")
    st.stop()
m = st.columns(5)
m[0].metric("Records", f"{k['records']:,}")
m[1].metric("Area (ha)", f"{k['area_ha']:,.0f}")
m[2].metric("Yield (kg/ha)", f"{k['yield_kg_ha']:,.0f}")
m[3].metric("Margin (KES/ha)", f"{k['margin_ha']:,.0f}")
m[4].metric("Records flagged", f"{k['flagged_pct']}%")

# ---- charts
left, right = st.columns(2)
t = an.trend(df)
with left:
    mode = st.radio("Trend measure", ["Index (100 = crop average)", "kg/ha"], horizontal=True)
    if mode.startswith("Index"):
        fig = px.line(x=t["seasons"], y=t["index"], markers=True, labels={"x": "Season", "y": "Yield index"},
                      title="Yield index by season")
        fig.update_traces(line_color="#1F6B4F")
    else:
        long = pd.DataFrame(t["series"], index=t["seasons"]).rename_axis("season").reset_index().melt("season", var_name="crop", value_name="kg_ha")
        fig = px.line(long, x="season", y="kg_ha", color="crop", markers=True, color_discrete_map=COLORS, title="Yield by season (kg/ha)")
    st.plotly_chart(fig, width="stretch")
with right:
    r = an.regions(df)
    vals = r["kg_ha"] if fc else r["index"]
    fig = px.bar(x=vals, y=r["labels"], orientation="h", labels={"x": "kg/ha" if fc else "Index", "y": ""},
                 title=("Yield by region (kg/ha)" if fc else "Yield index by region (100 = crop average)"))
    fig.update_traces(marker_color="#1F6B4F")
    st.plotly_chart(fig, width="stretch")
left, right = st.columns(2)
mg = an.margins(df)
fig = px.bar(x=mg["labels"], y=mg["margin_ha"], title="Gross margin per hectare by crop (KES)", labels={"x": "", "y": "KES/ha"})
fig.update_traces(marker_color=["#B4472F" if v < 0 else "#D9A21B" for v in mg["margin_ha"]])
left.plotly_chart(fig, width="stretch")
ir = an.input_response(df)
if ir["fit"]:
    pts = pd.DataFrame(ir["points"])
    ycol = "y_kg_ha" if fc else "y_idx"
    fig = px.scatter(pts, x="x", y=ycol, opacity=.5, title="Fertiliser vs yield", labels={"x": "Fertiliser kg/ha", ycol: "Yield kg/ha" if fc else "Yield index"})
    fig.update_traces(marker_color="#1F6B4F")
    if not fc:
        xs = np.array([0, pts.x.max()])
        fig.add_trace(go.Scatter(x=xs, y=ir["fit"]["intercept_idx"] + ir["fit"]["slope_idx"] * xs, mode="lines", name="Trend", line_color="#B4472F"))
    right.plotly_chart(fig, width="stretch")

# ---- data quality
st.header("Data quality")
f = data["dq"]["funnel"]
q = st.columns(4)
q[0].metric("Received", f"{f['received']:,}")
q[1].metric("Passed all gates", f"{f['loaded']:,}")
q[2].metric("…with warnings", f"{f['flagged']:,}")
q[3].metric("Rejected", f"{f['rejected']:,}")
if not data["reconciled"]:
    st.info("No farmer master list supplied, so reconciliation checks were skipped.")
rules = pd.DataFrame(data["dq"]["rules"])
rules["effect"] = rules.severity.map({"error": "Rejects", "warning": "Flags"})
rules["note"] = np.where(rules.suspect, "Check the rule before blaming the data", "")
with st.expander(f"Checks that fired (a check firing on over {SUSPECT_RATE:.0%} of records is marked)", expanded=True):
    st.dataframe(rules[rules.records > 0][["rule", "description", "gate", "effect", "records", "rate", "note"]], hide_index=True, width="stretch")

st.header("Records")
with st.expander("Preview filtered records"):
    st.dataframe(df[[c for c in ("submitted_at", "farmer_id", "region", "season", "crop", "area_ha", "yield_kg_ha", "gross_margin", "has_warning")]].sort_values("submitted_at", ascending=False), hide_index=True, width="stretch")

# ---- findings last
st.header("What stands out")
for line in an.insights(df):
    st.markdown(f"- {line}")
