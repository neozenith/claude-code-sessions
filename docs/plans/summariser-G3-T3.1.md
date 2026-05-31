# T3.1: The driver + a registered stub merger write one rollup row for a leaf scope

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T3.2](./summariser-G3-T3.2.md)

- [ ] **Done**

`roll_up_scopes(conn, engine, strategy, model, granularity)` with an in-test stub merger registered under that strategy writes exactly one `rollup_summaries` row keyed `(strategy, model, scope_path, 'day', bucket)` for a project-leaf scope, merging its `session_summaries` for that model. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_summaries.py::test_driver_writes_one_rollup_row_via_registered_merger` — register a stub merger returning canned lenses, seed two `session_summaries` rows for one leaf scope+model, run the driver, assert one `rollup_summaries` row with the matching composite key and `child_count=2` |
| Implements | `src/.../database/sqlite/schema.py` `rollup_summaries` table + `SCHEMA_VERSION` "18"→"19"; `src/.../database/sqlite/merge.py` `SummaryMerger` Protocol + `MERGER_REGISTRY`; `src/.../database/sqlite/summaries.py` `roll_up_scopes` driver |
| Depends on | [T1.2](./summariser-G1-T1.2.md), [T2.1](./summariser-G2-T2.1.md) |
| Refactor | extract the day/week/month truncation expressions from `cache.py` into a shared helper reused by the driver |
