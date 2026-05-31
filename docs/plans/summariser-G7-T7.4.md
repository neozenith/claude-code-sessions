# T7.4: A consumer sees a valid-but-unsummarised scope reported explicitly

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.3](./summariser-G7-T7.3.md)
> - **Next:** [T7.5](./summariser-G7-T7.5.md)

- [x] **Done**

`GET /api/summaries/scope?...` returns `200` with `{status:"not_summarised"}` when the scope exists in the G1 hierarchy but has no `rollup_summaries` row (ADR7.1).

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_unsummarised_scope_returns_not_summarised_status` — seed a cache where the scope is a valid `ancestor_scopes`-derived path with no rollup row, call via `TestClient`, assert `200` and body `{"status":"not_summarised"}` |
| Implements | `src/.../database/sqlite/backend.py` `get_rollup_summary` (not-summarised path); `src/.../main.py` `GET /api/summaries/scope` |
| Depends on | [T7.2](./summariser-G7-T7.2.md), [T1.2](./summariser-G1-T1.2.md) |
