# T8.1: Both ingesters produce identical rows for a shared fixture

> - **Gap:** [G8: Introspect-script parity](./tokenometrics-G8.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)

- [x] **Done**

Ingesting the same JSONL fixture through the backend `CacheManager` and through the introspect script yields identical event rows for the response-accounting, context, subagent-prefix, and duration fields.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_introspect_parity.py::test_backend_and_introspect_agree` — for a shared fixture, the two caches' `get_session_events`-equivalent rows match on `is_response_head`, `output_tokens`, `context_tokens`, `context_window`, `context_ratio`, `msg_kind`, `response_duration_ms`, and both report the **same** `SCHEMA_VERSION` (import the constant; do not hardcode — it is bumped per schema-changing gap, `"15"` after G2) |
| Implements | `.claude/skills/introspect/scripts/introspect_sessions.py` (mirror `CONTEXT_WINDOWS`, `context_ratio`, requestId dedup/head, response duration, `subagent-` prefix, `SCHEMA_VERSION`) |
| Depends on | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T4.1](./tokenometrics-G4-T4.1.md) |
| Refactor | if drift risk is high, note a follow-up to extract the shared parse logic into an importable module (out of scope here; the project deliberately keeps two copies per MEMORY.md) |
