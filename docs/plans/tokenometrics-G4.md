# G4: Response performance (TPS)

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 4 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md)  ·  **Blocks:** [G5](./tokenometrics-G5.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** [« G3](./tokenometrics-G3.md)  ·  [G5 »](./tokenometrics-G5.md)

**Current:** No response duration or throughput metric. No `durationMs` on assistant events.

**Gap:** Stamp `response_duration_ms` on each response head (G1 post-pass) and expose TPS = head `output_tokens` ÷ (`response_duration_ms`/1000).

**Output(s):**
- `schema.py`: `events.response_duration_ms INTEGER`.
- `cache.py:_annotate_responses`: duration computation (see G1 reference).
- `backend.py`: derive `tps` per response head in `get_session_events`.
- `tests/test_session_timing.py` (shared with G5).

**References:**
```python
def _delta_ms(start_iso: str | None, end_iso: str | None) -> int | None:
    if not start_iso or not end_iso: return None
    from datetime import datetime
    d = (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).total_seconds() * 1000
    return int(d) if d >= 0 else None
# tps = output_tokens / (response_duration_ms/1000) when duration_ms > 0 else None
```

## ADR: TPS definition
**Decision:** TPS = deduped response `output_tokens` ÷ response duration (model performance), per response head; session `avg_tps` = Σ output over heads ÷ Σ duration over heads.
**Rationale:** User confirmed TPS should measure model performance over the assistant's own response duration, not wall-clock including idle.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T4.1](./tokenometrics-G4-T4.1.md) | An operator sees a response's tokens/sec | [T1.1](./tokenometrics-G1-T1.1.md) |
| [T4.2](./tokenometrics-G4-T4.2.md) | TPS is absent when duration is unknown | [T4.1](./tokenometrics-G4-T4.1.md) |

