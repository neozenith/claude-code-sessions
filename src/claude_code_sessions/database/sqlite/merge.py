"""SummaryMerger abstraction + registry (G3).

The roll-up driver (:func:`claude_code_sessions.database.sqlite.summaries.roll_up_scopes`)
walks the variable-depth scope trie and, at each node, delegates the actual
synthesis to a :class:`SummaryMerger` selected from :data:`MERGER_REGISTRY` by
its flag value. Three concrete strategies plug into this seam — strict (G4),
reground (G5), flat (G6) — and the G10 benchmark chooses one empirically.

No concrete mergers live here: this module is *only* the interface, the value
types it exchanges, and the fail-loud registry lookup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    # Only needed for the merge() annotation. Importing at runtime would create
    # a cycle: summaries.py imports get_merger/Summary from this module.
    from claude_code_sessions.database.sqlite.summaries import SummaryEngine

__all__ = [
    "MERGER_REGISTRY",
    "ChildMode",
    "ExcerptCandidate",
    "SourceExcerpts",
    "Summary",
    "SummaryMerger",
    "SummaryMergerFlat",
    "SummaryMergerReGround",
    "SummaryMergerStrict",
    "get_merger",
    "register_merger",
    "select_excerpts",
]

# How a merger sources the children of a scope:
#   'child_rollups' — merge the child scopes' rollups (strict, reground)
#   'raw_sessions'  — re-summarise raw descendant session summaries (flat)
ChildMode = Literal["child_rollups", "raw_sessions"]


@dataclass(frozen=True)
class Summary:
    """The three-lens unit exchanged between sessions, mergers, and rollups."""

    task_summary: str
    patterns: str
    decisions_values: str


@dataclass(frozen=True)
class SourceExcerpts:
    """A bounded, deterministic sample of raw source text for re-grounding (G5)."""

    excerpts: list[str]


@dataclass(frozen=True)
class ExcerptCandidate:
    """A raw source excerpt with its activity timestamp, before bounded selection."""

    timestamp: str
    text: str


def select_excerpts(candidates: list[ExcerptCandidate], k: int) -> SourceExcerpts:
    """The top-``k`` excerpts by a fixed total order: recency, then length, then
    text (ADR5.1).

    The fixed order makes selection deterministic — the same candidates always
    yield the same sample — which is what keeps the G10 benchmark reproducible.
    The ``k`` cap bounds prompt size at the largest top-tier scopes.
    """
    ordered = sorted(
        candidates,
        key=lambda c: (c.timestamp, len(c.text), c.text),
        reverse=True,
    )
    return SourceExcerpts([c.text for c in ordered[:k]])


class SummaryMerger(Protocol):
    """Synthesises a parent :class:`Summary` from its children.

    The driver inspects ``child_mode`` to decide what to gather and
    ``wants_excerpts`` to decide whether to supply ``excerpts`` — so the
    strategy-specific choices stay in the implementations, not the driver.
    """

    name: str
    child_mode: ChildMode
    wants_excerpts: bool

    def merge(
        self,
        engine: SummaryEngine,
        model: str,
        children: list[Summary],
        excerpts: SourceExcerpts | None,
    ) -> Summary: ...


MERGER_REGISTRY: dict[str, SummaryMerger] = {}


def register_merger(merger: SummaryMerger) -> None:
    """Register ``merger`` under its ``name`` (the flag value)."""
    MERGER_REGISTRY[merger.name] = merger


def get_merger(name: str) -> SummaryMerger:
    """Return the registered merger for ``name``, or fail loud.

    An unknown flag is a configuration error — never silently fall back to a
    default strategy (that would let the benchmark compare the wrong thing).
    """
    try:
        return MERGER_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown merge strategy {name!r}. Registered strategies: {sorted(MERGER_REGISTRY)}"
        ) from None


# ---------------------------------------------------------------------------
# Concrete mergers
# ---------------------------------------------------------------------------

_MERGE_PROMPT_HEADER = (
    "You are merging several child summaries into ONE higher-level summary across "
    "the same three lenses. Read the child summaries below and reply with a single "
    "JSON object with exactly these keys:\n"
    '  "task_summary": the combined task + ubiquitous language across the children;\n'
    '  "patterns": the architectural patterns used or reused across the children;\n'
    '  "decisions_values": the decisions and values expressed across the children.\n'
)


def _parse_summary(raw: str) -> Summary:
    """Parse the engine's JSON reply into a :class:`Summary` (fail-loud on bad output)."""
    parsed = json.loads(raw)
    return Summary(parsed["task_summary"], parsed["patterns"], parsed["decisions_values"])


