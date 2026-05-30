# G1: Response-level token accounting

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 1 of 8
>
> **Depends on:** none  ·  **Blocks:** [G2](./tokenometrics-G2.md), [G3](./tokenometrics-G3.md), [G4](./tokenometrics-G4.md), [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** « _(first)_  ·  [G2 »](./tokenometrics-G2.md)

**Current:** Each response's content-block events duplicate request-level usage; `rebuild_aggregates` and `agg` `SUM()` them, inflating every token + cost total ~2.4×.

**Gap:** Introduce the `requestId` as the unit of a response. In a per-file post-pass, mark exactly one **head** event per `requestId` and **zero the duplicated token/cost columns on non-heads**, so every existing `SUM()` becomes correct without query rewrites. Bump `SCHEMA_VERSION` to force a full reingest.

**Output(s):**
- `src/claude_code_sessions/database/sqlite/schema.py` (Python/SQL): `SCHEMA_VERSION "13"→"14"`; add `events.request_id TEXT`, `events.stop_reason TEXT`, `events.is_response_head INTEGER DEFAULT 1`; index `idx_events_request_id`.
- `src/claude_code_sessions/database/sqlite/cache.py` (Python): extract `requestId`/`stop_reason` in `_parse_event`; new `_annotate_responses(events_data)` called at end of `_parse_file`; extend the `INSERT INTO events` column list/tuple in `_write_parsed`.
- `tests/test_response_dedup.py` (Python).

**References:**
```python
# cache.py — new post-pass over the ALREADY-ORDERED per-file event list.
# Heads keep usage; non-heads are zeroed so every downstream SUM() is correct.
_USAGE_COLS = ("input_tokens","output_tokens","cache_read_tokens",
               "cache_creation_tokens","cache_5m_tokens",
               "billable_tokens","total_cost_usd","context_tokens")

def _annotate_responses(self, events: list[dict]) -> None:
    # Group consecutive assistant events sharing a requestId.
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, e in enumerate(events):
        rid = e.get("request_id")
        if e["event_type"] != "assistant" or rid is None:
            e["is_response_head"] = 1            # its own head (synthetic/non-assistant)
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
        # response duration: triggering event (preceding) → last block
        start = events[idxs[0] - 1]["timestamp"] if idxs[0] > 0 else events[idxs[0]]["timestamp"]
        events[head]["response_duration_ms"] = _delta_ms(start, events[head]["timestamp"])
```

## ADR: Cost-correction scope
| Option | Pros | Cons |
|--------|------|------|
| Fix everywhere (zero non-heads) | All totals/costs accurate, no query rewrites | Historical figures drop ~2.4×; per-event display shows 0 on continuation blocks |
| New metrics only | No change to existing dashboards | Dashboards stay knowingly wrong; two number systems diverge |
| Fix + keep raw columns | Accurate totals + display fidelity | Widest schema change, more query edits |

**Decision:** Fix everywhere (zero non-heads).
**Rationale:** User chose accuracy over preserving inflated historicals; zeroing keeps every existing `SUM()` correct with no query changes (fail-loud over silent inaccuracy).

## ADR: Response head selection & duration start
| Option | Pros | Cons |
|--------|------|------|
| Head = last block; duration from preceding event ts | Last block has `stop_reason`+final ts; duration = end-to-end (incl. TTFT) | Includes queue/tool latency before first token |
| Head = first block; duration = last−first block ts | Excludes pre-first-token latency | First block lacks final stop_reason; misses TTFT |

**Decision:** Head = last block; `response_duration_ms` = last-block ts − triggering (preceding) event ts, falling back to first-block ts when there is no preceding event.
**Rationale:** Matches "duration of the assistant response" as the user experiences it (request sent → response complete); the head is the natural carrier of stop_reason and final usage.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T1.1](./tokenometrics-G1-T1.1.md) | An operator can see a multi-block response counted once in session totals | none |
| [T1.2](./tokenometrics-G1-T1.2.md) | An operator can see exactly one response-head per requestId | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T1.3](./tokenometrics-G1-T1.3.md) | A single-block response is its own head with usage intact | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T1.4](./tokenometrics-G1-T1.4.md) | A synthetic assistant event (no requestId) is its own head | [T1.1](./tokenometrics-G1-T1.1.md) |

