# T7.5: A consumer gets a 404 for an unknown scope

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.4](./summariser-G7-T7.4.md)
> - **Next:** [T7.6](./summariser-G7-T7.6.md)

- [ ] **Done**

`GET /api/summaries/scope?...` returns `404` when `scope_path` does not exist in the G1 scope hierarchy at all (ADR7.1) — distinguishing "missing" from "not yet computed".

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_unknown_scope_returns_404` — seed a fixture cache, request a `scope_path` absent from `ancestor_scopes` via `TestClient`, assert `404` |
| Implements | `src/.../database/sqlite/backend.py` `get_rollup_summary` (unknown-scope branch); `src/.../main.py` `GET /api/summaries/scope` |
| Depends on | [T7.4](./summariser-G7-T7.4.md) |
