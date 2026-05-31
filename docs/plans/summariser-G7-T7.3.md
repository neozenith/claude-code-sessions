# T7.3: A consumer selects a specific strategy/model variant of a scope summary

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.2](./summariser-G7-T7.2.md)
> - **Next:** [T7.4](./summariser-G7-T7.4.md)

- [x] **Done**

`GET /api/summaries/scope?...&strategy=&model=` returns the row matching the requested `strategy`+`model` when multiple variants coexist for the same scope/grain/bucket (ADR7.2).

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_scope_summary_selects_matching_strategy_model_variant` — seed two rollup rows differing only by strategy/model for one scope/grain/bucket, request each via `TestClient`, assert each returns the correct variant |
| Implements | `src/.../database/sqlite/backend.py` `get_rollup_summary` (strategy/model selection) |
| Depends on | [T7.2](./summariser-G7-T7.2.md) |
