# T7.2: A consumer retrieves a roll-up summary for a scope at a grain+bucket

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.1](./summariser-G7-T7.1.md)
> - **Next:** [T7.3](./summariser-G7-T7.3.md)

- [x] **Done**

`GET /api/summaries/scope?path=&grain=&bucket=&strategy=&model=` returns `200` with the `rollup_summaries` row matching `scope_path` + `time_granularity` + `time_bucket`.

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_scope_summary_returns_rollup_for_grain_and_bucket` — seed one `rollup_summaries` row, request that path/grain/bucket via `TestClient`, assert `200` and the returned rollup matches |
| Implements | `src/.../database/sqlite/backend.py` `get_rollup_summary`; `src/.../main.py` `GET /api/summaries/scope` |
| Depends on | [T7.1](./summariser-G7-T7.1.md), [T3.1](./summariser-G3-T3.1.md) |
