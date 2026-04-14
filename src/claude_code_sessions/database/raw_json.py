"""
On-demand raw JSON fetch from JSONL source files.

The SQLite cache used to store a duplicate copy of every event's raw JSON
in `events.raw_json` — this cost over 2 GB. The canonical source of the raw
payload is the JSONL file on disk. This module looks up a specific event
by its (filepath, line_number) coordinate and returns the raw line.

Both database backends use this via `get_event_raw_json()`.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def read_jsonl_line(filepath: Path, line_number: int) -> str | None:
    """Return the content of ``line_number`` in ``filepath``, or None.

    Line numbers are 1-based to match the convention used during ingestion
    (``enumerate(f, start=1)``). Returns None if the file is missing, the
    line is out of range, or the file can't be read.
    """
    if line_number < 1 or not filepath.exists():
        return None

    try:
        with filepath.open(encoding="utf-8") as f:
            for current, line in enumerate(f, start=1):
                if current == line_number:
                    # Strip only trailing newline; preserve any content
                    return line.rstrip("\n").rstrip("\r")
        return None  # line_number beyond end of file
    except OSError as exc:
        log.warning("Could not read %s:%d — %s", filepath, line_number, exc)
        return None
