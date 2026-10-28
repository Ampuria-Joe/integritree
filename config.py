import os
from pathlib import Path

ROOT = Path(__file__).parent


class Config:
    DATA_DIR = ROOT / "data"
    DB_PATH = os.environ.get("DB_PATH", str(ROOT / "data" / "performance.db"))
    REFERENCE_CSV = os.environ.get("REFERENCE_CSV", str(ROOT / "data" / "reference" / "farmers_master.csv"))
    # ODK Central (used by `flask ingest --source central`)
    ODK_URL = os.environ.get("ODK_URL")
    ODK_EMAIL = os.environ.get("ODK_EMAIL")
    ODK_PASSWORD = os.environ.get("ODK_PASSWORD")
    ODK_PROJECT_ID = os.environ.get("ODK_PROJECT_ID")
    ODK_FORM_ID = os.environ.get("ODK_FORM_ID", "crop_production")
