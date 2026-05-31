# T6.2: A flat ancestor's child_count counts descendant sessions, not child scopes

> - **Gap:** [G6: SummaryMergerFlat (re-summarise raw sessions per scope)](./summariser-G6.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T6.1](./summariser-G6-T6.1.md)
> - **Next:** [T6.3](./summariser-G6-T6.3.md)

- [x] **Done**

For an ancestor scope (e.g. `clients`) with two child project scopes holding N total session summaries, the flat rollup's `child_count` equals N (the raw sessions) — distinguishing it from strict/reground where the same ancestor's `child_count` is the number of direct child scopes.

| | |
|--|--|
| Test | `tests/test_merge_flat.py::test_flat_child_count_is_descendant_sessions` — seed `clients/acme` and `clients/beta` with known session-summary counts, run `flat`, assert the `clients` rollup `child_count` equals the total sessions (not 2) |
| Implements | `src/.../database/sqlite/summaries.py` flat `child_count` from gathered raw sessions |
| Depends on | [T6.1](./summariser-G6-T6.1.md) |
