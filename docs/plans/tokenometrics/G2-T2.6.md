# T2.6: An operator sees per-event occupancy and ratio after ingestion

> - **Gap:** [G2: Context-window utilization annotations](./tokenometrics-G2.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T2.5](./tokenometrics-G2-T2.5.md)

- [x] **Done**

After ingesting an assistant response with `input=6, cache_read=180_000, cache_creation=0` on a 200k model, `get_session_events()` reports `context_tokens=180_006` and `context_ratio≈0.90`.

| | |
|--|--|
| Test | `tests/test_context_window.py::test_event_context_fields_after_ingest` — head event's `context_tokens` / `context_ratio` via `get_session_events()` |
| Implements | `schema.py` (3 columns), `cache.py:_parse_event` (compute occupancy/window/ratio), `backend.py:get_session_events` (surface them) |
| Depends on | [T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md) |
