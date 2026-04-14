"""
Pricing and message classification for SQLite event ingestion.

Matches the introspect script's cost computation and message kind classification.
"""

from __future__ import annotations

from typing import Any

PRICING: dict[str, dict[str, float]] = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read_mult": 0.1, "cache_write_mult": 1.25},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read_mult": 0.1, "cache_write_mult": 1.25},
    "haiku": {"input": 1.0, "output": 5.0, "cache_read_mult": 0.1, "cache_write_mult": 1.25},
}


def model_family(model_id: str | None) -> str:
    """Extract model family (opus/sonnet/haiku) from a full model ID string."""
    if model_id is None:
        return "unknown"
    lower = model_id.lower()
    for family in ("opus", "sonnet", "haiku"):
        if family in lower:
            return family
    return "unknown"


def compute_event_costs(
    model_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> tuple[float, float, float]:
    """Return (token_rate, billable_tokens, total_cost_usd) for an event."""
    family = model_family(model_id)
    pricing = PRICING.get(family)
    if pricing is None:
        return 0.0, 0.0, 0.0

    token_rate = pricing["input"]
    output_mult = pricing["output"] / pricing["input"]  # always 5.0
    billable = (
        input_tokens
        + output_tokens * output_mult
        + cache_read_tokens * pricing["cache_read_mult"]
        + cache_creation_tokens * pricing["cache_write_mult"]
    )
    return token_rate, round(billable, 4), round(billable * token_rate / 1_000_000, 8)


def first_content_block_type(content: Any) -> str | None:
    """Return the type of the first content block, or None."""
    if content is None:
        return None
    if isinstance(content, str):
        return "string"
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return content[0].get("type")
    return None


def message_kind(event_type: str, is_meta: bool, content: Any) -> str:
    """Classify an event into one of 9 fine-grained message kinds."""
    fct = first_content_block_type(content)
    if event_type == "user":
        if is_meta:
            return "meta"
        if fct == "string":
            if isinstance(content, str) and content.lstrip().startswith("<task-notification>"):
                return "task_notification"
            return "human"
        if fct == "tool_result":
            return "tool_result"
        return "user_text"
    if event_type == "assistant":
        if fct == "thinking":
            return "thinking"
        if fct == "tool_use":
            return "tool_use"
        return "assistant_text"
    return "other"
