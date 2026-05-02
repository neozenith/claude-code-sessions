"""Knowledge-graph layer.

Each module here is the equivalent of a sessions_demo phase, freshly
written against the published ``sqlite-muninn`` extension's SQL surface.
There is intentionally NO import from ``benchmarks.sessions_demo`` —
this layer is a sibling implementation that shares only the on-disk
schema contract via ``SCHEMA_VERSION``.
"""

from claude_code_sessions.database.sqlite.kg.pipeline import sync_kg

__all__ = ["sync_kg"]
