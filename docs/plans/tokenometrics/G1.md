# G1: Response-level token accounting

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** none
> - **Blocks:** [G2](./tokenometrics-G2.md), [G3](./tokenometrics-G3.md), [G4](./tokenometrics-G4.md), [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
> - **Next:** [G2](./tokenometrics-G2.md)

Count each response once: mark one **head** per `requestId` and zero the duplicated usage on non-heads, so every existing `SUM()` is correct with no query rewrites.

## Context

Each response's content-block events repeat the same request-level usage,
and `rebuild_aggregates` + `agg` `SUM()` them with no dedup —
inflating every token and cost total ~2.4×.
A `SCHEMA_VERSION` bump (→14) forces the one-time reingest.

## Outputs

| File | Change |
|------|--------|
| `database/sqlite/schema.py` | `SCHEMA_VERSION`→14; add `request_id`, `stop_reason`, `is_response_head` + `idx_events_request_id` |
| `database/sqlite/cache.py` | extract `requestId`/`stop_reason` in `_parse_event`; `_annotate_responses` at end of `_parse_file`; widen `INSERT` in `_write_parsed` |
| `tests/test_response_dedup.py` | dedup correctness |

## Key logic

```python
# cache.py — post-pass over the ALREADY-ORDERED per-file event list.
# Heads keep usage; non-heads are zeroed so every downstream SUM() is correct.
_USAGE_COLS = ("input_tokens","output_tokens","cache_read_tokens",
               "cache_creation_tokens","cache_5m_tokens",
               "billable_tokens","total_cost_usd","context_tokens")

def _annotate_responses(self, events: list[dict]) -> None:
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, e in enumerate(events):
        rid = e.get("request_id")
        if e["event_type"] != "assistant" or rid is None:
            e["is_response_head"] = 1            # synthetic/non-assistant → own head
            continue
        if rid not in groups:
            groups[rid] = []; order.append(rid)
        groups[rid].append(i)
    for rid in order:
        idxs = groups[rid]
        head = idxs[-1]                          # last block carries stop_reason + final ts
        for j in idxs:
            events[j]["is_response_head"] = 1 if j == head else 0
            if j != head:
                for c in _USAGE_COLS:
                    events[j][c] = 0
        start = events[idxs[0] - 1]["timestamp"] if idxs[0] > 0 else events[idxs[0]]["timestamp"]
        events[head]["response_duration_ms"] = _delta_ms(start, events[head]["timestamp"])
```

## ADR1.1: Fix the over-count everywhere

- **Decision:** zero the duplicated usage on non-head events so every existing `SUM()` stays correct.
- **Why:** accuracy over preserving inflated historicals, with no query rewrites (fail-loud).
- **Rejected:** new-metrics-only (dashboards stay knowingly wrong); fix + raw columns (widest schema change).

## ADR1.2: Last block is the response head

- **Decision:** use the **last** block as the head, and set `response_duration_ms` = last-block ts − preceding-event ts (fallback: first-block ts).
- **Why:** the last block carries `stop_reason` and final usage; end-to-end timing matches the response time the user feels.
- **Rejected:** first-block head (lacks final `stop_reason`, misses TTFT).

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T1.1](./tokenometrics-G1-T1.1.md) | An operator can see a multi-block response counted once in session totals | — |
| [T1.2](./tokenometrics-G1-T1.2.md) | An operator can see exactly one response-head per requestId | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T1.3](./tokenometrics-G1-T1.3.md) | A single-block response is its own head with usage intact | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T1.4](./tokenometrics-G1-T1.4.md) | A synthetic assistant event (no requestId) is its own head | [T1.1](./tokenometrics-G1-T1.1.md) |
