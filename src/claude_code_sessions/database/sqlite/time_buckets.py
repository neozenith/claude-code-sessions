"""Shared SQLite time-bucket truncation expressions.

Both the agg-table rebuild (``cache.py``) and the roll-up driver
(``summaries.py``) truncate a timestamp column to a calendar grain. Holding the
SQL in one place means day/week/month semantics can never drift between the two
consumers — a divergence would silently mis-bucket roll-ups relative to the
dashboard aggregates.

``{col}`` is the timestamp column/alias to truncate (e.g. ``"timestamp"`` for the
agg rebuild, ``"e.timestamp"`` for the driver's joined query).
"""

from __future__ import annotations

# Canonical grain → SQLite truncation expression template.
_GRAIN_SQL: dict[str, str] = {
    "hour": "strftime('%Y-%m-%dT%H:00:00', {col})",
    "day": "date({col})",
    "week": "date({col}, 'weekday 0', '-6 days')",
    "month": "strftime('%Y-%m-01', {col})",
}


def bucket_expr(grain: str, col: str = "timestamp") -> str:
    """Return the SQLite expression truncating ``col`` to ``grain``.

    Raises ``ValueError`` on an unknown grain — never falls back to a default
    bucket, which would silently mislabel time series.
    """
    try:
        return _GRAIN_SQL[grain].format(col=col)
    except KeyError:
        raise ValueError(f"Unknown grain {grain!r}. Known grains: {sorted(_GRAIN_SQL)}") from None
