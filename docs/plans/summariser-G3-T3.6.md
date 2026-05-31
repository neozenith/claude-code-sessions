# T3.6: The root scope yields the all-domains rollup

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.5](./summariser-G3-T3.5.md)
> - **Next:** [T3.7](./summariser-G3-T3.7.md)

- [ ] **Done**

The driver produces a `rollup_summaries` row at `scope_path=''` (`scope_depth=0`) that merges every top-level domain's rollup for the given `(strategy, model, grain, bucket)` — the all-domains summary at the top of the trie.

| | |
|--|--|
| Test | `tests/test_summaries.py::test_root_scope_merges_all_domains` — seed projects under two distinct domains (e.g. `play/foo`, `clients/acme/app`), run the driver (stub merger), assert a `scope_path=''` row exists with `scope_depth=0` and `child_count` equal to the number of top-level domains |
| Implements | `src/.../database/sqlite/summaries.py` root-node handling in `roll_up_scopes` (empty `scope_path`, merges depth-1 children) |
| Depends on | [T3.2](./summariser-G3-T3.2.md) |
