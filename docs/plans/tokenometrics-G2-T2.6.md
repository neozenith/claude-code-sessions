# T2.6: An operator sees per-event occupancy and ratio after ingestion

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 6 of 6 in G2
>
> **Nav:** [« T2.5](./tokenometrics-G2-T2.5.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** After ingesting an assistant response with `input=6, cache_read=180_000, cache_creation=0` on a 200k model, `get_session_events()` reports `context_tokens=180_006` and `context_ratio≈0.90`.
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_event_context_fields_after_ingest`
  - Asserts: head event's `context_tokens` / `context_ratio` via `get_session_events()`.
- **Implementation outline:**
  - File(s): `schema.py` (3 columns), `cache.py:_parse_event` (compute occupancy/window/ratio), `backend.py:get_session_events` (surface them).
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md)
