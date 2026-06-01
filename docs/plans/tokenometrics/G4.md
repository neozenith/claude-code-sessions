# G4: Response performance (TPS)

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G1](./tokenometrics-G1.md)
> - **Blocks:** [G5](./tokenometrics-G5.md), [G8](./tokenometrics-G8.md)
> - **Prev:** [G3](./tokenometrics-G3.md)
> - **Next:** [G5](./tokenometrics-G5.md)

Expose per-response throughput: TPS = head `output_tokens` ÷ `response_duration_ms`.

## Context

No response duration or throughput metric exists,
and the JSONL carries no per-assistant `durationMs` (only hook/system events) —
so duration is derived from event timestamps in the G1 post-pass.

## Outputs

| File | Change |
|------|--------|
| `schema.py` | add `events.response_duration_ms INTEGER` |
| `cache.py:_annotate_responses` | duration = last-block ts − triggering-event ts (see G1) |
| `backend.py` | derive `tps` per head in `get_session_events` |
| `tests/test_session_timing.py` | duration + TPS (shared with G5) |

## Key logic

```python
def _delta_ms(start_iso: str | None, end_iso: str | None) -> int | None:
    if not start_iso or not end_iso: return None
    d = (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).total_seconds() * 1000
    return int(d) if d >= 0 else None
# tps = output_tokens / (response_duration_ms / 1000) when duration_ms > 0 else None
```

## ADR4.1: TPS is output ÷ response duration

- **Decision:** TPS = deduped response `output_tokens` ÷ response duration, per head; session `avg_tps` = Σ output ÷ Σ duration over heads.
- **Why:** measures model performance over the assistant's own response time, not wall-clock including idle.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T4.1](./tokenometrics-G4-T4.1.md) | An operator sees a response's tokens/sec | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T4.2](./tokenometrics-G4-T4.2.md) | TPS is absent when duration is unknown | [T4.1](./tokenometrics-G4-T4.1.md) |
