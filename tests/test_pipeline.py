import pandas as pd
import pytest

from app import create_app
from app.db import read_df
from pipeline import geo, transform
from pipeline.dqc import run_gates
from pipeline.etl import run
from pipeline.synth import generate


def _row(**kw):
    base = dict(instance_id="a1", submitted_at="2024-08-01T10:00:00", farmer_id="F1", region="Meru",
                season="2024A", crop="maize", area_ha="1", planting_date="2024-03-10", harvest_date="2024-08-05",
                yield_kg="2500", fertilizer_kg="40", input_cost="20000", price_per_kg="45",
                plot_boundary="0.0500 37.6500 0 5; 0.0500 37.6509 0 5; 0.0509 37.6509 0 5; 0.0509 37.6500 0 5; 0.0500 37.6500 0 5",
                plot_gps="0.05045 37.65045 0 4")
    base.update(kw)
    return base


def _gates(*rows):
    return run_gates(transform.derive(transform.standardise(pd.DataFrame(rows))))


def test_polygon_area_is_about_one_hectare():
    pairs = transform.to_pairs(_row()["plot_boundary"])
    assert geo.area_ha(geo.to_poly(pairs)) == pytest.approx(1.0, rel=0.1)


def test_clean_record_passes_all_gates():
    clean, issues = _gates(_row())
    assert len(clean) == 1 and not [i for i in issues if i["severity"] == "error"]


def test_harvest_before_planting_is_rejected():
    clean, issues = _gates(_row(planting_date="2024-08-05", harvest_date="2024-03-10"))
    assert clean.empty and any(i["rule"] == "G1_DATE_ORDER" for i in issues)


def test_bowtie_polygon_is_rejected_at_gate2():
    bad = "0.05 37.65 0 5; 0.0509 37.6509 0 5; 0.05 37.6509 0 5; 0.0509 37.65 0 5; 0.05 37.65 0 5"
    clean, issues = _gates(_row(plot_boundary=bad))
    assert clean.empty and any(i["rule"] == "G2_POLY_INVALID" for i in issues)


def test_crop_synonym_is_standardised():
    clean, _ = _gates(_row(crop=" Corn "))
    assert clean.crop.iloc[0] == "maize"


def test_duplicate_submission_keeps_one_and_warns():
    clean, issues = _gates(_row(), _row())
    assert len(clean) == 1 and any(i["rule"] == "G0_DUPLICATE" for i in issues)


@pytest.fixture
def env(tmp_path):
    paths = generate(tmp_path)
    return create_app(tmp_path / "t.db"), paths, str(tmp_path / "reference" / "farmers_master.csv")


def test_incremental_and_idempotent_loads(env):
    app, (b1, b2), ref = env
    db = app.config["DB_PATH"]
    r1 = run(db, "csv", str(b1), ref_csv=ref)
    n1 = int(read_df(db, "SELECT COUNT(*) n FROM clean_records").n[0])
    assert r1["rows_loaded"] == n1 > 0 and r1["rows_rejected"] > 0
    assert run(db, "csv", str(b1), ref_csv=ref)["rows_extracted"] == 0      # watermark skips old rows
    run(db, "csv", str(b2), ref_csv=ref)
    n2 = int(read_df(db, "SELECT COUNT(*) n FROM clean_records").n[0])
    assert n2 > n1
    run(db, "csv", str(b2), full=True, ref_csv=ref)                          # full reload must not duplicate
    assert int(read_df(db, "SELECT COUNT(*) n FROM clean_records").n[0]) == n2


def test_failed_run_is_logged_and_raises(env):
    app, _, ref = env
    bad = app.config["DB_PATH"] + ".bad.csv"
    pd.DataFrame({"KEY": ["x"]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        run(app.config["DB_PATH"], "csv", bad, ref_csv=ref)
    assert read_df(app.config["DB_PATH"], "SELECT status FROM etl_runs").status.iloc[-1] == "failed"


def test_api_endpoints(env):
    app, (b1, _), ref = env
    run(app.config["DB_PATH"], "csv", str(b1), ref_csv=ref)
    c = app.test_client()
    for p in ("kpis", "insights", "trend", "regions", "margins", "input-response", "dq", "runs", "records", "filters"):
        assert c.get(f"/api/{p}").status_code == 200, p
    assert c.get("/api/kpis?crop=maize").json["records"] > 0
    assert c.get("/").status_code == 200


def test_upload_rejected_when_columns_missing():
    from pipeline import odk_client
    with pytest.raises(ValueError, match="missing expected columns"):
        odk_client.prepare(pd.DataFrame({"KEY": ["x"], "crop": ["maize"]}))


def test_exports_partition_every_record(tmp_path):
    from pipeline import odk_client
    from pipeline.etl import process
    from pipeline.exports import build_exports
    b1, b2 = generate(tmp_path)
    raw = odk_client.prepare(pd.concat([pd.read_csv(b1, dtype=str), pd.read_csv(b2, dtype=str)]))
    clean, issues, ids, warned, rejected = process(raw, pd.read_csv(tmp_path / "reference" / "farmers_master.csv", dtype=str))
    ex = build_exports(raw, clean, issues, rejected)
    assert len(ex["passed"]) + len(ex["flagged"]) + len(rejected) == len(ids)
    assert (ex["rejected"].reasons != "").all() and (ex["flagged"].reasons != "").all()


def test_streamlit_app_runs_without_error():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=90).run()
    assert not at.exception, at.exception
    assert at.title[0].value == "🌾 Integritree"
