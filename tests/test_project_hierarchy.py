"""Tests for variable-depth project hierarchy resolution (G1).

The scope path of a project is its home-relative '/'-joined path, drawn from the
authoritative ``ProjectInfo.project_path`` (sourced from ``sessions-index.json``),
never from dash-splitting the lossy encoded ``project_id``.
"""

from __future__ import annotations

import json
from pathlib import Path

from claude_code_sessions.project_resolver import (
    ProjectResolver,
    ancestor_scopes,
    scope_path_of,
)


def _write_index(projects_dir: Path, project_id: str, project_path: str) -> None:
    """Write a minimal sessions-index.json so the resolver yields ``project_path``.

    The authoritative path lives in ``entries[*].projectPath`` — matching the
    real Claude Code index schema the resolver reads.
    """
    project_dir = projects_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}),
        encoding="utf-8",
    )


def test_scope_path_of_depth1_project(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    pid = "-Users-testuser-play-foo"
    _write_index(projects, pid, "/Users/testuser/play/foo")

    resolver = ProjectResolver(projects)

    assert scope_path_of(resolver, pid) == "play/foo"


def test_ancestor_scopes_depth1_chain(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    pid = "-Users-testuser-play-foo"
    _write_index(projects, pid, "/Users/testuser/play/foo")

    resolver = ProjectResolver(projects)

    assert ancestor_scopes(resolver, pid) == ["", "play", "play/foo"]
