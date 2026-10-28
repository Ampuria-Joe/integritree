import json
import logging
import sys
from logging.handlers import RotatingFileHandler

import click


def register(app):
    log_dir = app.config["DATA_DIR"] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("etl")
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        for h in (RotatingFileHandler(log_dir / "etl.log", maxBytes=1_000_000, backupCount=3), logging.StreamHandler()):
            h.setFormatter(fmt)
            log.addHandler(h)

    @app.cli.command("synth")
    def synth():
        """Create sample ODK exports + farmer master list in data/."""
        from pipeline.synth import generate
        for p in generate(app.config["DATA_DIR"]):
            click.echo(f"wrote {p}")

    @app.cli.command("ingest")
    @click.option("--source", type=click.Choice(["csv", "central"]), default="csv")
    @click.option("--csv", "csv_path", type=click.Path(exists=True), help="ODK CSV export (source=csv)")
    @click.option("--full", is_flag=True, help="Ignore the watermark and reload everything")
    def ingest(source, csv_path, full):
        """Run the ETL pipeline once (incremental by default)."""
        from pipeline.etl import run
        try:
            res = run(app.config["DB_PATH"], source, csv_path, full, app.config["REFERENCE_CSV"])
        except Exception:
            sys.exit(1)  # non-zero exit => GitHub Actions / cron marks the job failed
        click.echo(json.dumps(res))

    @app.cli.command("triage")
    def triage():
        """Draft an AI-assisted triage of flagged issues (aggregates only, no farmer IDs)."""
        from pipeline.ai_triage import run
        click.echo(run(app.config["DB_PATH"]))
