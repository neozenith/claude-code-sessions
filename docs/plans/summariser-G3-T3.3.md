# T3.3: get_merger(flag) selects an impl from the registry; unknown fails loudly

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.2](./summariser-G3-T3.2.md)
> - **Next:** [T3.4](./summariser-G3-T3.4.md)

- [x] **Done**

`get_merger(name)` returns the registered `SummaryMerger` whose `.name` matches the feature-flag value; an unknown name raises (no silent default), so the `strategy` written and the impl invoked always agree.

| | |
|--|--|
| Test | `tests/test_summaries.py::test_get_merger_resolves_registered_and_rejects_unknown` — register two stub mergers, assert `get_merger('a')`/`get_merger('b')` return the matching impls and `get_merger('nope')` raises |
| Implements | `src/.../database/sqlite/merge.py` `MERGER_REGISTRY` + `get_merger(name)` (raises on unknown) |
| Depends on | [T3.1](./summariser-G3-T3.1.md) |
