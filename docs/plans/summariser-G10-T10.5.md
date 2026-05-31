# T10.5: Skipped no-GGUF cells are logged, never silently dropped

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.4](./summariser-G10-T10.4.md)
> - **Next:** [T10.6](./summariser-G10-T10.6.md)

- [ ] **Done**

When a {family × size} cell has no registered GGUF, the registry omits it from runnable cells but emits an explicit log line naming each skipped cell (no silent caps).

| | |
|--|--|
| Test | `tests/test_summary_bench.py::test_no_gguf_cells_are_logged_not_dropped` — with a GGUF-availability seam reporting one missing build, assert the skipped cell appears in the emitted skip log and is absent from the runnable `--missing` set |
| Implements | `scripts/summary_bench.py` `available_gguf_cells` + skip-logging in `all_permutations` |
| Depends on | [T10.2](./summariser-G10-T10.2.md) |
| Mocks | stub only the GGUF-availability lookup |
