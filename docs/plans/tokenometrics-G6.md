# G6: Query layer & API endpoints

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 6 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md), [G2](./tokenometrics-G2.md), [G3](./tokenometrics-G3.md), [G5](./tokenometrics-G5.md)  ·  **Blocks:** [G7](./tokenometrics-G7.md)
>
> **Nav:** [« G5](./tokenometrics-G5.md)  ·  [G7 »](./tokenometrics-G7.md)

**Current:** Endpoints return only legacy fields; no per-session metrics or performance summary; `Database` Protocol lacks the methods.

**Gap:** Surface new per-event fields, add `get_session_metrics` and `get_performance_summary`, and add `avg_tps`/idle/active/`peak_context_ratio` to sessions lists.

**Output(s):**
- `database/sqlite/backend.py` (Python): extend `get_session_events`, `get_sessions_list`, `get_session_usage`; add `get_session_metrics`, `get_performance_summary`.
- `database/protocol.py` (Python): add the two new methods.
- `src/claude_code_sessions/main.py` (Python): `GET /api/sessions/{projectId}/{sessionId}/metrics`, `GET /api/performance` (honor `days`/`project`).
- `tests/test_kg_cache_stats.py`-style endpoint tests under `tests/`.

## ADR: Performance summary aggregation grain
| Option | Pros | Cons |
|--------|------|------|
| Per-model (TPS, smart-zone buckets, idle/active) | Compares model performance directly | No per-project drilldown |
| Per-model × per-project | Richer drilldown | Larger payload; sparse cells |
| Per-model + global smart-zone histogram | Compact, answers "am I in the zone" | Less granular |

**Decision:** **Per-model aggregation that honors the global `days`/`project` filters**, plus a global smart-zone histogram (counts of response heads per zone). The endpoint returns: `by_model: [{model_id, avg_tps, median_tps, response_count, total_idle_ms, total_active_ms}]` and `zone_histogram: {smart, caution, danger}`.
**Rationale:** Project drilldown comes for free from the existing global filter (`useFilters`), so per-model rows already scope to the selected project without a sparse per-model×project matrix. The global histogram directly answers "am I staying in the smart zone." This matches how every other endpoint in the app consumes `days`/`project`.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T6.1](./tokenometrics-G6-T6.1.md) | A client can fetch per-session turn metrics over HTTP | [T5.1](./tokenometrics-G5-T5.1.md) |
| [T6.2](./tokenometrics-G6-T6.2.md) | A client can fetch the performance summary, scoped by filters | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T5.1](./tokenometrics-G5-T5.1.md) |
| [T6.3](./tokenometrics-G6-T6.3.md) | An operator sees TPS and idle/active in the sessions list | [T5.1](./tokenometrics-G5-T5.1.md) |

