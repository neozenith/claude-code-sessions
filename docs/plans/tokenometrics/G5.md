# G5: Turn timing (idle / active)

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G4](./tokenometrics-G4.md)
> - **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
> - **Prev:** [G4](./tokenometrics-G4.md)
> - **Next:** [G6](./tokenometrics-G6.md)

Decompose each session's main thread into active (human → assistant turn-end) and idle (turn-end → next human) spans, and flag implausibly fast human replies.

## Context

No call-and-response timing exists.
Idle and active spans come from a `LEAD()` window over main-thread events ordered by timestamp;
per-session totals roll up in `rebuild_aggregates`.

## Outputs

| File | Change |
|------|--------|
| `schema.py` | `sessions`: `total_active_ms`, `total_idle_ms`, `total_response_ms`, `total_response_output_tokens`, `avg_tps`, `peak_context_ratio`; `idx_events_session_ts` |
| `cache.py` | `_compute_session_timing()` inside `rebuild_aggregates` |
| `backend.py` | `get_session_metrics(project_id, session_id)` per-turn + `too_fast` |
| `database/protocol.py` | add `get_session_metrics` |
| `tests/test_session_timing.py` | idle / active / too-fast |

## Key logic

```sql
-- Idle = gap from an assistant turn-end (stop_reason='end_turn', is_response_head=1)
-- to the next human event, ordered by timestamp within the main session.
SELECT e.uuid, e.msg_kind, e.timestamp,
       LEAD(e.timestamp) OVER (PARTITION BY e.session_id ORDER BY e.timestamp) AS next_ts
FROM events e
WHERE e.session_id = :sid AND e.is_sidechain = 0
ORDER BY e.timestamp;
-- too_fast: idle_seconds < (turn_output_tokens / READ_TOKENS_PER_SEC)
```

## ADR5.1: Too-fast flag at an 8 tok/s skim bar

- **Decision:** idle boundary = an `end_turn` head → next `human` event (main thread only); flag `too_fast` when `idle_seconds < output_tokens / READ_TOKENS_PER_SEC` **and** `output_tokens >= 200`, with `READ_TOKENS_PER_SEC = 8` (~480 wpm fast-skim) configurable in `pricing.py`.
- **Why:** a fast-skim bar fires only when the reply was impossible to have read; the 200-token floor avoids flagging instant replies to short outputs.
- **Source:** WPM ranges — [Words per minute](https://en.wikipedia.org/wiki/Words_per_minute) (228±30 read-aloud, ~184 silent, 180 monitor proofreading).

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T5.1](./tokenometrics-G5-T5.1.md) | An operator sees idle time between assistant stop and next prompt | [T4.1](./tokenometrics-G4-T4.1.md) |
| [T5.2](./tokenometrics-G5-T5.2.md) | An operator sees active (working) time per turn | [T5.1](./tokenometrics-G5-T5.1.md) |
| [T5.3](./tokenometrics-G5-T5.3.md) | A reviewer sees a 'too-fast' flag only for implausibly quick replies | [T5.1](./tokenometrics-G5-T5.1.md) |
| [T5.4](./tokenometrics-G5-T5.4.md) | Machine latency is not counted as human idle | [T5.1](./tokenometrics-G5-T5.1.md) |
