<img src="assets/logo.svg" width="72" alt="Integritree logo">

# Integritree: Seasonal Performance Pipeline Intelligence

**Live demo:** https://integritree.streamlit.app/


ETL pipeline and Flask dashboard that turns raw ODK survey submissions into agricultural **performance analysis** across seasons, crops and regions, with a gate-based data quality framework in front of it.

```
ODK Central (OData) / CSV export
        |  extract: incremental by submission-date watermark, schema contract
        v
 raw_submissions  --standardise/derive-->  DQC gates G0 -> G1 -> G2  --> clean_records
                                              |                            |
                                         dqc_issues                  Flask API + dashboard
                                 etl_runs (log, watermark, alerts)
```

## Two front ends, one pipeline
- `streamlit_app.py` is the hosted demo: filters, key figures, charts, data quality, **CSV upload with validation**, **downloads of passed / flagged / rejected data**, and findings last.
- `app/` is the Flask version (REST API + dashboard) used with the SQLite database and `flask ingest` CLI.
Both share `pipeline/` and `app/analytics.py`.

```bash
streamlit run streamlit_app.py
```

## Quick start (Flask + CLI)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app:create_app
flask synth                                          # sample ODK exports with injected defects
flask ingest --csv data/incoming/odk_batch_1.csv     # first load
flask ingest --csv data/incoming/odk_batch_2.csv     # incremental load
flask run                                            # http://127.0.0.1:5000
pytest -q
```
Live data: set `ODK_URL, ODK_EMAIL, ODK_PASSWORD, ODK_PROJECT_ID, ODK_FORM_ID`, then `flask ingest --source central`. Adjust `CONTRACT` in `pipeline/odk_client.py` to your form's field names.

## What the dashboard shows
Plain-language findings, key figures, yield by season (index or kg/ha), regional comparison, margin by crop, fertiliser-versus-yield, the quality funnel with per-rule hit rates, pipeline run history and filterable records. Filters: season, crop, region.

## How this maps to the role
| Requirement | Where |
|---|---|
| Clean, standardise, validate ODK data | `pipeline/transform.py`, `pipeline/dqc.py` |
| Gate-based DQC, reconcile with master list | `dqc.py` gates; `G1_UNKNOWN_FARMER`, `G1_REGION_MISMATCH` |
| Tell data problems from check defects | Per-rule hit rates, `suspect` flag at 30%, `docs/SOP_dqc.md` |
| Identify SOP gaps | "Known gaps" in `docs/SOP_dqc.md` |
| ETL with incremental loads, logging, failure alerts | `pipeline/etl.py` (watermark, `etl_runs`, `ALERT_WEBHOOK`, non-zero exit) |
| Scheduled jobs on GitHub Actions | `.github/workflows/etl.yml` |
| Schemas, data dictionary | `app/schema.sql`, `docs/data_dictionary.md` |
| Tested Python and SQL | `tests/` (12 tests, run by CI on every push and before every load) |
| Geospatial / EUDR-style polygon validation | `pipeline/geo.py`, gate G2 |
| AI-assisted workflows, prompts, context files, runbooks | `pipeline/ai_triage.py`, `prompts/`, `CLAUDE.md`, `docs/ai_workflows.md` |
| AI vs deterministic, cost, privacy | `docs/ai_workflows.md` |
| Dashboards, SOPs, training material | `app/`, `docs/` |

## Runbook
- **Run failed:** read `data/logs/etl.log` and the dashboard run table. A missing-column error means the form changed: update `CONTRACT` and the data dictionary.
- **Reload everything:** `flask ingest --csv <file> --full` (safe, loads are idempotent by instance ID).
- **Add a rule:** see `CLAUDE.md`.

## Limits of this demo
- Storage is SQLite for portability. `schema.sql` is plain SQL, but moving to PostgreSQL/PostGIS needs a driver swap in `app/db.py` and `etl.py`. GitHub Actions runners are ephemeral, so point `DB_PATH`/database at persistent storage.
- Sample data is synthetic. Insights are descriptive associations, not causal findings.
- OCR/LLM document extraction is described in `docs/ai_workflows.md` but not implemented.
- The dashboard loads Chart.js and fonts from CDNs and needs internet access in the browser.
- Add authentication before exposing farmer-level records.
