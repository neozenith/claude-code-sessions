# T7.1: A consumer retrieves the three lenses of a summarised session

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T7.2](./summariser-G7-T7.2.md)

- [x] **Done**

`GET /api/summaries/session/{project_id}/{session_id}?model=` returns `200` with the discriminated payload `{status:"summarised", lenses:{...}}` carrying the three lenses for a session that has a `session_summaries` row. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_session_summary_returns_three_lenses` — seed a fixture cache with one `session_summaries` row, call via `TestClient`, assert `200` and all three lenses present |
| Implements | `src/.../database/sqlite/backend.py` `get_session_summary`; `src/.../main.py` `GET /api/summaries/session/{project_id}/{session_id}` |
| Depends on | [T2.1](./summariser-G2-T2.1.md) |
