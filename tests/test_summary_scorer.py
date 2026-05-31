"""Tests for the benchmark reference scorer (G10).

``score_summary`` is a deterministic, fully-local ROUGE-L/BLEU/F1 scorer used by
the G10 sweep to screen candidate summaries against the curated gold set. No
model inference — pure token math.
"""

from __future__ import annotations

from claude_code_sessions.database.sqlite.summaries import score_summary


def test_score_summary_known_pair() -> None:
    """Identical text scores 1.0 on every metric; disjoint text scores 0.0."""
    identical = score_summary("the quick brown fox", "the quick brown fox")
    assert identical["rouge_l"] == 1.0
    assert identical["bleu"] == 1.0
    assert identical["f1"] == 1.0

    disjoint = score_summary("alpha beta gamma", "delta epsilon zeta")
    assert disjoint["rouge_l"] == 0.0
    assert disjoint["bleu"] == 0.0
    assert disjoint["f1"] == 0.0

    # Every metric stays within [0, 1].
    for scores in (identical, disjoint):
        for value in scores.values():
            assert 0.0 <= value <= 1.0
