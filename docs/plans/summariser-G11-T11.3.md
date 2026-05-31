# T11.3: Both ingesters produce identical rollup_summaries rows for the production strategy

> - **Gap:** [G11: Introspect-script parity](./summariser-G11.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T11.2](./summariser-G11-T11.2.md)
> - **Next:** [T11.4](./summariser-G11-T11.4.md)

- [ ] **Done**

For the single collapsed production strategy, the backend roll-up driver and the introspect script's mirrored driver walk the same bottom-up scope/time DAG and write byte-identical `rollup_summaries` rows over the shared fixture.

| | |
|--|--|
| Test | `tests/test_introspect_parity.py::test_rollup_summaries_agree` — ingest the shared multi-scope fixture into two caches (same injected `FakeSummaryEngine`); `SELECT strategy, scope_path, scope_depth, time_granularity, time_bucket, task_summary, patterns, decisions_values, child_count, source_hash, model … ORDER BY …` from each and assert equality |
| Implements | `.claude/skills/introspect/scripts/introspect_sessions.py` `rollup_summaries` DDL + roll-up driver/merger for the winning strategy (mirroring the collapsed `merge.py` + driver) |
| Depends on | [T11.2](./summariser-G11-T11.2.md), [T3.1](./summariser-G3-T3.1.md) |
| Mocks | shared fixture + the same injected fake `SummaryEngine` in both ingesters |
