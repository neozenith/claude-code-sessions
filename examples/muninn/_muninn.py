"""Shared muninn wiring for the CR2 dial-in probes.

Mirrors how the app itself loads the extension (``sqlite_muninn.load`` +
``temp.muninn_chat_models``), not the reference repo's ``build/muninn`` path, so
the probes exercise the exact runtime the summariser uses.

Model policy (CR2): dial in on a 4B; never below 2B. Sub-2B models are less
capable and were the leading cause of the thinking / JSON-termination failures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_muninn

# GGUF search dirs, in priority order — same as summarise_cli.MODELS_DIRS.
MODELS_DIRS: tuple[Path, ...] = (
    Path.home() / ".claude" / "cache" / "models",
    Path.home() / "play" / "sqlite-vector-graph" / "models",
)

# model_id -> gguf filename. 4B is the dial-in default; the 2B/4B bench models
# are the validation set. The 0.8B is deliberately absent (CR2 model policy).
MODELS: dict[str, str] = {
    "Qwen3.5-9B": "Qwen3.5-9B-Q4_K_M.gguf",
    "Qwen3.5-4B": "Qwen3.5-4B-Q4_K_M.gguf",  # dial-in default (reliable)
    "gemma-4-E4B": "gemma-4-E4B-it-Q4_K_M.gguf",
    "Qwen3.5-2B": "Qwen3.5-2B-Q4_K_M.gguf",
    "gemma-4-E2B": "gemma-4-E2B-it-Q4_K_M.gguf",
}

DIAL_IN_MODEL = "Qwen3.5-4B"


def gguf_path(model_id: str) -> Path:
    """Resolve a model_id to its on-disk GGUF, or fail loud."""
    filename = MODELS[model_id]
    for directory in MODELS_DIRS:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    searched = ", ".join(str(d) for d in MODELS_DIRS)
    raise FileNotFoundError(f"no GGUF {filename!r} for {model_id!r} in: {searched}")


def open_conn() -> sqlite3.Connection:
    """A connection with the muninn extension loaded."""
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_muninn.load(conn)
    conn.enable_load_extension(False)
    return conn


def register(conn: sqlite3.Connection, model_id: str) -> int:
    """Register ``model_id``'s GGUF as a chat model; return its context size."""
    conn.execute(
        "INSERT INTO temp.muninn_chat_models(name, model) SELECT ?, muninn_chat_model(?)",
        (model_id, str(gguf_path(model_id))),
    )
    row = conn.execute(
        "SELECT n_ctx FROM muninn_chat_models WHERE name = ?", (model_id,)
    ).fetchone()
    return int(row[0])


# GBNF grammar forcing the exact 3-lens object the summariser needs. A
# grammar-constrained call cannot emit a <think> preamble (it must match `root`
# from the first token), which is what tames the thinking-runaway.
#
# Two hard-won constraints:
#  * `root` MUST be a single logical line — muninn's GBNF parser treats a newline
#    as end-of-rule, so a wrapped `root ::=` errors ("expecting name") and (worse)
#    segfaults the process.
#  * the unescaped string class MUST exclude control chars (\x00-\x1F) — otherwise
#    the model emits a raw newline inside a value and the JSON is invalid.
#  * each lens string is length-bounded ({0,LENS_MAX}) so the object ALWAYS closes
#    within the token budget — an unbounded string on a real (rich) session runs
#    past max_tokens and truncates mid-string into invalid JSON.
LENS_MAX = 300  # max chars per lens value (≈50 words — ample for a screen)

THREE_LENS_GBNF = (
    r'root ::= "{" ws "\"task_summary\"" ws ":" ws string ws "," ws '
    r'"\"patterns\"" ws ":" ws string ws "," ws '
    r'"\"decisions_values\"" ws ":" ws string ws "}"'
    "\n"
    r'string ::= "\"" ( [^"\\\x00-\x1F] | "\\" ["\\/bfnrt] ){0,' + str(LENS_MAX) + r'} "\""'
    "\n"
    r"ws ::= [ \t\n]*"
)

# Generous enough to always complete the length-bounded object (3×LENS_MAX chars
# ≈ ~320 tokens + structure), with headroom — but still a hard ceiling.
MAX_TOKENS = 512

LENS_KEYS = ("task_summary", "patterns", "decisions_values")
