# T8.1: Both ingesters produce identical rows for a shared fixture

> **[« G8: Introspect-script parity](./tokenometrics-G8.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 1 in G8
>
> **Nav:** « _(first)_  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN → REFACTOR
- **Behavior:** Ingesting the same JSONL fixture through the backend `CacheManager` and through the introspect script yields identical event rows for the response-accounting, context, subagent-prefix, and duration fields. (Tracer bullet for parity.)
- **Test outline:**
  - File: `tests/test_introspect_parity.py`
  - Name: `test_backend_and_introspect_agree`
  - Asserts: for a shared fixture, the two caches' `get_session_events`-equivalent rows match on `is_response_head`, `output_tokens`, `context_tokens`, `context_window`, `msg_kind`, `response_duration_ms`, and both report `SCHEMA_VERSION == "14"`.
- **Implementation outline:**
  - File(s): `.claude/skills/introspect/scripts/introspect_sessions.py` (mirror `CONTEXT_WINDOWS`, `context_zone`, requestId dedup/head, response duration, `subagent-` prefix, `SCHEMA_VERSION`).
- **Mocks:** `none`
- **Refactor candidates:** if drift risk is high, note a follow-up to extract the shared parse logic into an importable module (out of scope here; the project deliberately keeps two copies per MEMORY.md).
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T4.1](./tokenometrics-G4-T4.1.md)
