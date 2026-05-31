# T2.1: A developer's typed prompts become one stored 3-lens session summary

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T2.2](./summariser-G2-T2.2.md)

- [ ] **Done**

`summarise_session(conn, project_id, session_id, engine, model)` gathers the session's `msg_kind='human'` text, calls the injected engine once, and writes exactly one `session_summaries` row holding `task_summary`, `patterns`, and `decisions_values` from the engine's parsed output. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_summaries.py::test_summarise_session_writes_one_three_lens_row` — seed a tiny fixture cache with two `msg_kind='human'` events; call `summarise_session` with a fake engine returning canned 3-lens output; assert one row with the three lenses, `model` provenance, `human_event_count == 2` |
| Implements | `src/.../database/sqlite/schema.py` `session_summaries` table + `SCHEMA_VERSION` "17"→"18"; `src/.../database/sqlite/summaries.py` `summarise_session`, `SummaryEngine` protocol |
| Depends on | — |
