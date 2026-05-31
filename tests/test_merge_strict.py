"""Correctness tests for the strict bottom-up merger (G4).

The merger is exercised through its public ``merge`` with a recording fake
engine (a real class, not a mock) so the assertions are about observable
behaviour: what the synthesised ``Summary`` contains and what text reaches the
engine prompt.
"""

from __future__ import annotations

import json

from claude_code_sessions.database.sqlite.merge import Summary, SummaryMergerStrict


class RecordingEngine:
    """A real ``SummaryEngine`` returning canned text and recording its prompt."""

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def summarise(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
        return self._output


def test_strict_merge_synthesises_children() -> None:
    """Strict merge synthesises one summary from two child summaries; the prompt
    carries the children's lens text and no raw source excerpts."""
    children = [
        Summary("CHILD_A_task", "CHILD_A_pat", "CHILD_A_dec"),
        Summary("CHILD_B_task", "CHILD_B_pat", "CHILD_B_dec"),
    ]
    engine = RecordingEngine(
        json.dumps(
            {"task_summary": "MERGED_task", "patterns": "MERGED_pat", "decisions_values": "MERGED_dec"}
        )
    )

    merger = SummaryMergerStrict()
    assert merger.name == "strict"
    assert merger.child_mode == "child_rollups"
    assert merger.wants_excerpts is False

    result = merger.merge(engine, "model-a", children, None)

    assert isinstance(result, Summary)
    assert result.task_summary == "MERGED_task"
    assert result.patterns == "MERGED_pat"
    assert result.decisions_values == "MERGED_dec"

    assert len(engine.calls) == 1
    prompt = engine.calls[0][1]
    for marker in (
        "CHILD_A_task",
        "CHILD_A_pat",
        "CHILD_A_dec",
        "CHILD_B_task",
        "CHILD_B_pat",
        "CHILD_B_dec",
    ):
        assert marker in prompt
