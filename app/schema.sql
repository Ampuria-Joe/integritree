-- Portable SQL: runs on SQLite for the demo; change AUTOINCREMENT->SERIAL and
-- add geometry columns when pointing at PostgreSQL/PostGIS.
CREATE TABLE IF NOT EXISTS etl_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT, source TEXT, status TEXT,
  rows_extracted INTEGER, rows_loaded INTEGER, rows_rejected INTEGER, rows_warned INTEGER,
  watermark TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS raw_submissions (
  instance_id TEXT PRIMARY KEY, submitted_at TEXT, run_id INTEGER, payload TEXT
);
CREATE TABLE IF NOT EXISTS clean_records (
  instance_id TEXT PRIMARY KEY, submitted_at TEXT, farmer_id TEXT, region TEXT,
  season TEXT, crop TEXT, area_ha REAL, polygon_area_ha REAL,
  planting_date TEXT, harvest_date TEXT, days_to_harvest INTEGER,
  yield_kg REAL, yield_kg_ha REAL, fertilizer_kg_ha REAL,
  input_cost REAL, price_per_kg REAL, revenue REAL, gross_margin REAL,
  lat REAL, lon REAL, has_warning INTEGER, run_id INTEGER
);
CREATE TABLE IF NOT EXISTS dqc_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, instance_id TEXT,
  gate TEXT, rule TEXT, severity TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_clean_season_crop ON clean_records(season, crop);
CREATE INDEX IF NOT EXISTS ix_issues_rule ON dqc_issues(rule);
