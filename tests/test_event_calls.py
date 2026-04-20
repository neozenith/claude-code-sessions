"""Tests for the event_calls raw-fact-table extraction."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.cache import CacheManager
from claude_code_sessions.database.sqlite.calls import (
    _is_env_assignment,
    _parse_cli_heads,
    _parse_make_targets,
    extract_calls,
)


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


class TestEnvAssignment:
    @pytest.mark.parametrize("token", ["FOO=bar", "FOO_BAR=value", "_x=1", "A=B=C"])
    def test_is_env_assignment(self, token: str) -> None:
        assert _is_env_assignment(token)

    @pytest.mark.parametrize("token", ["", "=bar", "1FOO=bar", "-foo=bar", "foo", "foo/bar"])
    def test_is_not_env_assignment(self, token: str) -> None:
        assert not _is_env_assignment(token)


class TestParseCliHeads:
    def test_empty_returns_empty(self) -> None:
        assert _parse_cli_heads("") == []

    def test_simple(self) -> None:
        assert _parse_cli_heads("gh pr view 42") == ["gh"]

    def test_pipe_chain(self) -> None:
        assert _parse_cli_heads("aws s3 ls | grep foo | wc -l") == ["aws", "grep", "wc"]

    def test_and_chain(self) -> None:
        assert _parse_cli_heads("make install && uv run pytest") == ["make", "uv"]

    def test_semicolon_chain(self) -> None:
        assert _parse_cli_heads("date; uptime; whoami") == ["date", "uptime", "whoami"]

    def test_or_chain(self) -> None:
        assert _parse_cli_heads("ls missing || echo not-found") == ["ls", "echo"]

    def test_absolute_path_becomes_basename(self) -> None:
        assert _parse_cli_heads("/usr/bin/duckdb :memory:") == ["duckdb"]

    def test_skips_env_assignments(self) -> None:
        assert _parse_cli_heads("FOO=bar BAZ=qux make test") == ["make"]

    def test_unwraps_sudo(self) -> None:
        assert _parse_cli_heads("sudo -E apt-get install curl") == ["apt-get"]

    def test_unwraps_xargs(self) -> None:
        assert _parse_cli_heads("ls | xargs -n1 rm") == ["ls", "rm"]

    def test_unwraps_env(self) -> None:
        # The typical shape is ``env KEY=VAL cmd``. Flag-with-argument
        # variants like ``env -u VAR cmd`` aren't unwrapped — generically
        # deciding which flags consume a positional is out of scope here.
        assert _parse_cli_heads("env FOO=bar python script.py") == ["python"]

    def test_detects_common_data_clis(self) -> None:
        heads = _parse_cli_heads(
            "duckdb -c 'select 1' && sqlite3 test.db '.schema' "
            "&& aws s3 ls && gcloud auth list && gh pr view 1"
        )
        assert heads == ["duckdb", "sqlite3", "aws", "gcloud", "gh"]

    def test_strips_trailing_paren(self) -> None:
        # Subshell syntax: "(cd /tmp && ls)" — the "(cd" token's leading paren
        # is stripped, leaving "cd" as the head of the first segment.
        assert _parse_cli_heads("(cd /tmp && ls)") == ["cd", "ls"]

    def test_rejects_bash_for_loop_control_tokens(self) -> None:
        # `for i in 1 2 3; do echo $i; done` — split on `;` gives three
        # segments, none of which should produce a CLI row:
        #   - `for i in 1 2 3`  → loop header, no command
        #   - ` do echo $i`     → unwrap `do`, real command is `echo`
        #   - ` done`           → terminator, no command
        assert _parse_cli_heads("for i in 1 2 3; do echo $i; done") == ["echo"]

    def test_rejects_bash_while_loop_control_tokens(self) -> None:
        # `while true; do sleep 1; done` — `while` unwraps to `true`.
        assert _parse_cli_heads("while true; do sleep 1; done") == [
            "true", "sleep",
        ]

    def test_rejects_bash_if_statement_tokens(self) -> None:
        # `if grep -q foo; then cat bar; else cat baz; fi`
        # - segment 1 (`if grep -q foo`)    → `if` unwraps → `grep`
        # - segment 2 (` then cat bar`)     → `then` unwraps → `cat`
        # - segment 3 (` else cat baz`)     → `else` unwraps → `cat`
        # - segment 4 (` fi`)               → terminator, rejected
        assert _parse_cli_heads("if grep -q foo; then cat bar; else cat baz; fi") == [
            "grep", "cat", "cat",
        ]

    def test_rejects_pure_punctuation_head(self) -> None:
        # A bare double-quote surviving as its own token (sometimes
        # happens with heredoc-style or `sh -c "..."` inputs) is not a
        # real command and should be dropped.
        assert _parse_cli_heads('" | cat') == ["cat"]

    def test_rejects_semicolon_only_head(self) -> None:
        # Shouldn't happen naturally — we split on `;` — but belt-and-
        # braces: any pure-punctuation head is rejected.
        assert _parse_cli_heads("; cat") == ["cat"]


class TestParseMakeTargets:
    def test_single_target(self) -> None:
        assert _parse_make_targets(["test"]) == ["test"]

    def test_multiple_targets(self) -> None:
        assert _parse_make_targets(["test", "lint", "format"]) == [
            "test", "lint", "format",
        ]

    def test_skips_flag_with_arg(self) -> None:
        # -C consumes the next token; the real target is after.
        assert _parse_make_targets(["-C", "subproj", "test"]) == ["test"]

    def test_skips_short_flag_without_arg(self) -> None:
        assert _parse_make_targets(["-s", "test"]) == ["test"]

    def test_skips_long_flag(self) -> None:
        assert _parse_make_targets(["--directory=subproj", "build"]) == ["build"]

    def test_skips_env_override(self) -> None:
        assert _parse_make_targets(["CI=true", "ci"]) == ["ci"]

    def test_skips_env_and_flag_mixed(self) -> None:
        assert _parse_make_targets(["CI=true", "-j", "4", "test", "lint"]) == [
            "test", "lint",
        ]

    def test_no_positionals_returns_empty(self) -> None:
        assert _parse_make_targets([]) == []
        assert _parse_make_targets(["-s"]) == []

    def test_skips_shell_redirection_tokens(self) -> None:
        # `make test 2>&1 | tee log` → after segment-split on `|`, the
        # leftmost segment's tokens after `make` are ['test', '2>&1'].
        # `2>&1` is not a target.
        assert _parse_make_targets(["test", "2>&1"]) == ["test"]

    def test_skips_background_operator(self) -> None:
        # `make test &` → after tokenization, rest=['test', '&'].
        assert _parse_make_targets(["test", "&"]) == ["test"]

    def test_skips_redirection_with_filename(self) -> None:
        # `make test >log` → rest=['test', '>log'].
        assert _parse_make_targets(["test", ">log"]) == ["test"]


# ---------------------------------------------------------------------------
# extract_calls() — the top-level signal extractor
# ---------------------------------------------------------------------------


def _assistant_event(content: list[dict]) -> dict:
    """Build a minimal assistant event carrying the given content blocks."""
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def _user_event(content: object) -> dict:
    """Build a minimal user event."""
    return {"type": "user", "message": {"role": "user", "content": content}}


class TestExtractCalls:
    def test_no_content_returns_empty(self) -> None:
        assert extract_calls({"type": "user"}) == []
        assert extract_calls({"type": "assistant", "message": {"role": "assistant"}}) == []

    def test_plain_text_assistant_has_no_calls(self) -> None:
        ev = _assistant_event([{"type": "text", "text": "hello world"}])
        assert extract_calls(ev) == []

    def test_single_tool_use(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}},
        ])
        assert extract_calls(ev) == [(0, "tool", "Read")]

    def test_parallel_tool_uses_preserve_order(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Grep", "input": {}},
            {"type": "tool_use", "name": "Glob", "input": {}},
        ])
        assert extract_calls(ev) == [
            (0, "tool", "Read"),
            (1, "tool", "Grep"),
            (2, "tool", "Glob"),
        ]

    def test_skill_invocation(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Skill", "input": {"skill": "introspect"}},
        ])
        assert extract_calls(ev) == [(0, "skill", "introspect")]

    def test_skill_without_input_falls_back_to_tool_row(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Skill", "input": {}},
        ])
        assert extract_calls(ev) == [(0, "tool", "Skill")]

    def test_agent_invocation(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Agent",
             "input": {"subagent_type": "feature-dev:code-explorer", "prompt": "..."}},
        ])
        assert extract_calls(ev) == [(0, "subagent", "feature-dev:code-explorer")]

    def test_agent_without_type_falls_back_to_tool_row(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Agent", "input": {"prompt": "..."}},
        ])
        assert extract_calls(ev) == [(0, "tool", "Agent")]

    def test_bash_emits_tool_and_cli_rows(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Bash",
             "input": {"command": "gh pr view 42 && make test"}},
        ])
        # `make test` additionally emits a make_target row beyond the
        # 'cli' row — see _parse_make_targets tests below.
        assert extract_calls(ev) == [
            (0, "tool", "Bash"),
            (0, "cli", "gh"),
            (0, "cli", "make"),
            (0, "make_target", "test"),
        ]

    def test_bash_with_no_command_string_emits_only_tool_row(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Bash", "input": {"command": None}},
        ])
        assert extract_calls(ev) == [(0, "tool", "Bash")]

    def test_rule_extraction_from_user_text(self) -> None:
        text = (
            "<system-reminder>\n"
            "Contents of /Users/foo/.claude/rules/python/RULES.md:\n"
            "Some rule body.\n"
            "</system-reminder>\n"
            "Some unrelated text.\n"
            "<system-reminder>\n"
            "Contents of /Users/foo/project/CLAUDE.md: project rules.\n"
            "</system-reminder>"
        )
        ev = _user_event([{"type": "text", "text": text}])
        assert extract_calls(ev) == [
            (0, "rule", "/Users/foo/.claude/rules/python/RULES.md"),
            (0, "rule", "/Users/foo/project/CLAUDE.md"),
        ]

    def test_rule_paths_only_counted_inside_system_reminder(self) -> None:
        # A "Contents of" that is NOT inside a <system-reminder> block must be
        # ignored — otherwise every file listing in chat would inflate the
        # rule counter.
        ev = _user_event([{"type": "text",
                           "text": "Contents of /Users/foo/plain.md is here."}])
        assert extract_calls(ev) == []

    def test_make_with_flags_and_multiple_targets(self) -> None:
        ev = _assistant_event([
            {"type": "tool_use", "name": "Bash",
             "input": {"command": "make -C subproj -j 4 CI=true test lint"}},
        ])
        assert extract_calls(ev) == [
            (0, "tool", "Bash"),
            (0, "cli", "make"),
            (0, "make_target", "test"),
            (0, "make_target", "lint"),
        ]

    def test_make_bare_emits_no_targets(self) -> None:
        # `make` with no positional target → cli='make' row only, no
        # make_target rows (default target isn't something we can
        # determine without parsing the Makefile).
        ev = _assistant_event([
            {"type": "tool_use", "name": "Bash", "input": {"command": "make"}},
        ])
        assert extract_calls(ev) == [
            (0, "tool", "Bash"),
            (0, "cli", "make"),
        ]

    def test_mixed_assistant_content(self) -> None:
        ev = _assistant_event([
            {"type": "text", "text": "thinking out loud"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "uv run test"}},
            {"type": "tool_use", "name": "Skill", "input": {"skill": "mdtoc"}},
        ])
        assert extract_calls(ev) == [
            (1, "tool", "Bash"),
            (1, "cli", "uv"),
            (2, "skill", "mdtoc"),
        ]


# ---------------------------------------------------------------------------
# End-to-end ingest → event_calls rows
# ---------------------------------------------------------------------------


@pytest.fixture
def cache(tmp_path: Path) -> CacheManager:
    """Real CacheManager backed by a throwaway SQLite file."""
    c = CacheManager(db_path=tmp_path / "cache.db")
    c.init_schema()
    return c


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def test_ingest_populates_event_calls(tmp_path: Path, cache: CacheManager) -> None:
    """ingest_file() fans every content-block signal into event_calls."""
    session_id = "session-xyz"
    project_id = "-Users-foo-bar"

    events = [
        # Assistant with Bash + parallel Read.
        {
            "type": "assistant",
            "uuid": "u1",
            "parentUuid": None,
            "timestamp": "2026-01-01T00:00:00Z",
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "content": [
                    {"type": "tool_use", "name": "Bash",
                     "input": {"command": "gh pr view 7 | cat"}},
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "/tmp/x"}},
                ],
            },
        },
        # Assistant Skill + Agent launch.
        {
            "type": "assistant",
            "uuid": "u2",
            "parentUuid": "u1",
            "timestamp": "2026-01-01T00:00:01Z",
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "content": [
                    {"type": "tool_use", "name": "Skill",
                     "input": {"skill": "introspect"}},
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": "Explore", "prompt": "..."}},
                ],
            },
        },
        # User event with a rule injection.
        {
            "type": "user",
            "uuid": "u3",
            "parentUuid": "u2",
            "timestamp": "2026-01-01T00:00:02Z",
            "sessionId": session_id,
            "message": {
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": "<system-reminder>Contents of /Users/foo/.claude/rules/python/RULES.md:"
                             " rules.</system-reminder>"},
                ],
            },
        },
    ]

    jsonl_path = tmp_path / "projects" / project_id / f"{session_id}.jsonl"
    _write_jsonl(jsonl_path, events)

    stat = os.stat(jsonl_path)
    cache.ingest_file({
        "filepath": str(jsonl_path),
        "project_id": project_id,
        "session_id": session_id,
        "file_type": "main_session",
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
    })

    rows = cache.conn.execute(
        """
        SELECT call_type, call_name, ord, session_id, project_id
        FROM event_calls
        ORDER BY id
        """
    ).fetchall()
    tuples = [(r["call_type"], r["call_name"], r["ord"]) for r in rows]

    assert tuples == [
        ("tool", "Bash", 0),
        ("cli", "gh", 0),
        ("cli", "cat", 0),
        ("tool", "Read", 1),
        ("skill", "introspect", 0),
        ("subagent", "Explore", 1),
        ("rule", "/Users/foo/.claude/rules/python/RULES.md", 0),
    ]

    # Denormalized columns populated.
    for r in rows:
        assert r["session_id"] == session_id
        assert r["project_id"] == project_id


def test_ingest_populates_make_targets(tmp_path: Path, cache: CacheManager) -> None:
    """A Bash command invoking make should produce one row per target."""
    session_id = "session-mk"
    project_id = "-Users-foo-bar"
    jsonl_path = tmp_path / "projects" / project_id / f"{session_id}.jsonl"
    ev = {
        "type": "assistant",
        "uuid": "u1",
        "parentUuid": None,
        "timestamp": "2026-01-01T00:00:00Z",
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-5-20250929",
            "content": [
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "make -C subproj test lint"}},
            ],
        },
    }
    _write_jsonl(jsonl_path, [ev])
    stat = os.stat(jsonl_path)
    cache.ingest_file({
        "filepath": str(jsonl_path),
        "project_id": project_id,
        "session_id": session_id,
        "file_type": "main_session",
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
    })

    rows = cache.conn.execute(
        "SELECT call_type, call_name FROM event_calls ORDER BY id"
    ).fetchall()
    assert [(r["call_type"], r["call_name"]) for r in rows] == [
        ("tool", "Bash"),
        ("cli", "make"),
        ("make_target", "test"),
        ("make_target", "lint"),
    ]


def test_reingest_replaces_event_calls(tmp_path: Path, cache: CacheManager) -> None:
    """Re-ingesting the same file should not duplicate fact-table rows."""
    session_id = "session-xyz"
    project_id = "-Users-foo-bar"
    jsonl_path = tmp_path / "projects" / project_id / f"{session_id}.jsonl"

    ev = {
        "type": "assistant",
        "uuid": "u1",
        "parentUuid": None,
        "timestamp": "2026-01-01T00:00:00Z",
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-5-20250929",
            "content": [
                {"type": "tool_use", "name": "Grep", "input": {"pattern": "x"}},
            ],
        },
    }
    _write_jsonl(jsonl_path, [ev])
    stat = os.stat(jsonl_path)
    file_info = {
        "filepath": str(jsonl_path),
        "project_id": project_id,
        "session_id": session_id,
        "file_type": "main_session",
        "mtime": stat.st_mtime,
        "size_bytes": stat.st_size,
    }

    cache.ingest_file(dict(file_info))
    cache.ingest_file(dict(file_info))  # second time

    count = cache.conn.execute("SELECT COUNT(*) FROM event_calls").fetchone()[0]
    assert count == 1, "re-ingest must not duplicate event_calls rows"
