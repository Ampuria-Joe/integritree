# SOP: batch data quality control

1. **Run** `flask ingest` (nightly job or manually). Each run is logged in `etl_runs`; failures raise an alert and a non-zero exit.
2. **Gates.** G0 structure -> G1 validity and reconciliation -> G2 geospatial. An `error` rejects the record and stops it reaching later gates. A `warning` loads the record flagged.
3. **Review the Data quality section** of the dashboard:
   - Any rule over 30% of submissions is marked *check the rule*. Before contacting the field team, sample 10 flagged records by hand. If they are fine, the rule is wrong: fix it, add a regression test, and re-run with `--full`.
   - If a rule that normally fires on 1-3% jumps, suspect a form change or a new enumerator group, and ask the field supervisor.
4. **Resolve** rejected records with analysts/field teams. Corrected resubmissions reuse the instance ID and replace the earlier version on the next run (loads are idempotent).
5. **Close the loop.** Add recurring problems as new rules (see `CLAUDE.md`), or note a gap in this SOP in the weekly update.

## Known gaps / recommended improvements
- Yield bounds are national; regional bounds would reduce false errors.
- No photo or document verification yet (see `docs/ai_workflows.md`).
- Master list reconciliation checks IDs and region only, not names or phone numbers.
- EUDR polygon checks cover validity, location and area only; overlap with other plots and forest-cover layers still need PostGIS.
