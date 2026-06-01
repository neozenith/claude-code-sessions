"""CR2.3 — recipe on REAL session text + muninn_summarize comparison.

Pulls one real session's human-prompt text from the cache and runs:
  1. the dialed-in 3-lens grammar recipe (bounded muninn_chat), and
  2. muninn_summarize (strips <think>, returns clean prose),
printing timing, validity, and the outputs — to confirm the recipe holds on
real input, not just the sample, and to show the two functions' shapes.

    uv run examples/muninn/summarize_probe.py [--model Qwen3.5-4B] [--target-chars 12000]
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time

import _muninn

from claude_code_sessions.config import CACHE_DB_PATH

log = logging.getLogger("summarize_probe")

DOGFOOD = ("-Users-joshpeak-play-claude-code-sessions", "-Users-joshpeak-play-sqlite-vector-graph")
MAX_TOKENS = _muninn.MAX_TOKENS


def pick_real_session(target_chars: int) -> tuple[str, str]:
    """The dogfood session whose human text is closest to ``target_chars``."""
    cache = sqlite3.connect(f"file:{CACHE_DB_PATH}?mode=ro", uri=True)
    try:
        rows = cache.execute(
            """SELECT session_id, SUM(LENGTH(message_content)) chars
               FROM events
               WHERE msg_kind='human' AND message_content IS NOT NULL
                     AND project_id IN (?, ?)
               GROUP BY session_id HAVING chars > 0
               ORDER BY ABS(chars - ?) LIMIT 1""",
            (*DOGFOOD, target_chars),
        ).fetchone()
        sid = rows[0]
        texts = cache.execute(
            """SELECT message_content FROM events
               WHERE msg_kind='human' AND session_id=? AND message_content IS NOT NULL
               ORDER BY timestamp, line_number""",
            (sid,),
        ).fetchall()
        return sid, "\n".join(str(t[0]) for t in texts)
    finally:
        cache.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=_muninn.DIAL_IN_MODEL, choices=list(_muninn.MODELS))
    ap.add_argument("--target-chars", type=int, default=12000)
    args = ap.parse_args()

    sid, text = pick_real_session(args.target_chars)
    log.info("real session %s — %d chars of human prompts\n", sid[:8], len(text))

    conn = _muninn.open_conn()
    n_ctx = _muninn.register(conn, args.model)
    log.info("model %s (n_ctx=%d)\n", args.model, n_ctx)

    prompt = (
        "Summarise the developer's prompts below into a single JSON object with keys "
        '"task_summary", "patterns", "decisions_values".\n\nPrompts:\n' + text
    )

    # 1. grammar recipe (bounded, structured)
    t0 = time.perf_counter()
    raw = conn.execute(
        "SELECT muninn_chat(?, ?, ?, ?)",
        (args.model, prompt, _muninn.THREE_LENS_GBNF, MAX_TOKENS),
    ).fetchone()[0]
    secs = time.perf_counter() - t0
    try:
        obj = json.loads(raw or "")
        ok = all(k in obj for k in _muninn.LENS_KEYS)
        log.info("grammar recipe: %.2fs, valid_json=%s all_keys=%s", secs, True, ok)
        log.info("  task_summary: %s\n", str(obj.get("task_summary", ""))[:300])
    except json.JSONDecodeError as exc:
        log.info("grammar recipe: %.2fs, valid_json=False (%s)", secs, exc)
        log.info("  raw=%s\n", (raw or "")[:200])

    # 2. muninn_summarize (clean prose, <think> stripped internally)
    t0 = time.perf_counter()
    summary = conn.execute("SELECT muninn_summarize(?, ?)", (args.model, text)).fetchone()[0]
    log.info("muninn_summarize: %.2fs, %d chars", time.perf_counter() - t0, len(summary or ""))
    log.info("  %s", (summary or "(empty)")[:300])
    conn.close()


if __name__ == "__main__":
    main()
