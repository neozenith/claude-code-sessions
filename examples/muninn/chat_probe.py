"""CR2.1 — muninn_chat call-shape probe.

Drives `muninn_chat(model, prompt [, grammar [, max_tokens]])` in its 2/3/4-arg
forms on the dial-in model and prints, per call: the <think>/response split,
output length, and wall time. Shows that a grammar (3-arg) suppresses the think
preamble and an explicit max_tokens (4-arg) bounds the call.

    uv run examples/muninn/chat_probe.py [--model Qwen3.5-4B]
"""

from __future__ import annotations

import argparse
import logging
import re
import time

import _muninn

log = logging.getLogger("chat_probe")

_THINK_RE = re.compile(r"<think>(.*?)</think>(.*)", re.DOTALL)

# A prompt that nudges a thinking model to reason before answering — the shape
# that runs away when the call is unbounded.
PROMPT = (
    "Summarise, in one sentence, what this developer was doing: "
    "'wire the FastAPI summary endpoint to the SQLite rollup table and add a vitest'."
)


def split_think(raw: str) -> tuple[str, str]:
    m = _THINK_RE.search(raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", raw.strip()


def _chat(conn: object, sql_args: tuple[object, ...]) -> tuple[str, float]:
    placeholders = ", ".join("?" * len(sql_args))
    t0 = time.perf_counter()
    row = conn.execute(f"SELECT muninn_chat({placeholders})", sql_args).fetchone()  # type: ignore[attr-defined]
    return (row[0] if row and row[0] is not None else ""), time.perf_counter() - t0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=_muninn.DIAL_IN_MODEL, choices=list(_muninn.MODELS))
    args = ap.parse_args()

    conn = _muninn.open_conn()
    t0 = time.perf_counter()
    n_ctx = _muninn.register(conn, args.model)
    log.info("loaded %s (n_ctx=%d, %.2fs)\n", args.model, n_ctx, time.perf_counter() - t0)

    calls = [
        ("2-arg plain", (args.model, PROMPT)),
        ("3-arg + grammar", (args.model, PROMPT, _muninn.THREE_LENS_GBNF)),
        (
            f"4-arg + grammar + max_tokens={_muninn.MAX_TOKENS}",
            (args.model, PROMPT, _muninn.THREE_LENS_GBNF, _muninn.MAX_TOKENS),
        ),
    ]
    for label, sql_args in calls:
        raw, secs = _chat(conn, sql_args)
        thinking, response = split_think(raw)
        log.info("[%s] %.2fs, %d chars out", label, secs, len(raw))
        if thinking:
            log.info("  <think> %d chars (suppressed by grammar when empty)", len(thinking))
        log.info("  response: %s\n", (response or "(empty — exhausted tokens on reasoning)")[:400])


if __name__ == "__main__":
    main()
