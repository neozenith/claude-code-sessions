# T2.5: A session with no typed prompts produces no summary

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.4](./summariser-G2-T2.4.md)
> - **Next:** [T2.6](./summariser-G2-T2.6.md)

- [x] **Done**

A session containing only non-`human` events yields no engine call and no `session_summaries` row.

| | |
|--|--|
| Test | `tests/test_summaries.py::test_session_without_human_events_writes_no_row` — seed a session of only `assistant`/`tool`/`user_text` events; call `summarise_session` with a call-counting fake engine; assert zero engine calls and zero rows for that session |
| Implements | `src/.../database/sqlite/summaries.py` empty-human-text early return in `summarise_session` |
| Depends on | [T2.1](./summariser-G2-T2.1.md) |
