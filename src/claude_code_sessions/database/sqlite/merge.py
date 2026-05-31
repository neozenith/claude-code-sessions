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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    # Only needed for the merge() annotation. Importing at runtime would create
    # a cycle: summaries.py imports get_merger/Summary from this module.
    from claude_code_sessions.database.sqlite.summaries import SummaryEngine

__all__ = [
    "MERGER_REGISTRY",
    "ChildMode",
    "SourceExcerpts",
    "Summary",
    "SummaryMerger",
    "get_merger",
    "register_merger",
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
