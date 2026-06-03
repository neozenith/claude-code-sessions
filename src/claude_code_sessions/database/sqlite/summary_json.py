"""Robust extraction of the 3-lens JSON object from a chat model's raw reply.

Real local GGUFs don't reliably emit a bare JSON object: Qwen-family models wrap
it in ``<think>…</think>`` reasoning, others prepend prose or fence it in
```json``` blocks. A bare ``json.loads(raw)`` therefore fails on perfectly good
output. This module finds the first balanced ``{…}`` object in the text and
validates it carries the three lens keys — still **fail-loud** (raises) when no
such object exists, so a genuine model/parse failure never produces a blank
summary (the project's no-graceful-degradation rule).

Shared by ``summaries.summarise_session`` (session extraction) and
``merge._parse_summary`` (roll-up merging). It imports nothing from either, so
there is no import cycle.
"""

from __future__ import annotations

import json
from typing import Any

LENS_KEYS = ("task_summary", "patterns", "decisions_values")


def _first_json_object(text: str) -> str:
    """Return the first balanced ``{…}`` substring, respecting strings/escapes."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    raise ValueError("no balanced JSON object found in model output")


def parse_lenses(raw: str) -> dict[str, str]:
    """Parse a model reply into the three lens strings (fail-loud).

    Tolerates leading/trailing prose, ``<think>`` traces, and code fences by
    extracting the first balanced JSON object; raises ``ValueError`` /
    ``KeyError`` if no object with all three lens keys is present.
    """
    obj: dict[str, Any] = json.loads(_first_json_object(raw))
    missing = [k for k in LENS_KEYS if k not in obj]
    if missing:
        raise KeyError(f"model output JSON missing lens keys {missing}: {obj!r}")
    return {k: str(obj[k]) for k in LENS_KEYS}


# CR5 extractive path: each lens is a LIST of 0..N atomic claims, not one string.
# An empty list is a valid, first-class result (a session may express no decisions).
# ``learnings`` (4th lens, added 2026-06-03): process/skill improvements + failure
# modes to systematically avoid — the retrospective signal for getting better.
LENS_LIST_KEYS = ("tasks", "patterns", "decisions_values", "learnings")


def parse_lens_lists(raw: str) -> dict[str, list[str]]:
    """Parse a model reply into the three lens **lists** of atomic claims (fail-loud).

    Like :func:`parse_lenses` but each lens is a JSON array (0..N items) rather than a
    single string. Tolerates ``<think>`` traces / prose / code fences via the same
    balanced-object extraction. Raises ``KeyError`` if a lens key is missing and
    ``ValueError`` if a lens value is not a JSON array (never silently coerces — the
    project's fail-loud rule)."""
    obj: dict[str, Any] = json.loads(_first_json_object(raw))
    missing = [k for k in LENS_LIST_KEYS if k not in obj]
    if missing:
        raise KeyError(f"model output JSON missing lens keys {missing}: {obj!r}")
    out: dict[str, list[str]] = {}
    for key in LENS_LIST_KEYS:
        value = obj[key]
        if not isinstance(value, list):
            raise ValueError(
                f"lens {key!r} must be a JSON array of claims, "
                f"got {type(value).__name__}: {value!r}"
            )
        out[key] = [str(item) for item in value]
    return out
