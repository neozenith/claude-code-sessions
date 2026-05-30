# G5: Turn timing (idle / active)

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 5 of 8
>
> **Depends on:** [G4](./tokenometrics-G4.md)  ·  **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** [« G4](./tokenometrics-G4.md)  ·  [G6 »](./tokenometrics-G6.md)

**Current:** No call-and-response timing.

**Gap:** Decompose each session's main thread into active (human → assistant turn-end) and idle (assistant turn-end → next human) spans via a `LEAD()` window query; flag "too-fast" human replies. Roll up per-session totals.

**Output(s):**
- `schema.py`: `sessions.total_active_ms`, `total_idle_ms`, `total_response_ms`, `total_response_output_tokens`, `avg_tps`, `peak_context_ratio`; index `idx_events_session_ts`.
- `cache.py`: `_compute_session_timing()` invoked inside `rebuild_aggregates`.
- `backend.py`: `get_session_metrics(project_id, session_id)` per-turn breakdown + `too_fast`.
- `database/protocol.py`: add `get_session_metrics` to the `Database` Protocol.
- `tests/test_session_timing.py` (Python).

**References:**
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

## ADR: Idle/active boundary & too-fast threshold
Resolved (reading-rate figures corroborated via WebFetch on the WPM literature).

Idle boundary is settled: assistant `end_turn` head → next `human` event, main thread only (`is_sidechain=0`). For the "too-fast" trigger, normal silent reading is ~200–260 wpm (English read-aloud 228±30; monitor proofreading ~180); fast skimming reaches ~400–500 wpm. To flag only replies that were *impossible* to have read, use a generous fast-skim rate as the bar.

**Decision:** `READ_TOKENS_PER_SEC = 8` (≈480 wpm fast-skim, using ~0.75 words/token) as a configurable constant in `pricing.py`. `too_fast = (idle_seconds < response_output_tokens / READ_TOKENS_PER_SEC) AND (response_output_tokens >= TOO_FAST_MIN_TOKENS=200)`.
**Rationale:** A fast-skim bar (well above normal reading) makes the flag conservative — it fires only when the human replied faster than even a skim of a substantial response, matching "there's no way they read all of it." The min-tokens floor prevents flagging instant replies to short outputs. Configurable so the bar can be tuned.

**Citations (verified):** WPM ranges — https://en.wikipedia.org/wiki/Words_per_minute (228±30 read-aloud English; ~184±29 cross-language silent; 180 wpm monitor proofreading).

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T5.1](./tokenometrics-G5-T5.1.md) | An operator sees idle time between assistant stop and next prompt | [T4.1](./tokenometrics-G4-T4.1.md) |
| [T5.2](./tokenometrics-G5-T5.2.md) | An operator sees active (working) time per turn | [T5.1](./tokenometrics-G5-T5.1.md) |
| [T5.3](./tokenometrics-G5-T5.3.md) | A reviewer sees a 'too-fast' flag only for implausibly quick replies | [T5.1](./tokenometrics-G5-T5.1.md) |
| [T5.4](./tokenometrics-G5-T5.4.md) | Machine latency is not counted as human idle | [T5.1](./tokenometrics-G5-T5.1.md) |

