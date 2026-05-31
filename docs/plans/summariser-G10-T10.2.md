# T10.2: A developer enumerates the permutation registry with done/missing status

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.1](./summariser-G10-T10.1.md)
> - **Next:** [T10.3](./summariser-G10-T10.3.md)

- [ ] **Done**

`all_permutations(results_dir)` returns one dict per strategy×family×size cell with `permutation_id`, `sort_key`, `label`, and a `done` flag set by file-existence in `results_dir`.

| | |
|--|--|
| Test | `tests/test_summary_bench.py::test_registry_enumerates_and_marks_status` — with a tmp results dir holding one result file, assert that cell is `done=True`, an absent cell `done=False`, and ids are the strategy×family×size cross-product |
| Implements | `scripts/summary_bench.py` `all_permutations`, `permutation_id`, `check_status` |
| Depends on | [T10.1](./summariser-G10-T10.1.md), [T4.1](./summariser-G4-T4.1.md), [T5.1](./summariser-G5-T5.1.md), [T6.1](./summariser-G6-T6.1.md) |
