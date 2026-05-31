# T7.7: A consumer lists the available strategy/model variants

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.6](./summariser-G7-T7.6.md)

- [x] **Done**

`GET /api/summaries/variants` returns `200` with the distinct `(strategy, model)` pairs present across the summary tables — the eval picker's option source.

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_variants_lists_available_strategy_model_pairs` — seed rows spanning two distinct strategy/model pairs, call via `TestClient`, assert the body lists exactly those pairs |
| Implements | `src/.../database/sqlite/backend.py` `list_summary_variants`; `src/.../main.py` `GET /api/summaries/variants` |
| Depends on | [T7.3](./summariser-G7-T7.3.md) |
