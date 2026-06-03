"""Verify the n_ctx fix loads Llama-3.1-8B at the requested context (no inference).

Grounded in llama_chat.c: muninn_chat_model(path, n_ctx) consumes n_ctx at load
time; the muninn_chat_models.n_ctx column reflects the LOADED context (out->n_ctx).
So registering via the fixed path and SELECTing n_ctx is a fast, decisive check
that the context is what we asked for (was silently 16384 = 128K/8 before).

Run:  uv run --frozen scripts/ctx_smoke.py
"""

from __future__ import annotations

import os

os.environ.setdefault("MUNINN_LOG_LEVEL", "info")  # surface context negotiation

from claude_code_sessions.summarise_cli import (  # noqa: E402
    DEFAULT_N_CTX,
    _open_chat_connection,
    gguf_path,
)

MODEL = "Llama-3.1-8B"


def main() -> None:
    path = gguf_path(MODEL)
    if path is None:
        print(f"no GGUF for {MODEL}")
        return
    print(f"loading {MODEL} at requested n_ctx={DEFAULT_N_CTX} ...")
    conn = _open_chat_connection(MODEL, path, n_ctx=DEFAULT_N_CTX)
    rows = conn.execute("SELECT name, n_ctx FROM temp.muninn_chat_models").fetchall()
    for name, n_ctx in rows:
        verdict = "OK (fix works)" if n_ctx and int(n_ctx) >= DEFAULT_N_CTX else "STILL WRONG"
        print(f"  {name}: loaded n_ctx={n_ctx}  -> {verdict}")
    conn.close()


if __name__ == "__main__":
    main()
