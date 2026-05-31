"""Correctness tests for the re-grounding merger (G5).

Re-grounding folds a bounded sample of raw source excerpts into the merge
prompt so higher tiers stay faithful (Ou & Lapata, ACL 2025). Tests drive the
public ``merge`` with a recording fake engine and assert on the prompt.
"""

from __future__ import annotations

import json

from claude_code_sessions.database.sqlite.merge import (
    SourceExcerpts,
    Summary,
    SummaryMergerReGround,
)


class RecordingEngine:
    """A real ``SummaryEngine`` returning canned text and recording its prompt."""

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def summarise(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
        return self._output


def test_reground_includes_excerpts_in_prompt() -> None:
    """Re-ground merge folds the supplied source excerpts into the prompt
    alongside the child summaries."""
    children = [Summary("CT1", "CP1", "CD1"), Summary("CT2", "CP2", "CD2")]
    excerpts = SourceExcerpts(["EXCERPT_MARKER_ONE", "EXCERPT_MARKER_TWO"])
    engine = RecordingEngine(
        json.dumps({"task_summary": "m", "patterns": "m", "decisions_values": "m"})
    )

    merger = SummaryMergerReGround()
    assert merger.name == "reground"
    assert merger.child_mode == "child_rollups"
    assert merger.wants_excerpts is True

    result = merger.merge(engine, "model-a", children, excerpts)

    assert isinstance(result, Summary)
    prompt = engine.calls[0][1]
    assert "CT1" in prompt and "CT2" in prompt  # child summaries present
    assert "EXCERPT_MARKER_ONE" in prompt and "EXCERPT_MARKER_TWO" in prompt  # re-grounded
