# AI-assisted workflows

## When to use AI vs a script
| Task | Tool | Why |
|---|---|---|
| Range, date, duplicate, polygon validity checks | Deterministic Python | Exact, free, reproducible, auditable |
| Standardising known synonyms (corn -> maize) | Lookup table | Predictable; AI adds cost and drift |
| Triage of *why* a rule fires, drafting weekly summaries | LLM (draft) | Narrative judgement on aggregates; low risk |
| Reading land certificates, forms, field photos | OCR + LLM extraction | Unstructured input; **must** be verified (below) |

## Rules
- **Privacy:** send aggregates only. No farmer IDs, names, phone numbers, GPS or photos to external APIs unless the contract and a DPIA allow it.
- **Draft status:** AI output never changes data. An analyst verifies, and the decision is recorded in the run notes.
- **Prompts are code:** version them in `prompts/`; change via pull request.
- **Track cost and accuracy:** `flask triage` prints token usage. For extraction pipelines, double-key a random 5-10% sample by hand and report field-level accuracy before trusting a batch (not implemented in this demo).

## Try it
`flask triage` prints the prompt (no key) or, with `ANTHROPIC_API_KEY` set, a draft triage of the current issue counts.

## Training analysts (outline)
1. What to share and what never to share. 2. Write a prompt with context, data shape and expected output. 3. Verify: spot-check 10 items. 4. Log what you did.
