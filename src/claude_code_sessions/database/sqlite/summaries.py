"""Per-session human-prompt summarisation (G2).

Extracts, per session, a structured 3-lens view of the developer's typed
prompts — *what task* (with ubiquitous language), *which patterns*, and *which
decisions/values* — through a model-pluggable :class:`SummaryEngine`.

The engine is an injection seam: the production backend (T2.6) calls
``sqlite-muninn``'s ``muninn_chat(model, prompt)``, while tests inject a fake
returning canned output. ``summarise_session`` owns prompt construction,
output parsing, and the upsert; the engine owns only "text in → text out".
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Protocol

__all__ = ["SummaryEngine", "summarise_session"]


class SummaryEngine(Protocol):
    """A pluggable text-completion backend, parameterised by model name.

    ``model`` selects the GGUF (its family + parameter size); ``prompt`` is the
    fully-built 3-lens extraction prompt. The return is the model's raw text,
    which ``summarise_session`` parses into the three lenses.
    """

    def summarise(self, model: str, prompt: str) -> str: ...


# The three lenses the extraction must yield, in schema-column order.
_LENSES = ("task_summary", "patterns", "decisions_values")

_PROMPT_HEADER = (
    "You are summarising a software developer's typed prompts from one coding "
    "session. Read the prompts below and reply with a single JSON object with "
    "exactly these keys:\n"
    '  "task_summary": what task is being achieved, naming the specific '
    "systems and their ubiquitous language;\n"
    '  "patterns": which architectural patterns are used or reused;\n'
    '  "decisions_values": which decisions and values are expressed.\n\n'
    "Human prompts:\n"
)


def _gather_human_text(
    conn: sqlite3.Connection, project_id: str, session_id: str
) -> list[str]:
    """The session's ``msg_kind='human'`` prompt texts, in chronological order."""
    rows = conn.execute(
        """SELECT message_content
           FROM events
           WHERE project_id = ? AND session_id = ? AND msg_kind = 'human'
           ORDER BY timestamp, line_number""",
        (project_id, session_id),
    ).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None]


def _build_prompt(human_texts: list[str]) -> str:
    return _PROMPT_HEADER + "\n\n".join(human_texts)


def _content_hash(human_texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in human_texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def summarise_session(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    engine: SummaryEngine,
    model: str,
) -> None:
    """Summarise one session's human prompts into a ``session_summaries`` row.

    Gathers the ``msg_kind='human'`` text for ``(project_id, session_id)``,
    calls ``engine`` once with ``model`` and the 3-lens prompt, parses the
    JSON reply, and upserts exactly one row keyed by ``(project_id,
    session_id, model)``.
    """
    human_texts = _gather_human_text(conn, project_id, session_id)

    # A session with no typed prompts has nothing to summarise (T2.5):
    # no engine call, no row. There is no human intent to extract.
    if not human_texts:
        return

    content_hash = _content_hash(human_texts)

    # Content-hash freshness guard (ADR2.3): an unchanged session under the
    # same model is a cache hit — skip the engine entirely so an incremental
    # run does zero work for untouched sessions. A different model has no row
    # here, so it falls through as a cache miss and writes its own row.
    existing = conn.execute(
        """SELECT content_hash FROM session_summaries
           WHERE project_id = ? AND session_id = ? AND model = ?""",
        (project_id, session_id, model),
    ).fetchone()
    if existing is not None and existing[0] == content_hash:
        return

    prompt = _build_prompt(human_texts)
    raw = engine.summarise(model, prompt)
    parsed = json.loads(raw)
    conn.execute(
        """INSERT OR REPLACE INTO session_summaries
               (project_id, session_id, model, content_hash,
                task_summary, patterns, decisions_values,
                generated_at, human_event_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            session_id,
            model,
            content_hash,
            parsed[_LENSES[0]],
            parsed[_LENSES[1]],
            parsed[_LENSES[2]],
            datetime.now(UTC).isoformat(),
            len(human_texts),
        ),
    )
    conn.commit()
