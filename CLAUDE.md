# Project context for AI assistants
Flask dashboard + ETL for ODK crop-production surveys (performance analysis by season, crop, region).
- Pipeline code: `pipeline/` (extract -> transform -> dqc gates -> load). Dashboard: `app/`.
- Run tests before any change: `pytest -q`. Never weaken a DQC rule to make a test pass; fix the data or the rule's logic and say which.
- DQC rules live in `pipeline/dqc.py:RULES`. New rule = entry in RULES + check in a gate + a test + a line in `docs/data_dictionary.md`.
- Privacy: never send farmer IDs, names, GPS or photos to an external LLM. Aggregates only (see `docs/ai_workflows.md`).
- All AI output is a draft. Record what the AI did and who verified it.
