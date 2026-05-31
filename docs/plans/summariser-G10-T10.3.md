# T10.3: A user lists only the incomplete permutations via `manifest --missing`

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.2](./summariser-G10-T10.2.md)
> - **Next:** [T10.4](./summariser-G10-T10.4.md)

- [ ] **Done**

`manifest --missing` prints exactly the permutations whose result file is absent, cheapest-first by `sort_key`; `--commands` emits one runnable `run --id <perm>` line each.

| | |
|--|--|
| Test | `tests/test_summary_bench.py::test_manifest_missing_lists_incomplete` — invoke the CLI `manifest --missing --commands` against a tmp results dir with some cells pre-populated, assert output contains only missing ids as `run --id ...` lines in size order |
| Implements | `scripts/summary_bench.py` `cmd_manifest` + manifest argparse subparser |
| Depends on | [T10.2](./summariser-G10-T10.2.md) |