def _format_children(children: list[Summary]) -> str:
    blocks = []
    for i, child in enumerate(children, start=1):
        blocks.append(
            f"Child {i}:\n"
            f"- task: {child.task_summary}\n"
            f"- patterns: {child.patterns}\n"
            f"- decisions/values: {child.decisions_values}"
        )
    return "\n\n".join(blocks)


class SummaryMergerStrict:
    """Bottom-up, summaries-only merger (GraphRAG-style) — the cheapest strategy.

    Synthesises a scope's three lenses from its children's summaries alone, with
    no source re-grounding. ``excerpts`` is accepted to satisfy the Protocol but
    ignored — the summary-only contract (ADR3.1; G5 is the re-grounding variant).
    """

    name = "strict"
    child_mode: ChildMode = "child_rollups"
    wants_excerpts = False

    def merge(
        self,
        engine: SummaryEngine,
        model: str,
        children: list[Summary],
        excerpts: SourceExcerpts | None,
    ) -> Summary:
        prompt = _MERGE_PROMPT_HEADER + "\n" + _format_children(children)
        return _parse_summary(engine.summarise(model, prompt))


register_merger(SummaryMergerStrict())


def _format_excerpts(excerpts: SourceExcerpts | None) -> str:
    if excerpts is None or not excerpts.excerpts:
        return ""
    block = "\n".join(f"- {e}" for e in excerpts.excerpts)
    return "\n\nGround your summary in these raw source excerpts:\n" + block


class SummaryMergerReGround:
    """Bottom-up merger that re-grounds in a bounded sample of source excerpts.

    Identical in shape to :class:`SummaryMergerStrict` but folds the driver-
    supplied ``excerpts`` into the prompt so higher tiers stay faithful to the
    underlying prompts rather than drifting across summary-of-summary layers
    (Ou & Lapata, ACL 2025). The most token-heavy strategy — the cost the G10
    benchmark weighs against its fidelity.
    """

    name = "reground"
    child_mode: ChildMode = "child_rollups"
    wants_excerpts = True

    def merge(
        self,
        engine: SummaryEngine,
        model: str,
        children: list[Summary],
        excerpts: SourceExcerpts | None,
    ) -> Summary:
        prompt = _MERGE_PROMPT_HEADER + "\n" + _format_children(children) + _format_excerpts(excerpts)
        return _parse_summary(engine.summarise(model, prompt))


register_merger(SummaryMergerReGround())


class SummaryMergerFlat:
    """Re-summarises a scope's raw descendant session summaries directly, with no
    intermediate child-rollup tier.

    The merge mechanism matches strict (synthesise children, no excerpts); the
    distinction is entirely in the driver: ``child_mode='raw_sessions'`` makes
    it gather every descendant ``session_summaries`` row under the scope rather
    than the child scopes' rollups. Simplest dependency graph, largest top-tier
    prompts — the trade the G10 benchmark quantifies.
    """

    name = "flat"
    child_mode: ChildMode = "raw_sessions"
    wants_excerpts = False

    def merge(
        self,
        engine: SummaryEngine,
        model: str,
        children: list[Summary],
        excerpts: SourceExcerpts | None,
    ) -> Summary:
        prompt = _MERGE_PROMPT_HEADER + "\n" + _format_children(children)
        return _parse_summary(engine.summarise(model, prompt))


register_merger(SummaryMergerFlat())
