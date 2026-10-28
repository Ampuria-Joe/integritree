"""AI-assisted triage of DQC issues. Sends only aggregate rule counts (no farmer IDs, no GPS),
produces a *draft* for the analyst to verify. Falls back to printing the prompt without a key."""
import os
from pathlib import Path

import requests

from app.db import read_df

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "dqc_triage.md"


def build_prompt(db):
    d = read_df(db, "SELECT rule, severity, COUNT(*) n, COUNT(DISTINCT instance_id) records FROM dqc_issues "
                    "GROUP BY rule, severity ORDER BY n DESC")
    total = int(read_df(db, "SELECT COUNT(*) n FROM raw_submissions").n[0])
    return PROMPT.read_text() + f"\n\nBatch size: {total} submissions\n\n" + d.to_string(index=False)


def run(db):
    prompt = build_prompt(db)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "[ANTHROPIC_API_KEY not set - prompt that would be sent]\n\n" + prompt
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      json={"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 800,
                            "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    j = r.json()
    u = j.get("usage", {})
    return ("DRAFT - analyst must verify before acting\n"
            f"(tokens in/out: {u.get('input_tokens')}/{u.get('output_tokens')})\n\n" + j["content"][0]["text"])
