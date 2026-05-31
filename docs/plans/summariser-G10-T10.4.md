# T10.4: A user runs one permutation and a result row is written

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.3](./summariser-G10-T10.3.md)
> - **Next:** [T10.5](./summariser-G10-T10.5.md)

- [x] **Done**

`run --id <perm>` generates a candidate summary via the selected merger/model, scores it with `score_summary`, and writes a JSON result row (`permutation_id`, scores, speed) so a re-run sees it `done`.

| | |
|--|--|
| Test | `tests/test_summary_bench.py::test_run_writes_result_row` — with the model-generation seam stubbed to a canned candidate, run `run --id <perm>` and assert the result JSON exists with `permutation_id` + `rouge_l`/`bleu`/`f1` keys |
| Implements | `scripts/summary_bench.py` `cmd_run`, `save_result` |
| Depends on | [T10.1](./summariser-G10-T10.1.md), [T10.2](./summariser-G10-T10.2.md), [T4.1](./summariser-G4-T4.1.md), [T5.1](./summariser-G5-T5.1.md), [T6.1](./summariser-G6-T6.1.md) |
| Mocks | stub only the model-generation seam; the scorer runs real |
