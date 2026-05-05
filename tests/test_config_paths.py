"""Tests for env-overridable cache and projects paths.

The config module reads env vars at import time, so each test reloads
the module after manipulating ``os.environ`` via monkeypatch.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest

from claude_code_sessions import config


def _reload_config(monkeypatch: pytest.MonkeyPatch, **env: str | None) -> ModuleType:
    """Apply env overrides + reload config module so module-level
    constants pick up the new values."""
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.reload(config)


# ---------------------------------------------------------------------------
# CACHE_DIR / CACHE_DB_PATH
# ---------------------------------------------------------------------------


class TestCacheDir:
    def test_default_cache_dir_is_home_claude_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch, CACHE_DIR=None)
        assert cfg.CACHE_DIR == Path.home() / ".claude" / "cache"

    def test_default_cache_db_path_is_cache_dir_plus_filename(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch, CACHE_DIR=None)
        assert cfg.CACHE_DB_PATH == cfg.CACHE_DIR / "introspect_sessions.db"

    def test_env_var_overrides_cache_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom = tmp_path / "custom_cache"
        cfg = _reload_config(monkeypatch, CACHE_DIR=str(custom))
        assert cfg.CACHE_DIR == custom
        assert cfg.CACHE_DB_PATH == custom / "introspect_sessions.db"

    def test_env_var_relative_path_resolves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch, CACHE_DIR="./relative/cache")
        # Relative paths are accepted as-is; resolution is the caller's job
        # (matches how PROJECTS_PATH already behaves).
        assert cfg.CACHE_DIR == Path("./relative/cache")

    def test_schema_module_re_exports_cache_db_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Backwards-compat: the introspect script imports CACHE_DB_PATH
        from the schema module. After moving the source-of-truth to
        config, schema must still re-export the same name so external
        imports don't break."""
        custom = tmp_path / "alt_cache"
        _reload_config(monkeypatch, CACHE_DIR=str(custom))
        from claude_code_sessions.database.sqlite import schema

        importlib.reload(schema)
        assert schema.CACHE_DB_PATH == custom / "introspect_sessions.db"


# ---------------------------------------------------------------------------
# PROJECTS_PATH (already env-overridable, but pin behaviour with a test)
# ---------------------------------------------------------------------------


class TestProjectsPath:
    def test_env_var_overrides_projects_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom = tmp_path / "all-sessions" / "claude" / "projects"
        cfg = _reload_config(monkeypatch, PROJECTS_PATH=str(custom))
        assert cfg.PROJECTS_PATH == custom

    def test_default_projects_path_points_at_repo_local_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch, PROJECTS_PATH=None)
        # Default still resolves to ``<repo>/projects`` for the rsync flow.
        assert cfg.PROJECTS_PATH.name == "projects"

    def test_home_projects_path_is_constant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch)
        assert cfg.HOME_PROJECTS_PATH == Path.home() / ".claude" / "projects"
