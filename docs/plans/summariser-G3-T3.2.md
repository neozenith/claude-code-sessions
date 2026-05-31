# T3.2: An ancestor scope merges its child scopes' rollups bottom-up

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.1](./summariser-G3-T3.1.md)
> - **Next:** [T3.3](./summariser-G3-T3.3.md)

- [ ] **Done**

The driver processes scopes deepest-first: given child-scope rollups at `clients/acme` and `clients/beta`, it merges them into a `clients` rollup whose `child_count` equals the number of direct child scopes (not transitive sessions), children existing before their parent merges.

| | |
|--|--|
| Test | `tests/test_summaries.py::test_ancestor_merges_child_rollups_bottom_up` — seed two leaf scopes sharing the `clients` ancestor (stub merger), run the driver once, assert a `clients` row with `child_count=2` written after the deeper rows (depth order) |
| Implements | `src/.../database/sqlite/summaries.py` deepest-first scope enumeration in `roll_up_scopes` (orders distinct `ancestor_scopes` by `scope_depth` desc; ancestor merge reads child `rollup_summaries`) |
| Depends on | [T3.1](./summariser-G3-T3.1.md), [T1.2](./summariser-G1-T1.2.md) |
