"""Tests for the context-window utilization map (G2).

``context_window(model_id)`` resolves a model id to its advertised
context-window size via a curated substring map, returning ``None`` for
unknown / synthetic models. These are pure-function unit tests — no cache,
no fixtures.
"""

from __future__ import annotations

import pytest

from claude_code_sessions.database.sqlite.pricing import CONTEXT_WINDOWS, context_window


@pytest.mark.parametrize(
    "model_id",
    [
        "claude-opus-4-7-20260115",
        "claude-opus-4-6-20251101",
        "claude-opus-4-8",
        "claude-sonnet-4-6-20251201",
    ],
)
def test_window_1m_models(model_id: str) -> None:
    """The 1M-window models (opus 4.6/4.7/4.8, sonnet 4.6) resolve to 1_000_000."""
    assert context_window(model_id) == 1_000_000


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-opus-4-5-20250805", 200_000),
        ("claude-sonnet-4-5-20250929", 200_000),
        ("claude-haiku-4-5-20251001", 200_000),
        ("<synthetic>", None),
        ("", None),
        (None, None),
        ("gpt-4o", None),
        ("model.gguf", None),
    ],
)
def test_window_200k_and_unknown(model_id: str | None, expected: int | None) -> None:
    """Standard 200k models resolve to 200_000; synthetic / empty / unrecognized
    ids resolve to None (window — and therefore ratio — undefined)."""
    assert context_window(model_id) == expected


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("qwen2.5-coder-7b-instruct", 32_768),
        ("devstral-small-2505", 256_000),
    ],
)
def test_window_local_models(model_id: str, expected: int) -> None:
    """Curated local-model windows (native defaults): qwen2.5-coder 32k,
    devstral-small 256k. Required by the G2 success measure."""
    assert context_window(model_id) == expected


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-sonnet-4-5-20250929", 200_000),
    ],
)
def test_window_real_ids_resolve(model_id: str, expected: int) -> None:
    """The real curated ids resolve to their windows (regression guard)."""
    assert context_window(model_id) == expected


def test_window_longest_key_first_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """When one window key is a superstring of another (the spec's hypothetical
    ``opus-4-50`` vs existing ``opus-4-5``), the longer, more specific key must
    win. With naive insertion-order iteration the shorter ``opus-4-5`` (200k)
    shadows it; longest-key-first resolves it correctly.

    Uses a real injected map entry (not a mock) so the collision actually
    exists at lookup time, then tears it down automatically."""
    monkeypatch.setitem(CONTEXT_WINDOWS, "opus-4-50", 2_000_000)
    assert context_window("claude-opus-4-50-20270101") == 2_000_000
