"""Tests for the benchmark reference scorer (G10).

``score_summary`` is a deterministic, fully-local ROUGE-L/BLEU/F1 scorer used by
the G10 sweep to screen candidate summaries against the curated gold set. No
model inference — pure token math.
"""

from __future__ import annotations

import pytest

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

    # The lexical metrics stay within [0, 1].
    for scores in (identical, disjoint):
        for key in ("rouge_l", "bleu", "f1"):
            assert 0.0 <= scores[key] <= 1.0


def test_score_summary_locates_on_the_band() -> None:
    """A short summary vs a long source exposes the context fields (CR4): a small
    compression ratio, a ceiling below 1, a normalised score = rouge_l/ceiling,
    and a lead anchor — so the bare lexical value can be located, not guessed."""
    source = "build a hierarchical summariser with pluggable merge strategies " * 20
    summary = "build a hierarchical summariser"
    s = score_summary(summary, source)

    assert 0.0 < s["compression_ratio"] < 0.2  # summary is a few % of the source
    assert 0.0 < s["rouge_l_ceiling"] < 1.0  # ceiling bounded by compression
    # normalised = rouge_l / ceiling — the "% of achievable" headroom; lifts the
    # tiny raw value toward 1 (this summary is ~all subsequence of the source).
    assert s["rouge_l_normalised"] >= s["rouge_l"]  # normalising can only lift it
    assert s["rouge_l_normalised"] == pytest.approx(s["rouge_l"] / s["rouge_l_ceiling"], abs=0.01)
    assert s["lead_combined"] > 0.0  # a verbatim lead extract has real overlap

    # Identical text: full compression (1.0), ceiling 1.0, so normalised == rouge_l.
    same = score_summary("alpha beta gamma", "alpha beta gamma")
    assert same["compression_ratio"] == 1.0
    assert same["rouge_l_normalised"] == 1.0
