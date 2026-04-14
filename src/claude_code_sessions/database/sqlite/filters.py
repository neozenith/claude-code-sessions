"""
SQL filter clause builders for the SQLite backend.
"""

from __future__ import annotations

from pathlib import Path

from claude_code_sessions.config import BLOCKED_DOMAINS, is_project_blocked


def days_clause(days: int | None, col: str = "e.timestamp") -> str:
    """Build an AND clause for day filtering. Empty string when no filter."""
    if not days or days <= 0:
        return ""
    return f"AND {col} >= datetime('now', '-{days} days')"


def project_clause(project: str | None, col: str = "e.project_id") -> str:
    """Build an AND clause for project filtering. Empty string when no filter."""
    if not project:
        return ""
    safe = project.replace("'", "''")
    return f"AND {col} = '{safe}'"


def domain_blocked_ids(projects_path: Path) -> set[str]:
    """Return project_ids that belong to blocked domains."""
    if not BLOCKED_DOMAINS:
        return set()
    blocked: set[str] = set()
    if not projects_path.exists():
        return blocked
    for d in projects_path.iterdir():
        if d.is_dir() and is_project_blocked(d.name):
            blocked.add(d.name)
    return blocked


def domain_clause(projects_path: Path, col: str = "e.project_id") -> str:
    """Build SQL AND clauses to exclude blocked domains."""
    blocked_ids = domain_blocked_ids(projects_path)
    if not blocked_ids:
        return ""
    placeholders = ", ".join(f"'{pid.replace(chr(39), chr(39)+chr(39))}'" for pid in blocked_ids)
    return f"AND {col} NOT IN ({placeholders})"
