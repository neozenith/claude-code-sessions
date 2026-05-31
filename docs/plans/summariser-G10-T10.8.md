# T10.8: On PROCEED, collapse the pipeline to the winning strategy+model

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.7](./summariser-G10-T10.7.md)

- [ ] **Done**

_(conditional — executed only on PROCEED; the loop STOPS at the [ADR3.2](./summariser-G3.md) gate for human review before this runs)_ Drop the losing `SummaryMerger` implementations + the feature flag, pin the winning model ([ADR2.1](./summariser-G2.md)), and remove the G7/G8 strategy/model selectors ([ADR7.2](./summariser-G7.md)). On ABANDON instead: freeze all three as a PoC with the default flag set to the best-scoring option, and open a new gap-analysis (this ticket is then dropped).

| | |
|--|--|
| Test | non-code at decision time — no test for the branch choice; the resulting collapse is a normal change validated by the existing G3/G7/G8 suites (winner-only mergers/selectors pass, losers' tests deleted) and `make ci` |
| Implements | `src/.../database/sqlite/summaries.py`/`merge.py` (remove losing mergers + flag); `src/.../backend.py` + `frontend` Summaries/SessionDetail (remove eval selectors) |
| Depends on | [T10.7](./summariser-G10-T10.7.md) |
