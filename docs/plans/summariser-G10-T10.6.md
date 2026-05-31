# T10.6: A reader gets a report ranking every permutation by score

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.5](./summariser-G10-T10.5.md)
> - **Next:** [T10.7](./summariser-G10-T10.7.md)

- [x] **Done**

`report` reads all result rows in `tmp/summary_bench/` and writes `docs/plans/summariser-G10-REPORT.md` listing permutations ranked by ROUGE-L/BLEU/F1, with the top survivors marked for the human gate and a PROCEED/ABANDON recommendation stub.

| | |
|--|--|
| Test | `tests/test_summary_bench.py::test_report_ranks_by_score` — given fixture result rows with known scores, assert the report orders permutations highest-score-first and names the top cell as the review candidate |
| Implements | `scripts/summary_bench.py` `cmd_report`, `rank_results` |
| Depends on | [T10.4](./summariser-G10-T10.4.md) |
