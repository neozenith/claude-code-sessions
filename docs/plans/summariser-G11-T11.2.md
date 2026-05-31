# T11.2: Both ingesters produce identical session_summaries rows for a shared fixture

> - **Gap:** [G11: Introspect-script parity](./summariser-G11.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T11.1](./summariser-G11-T11.1.md)
> - **Next:** [T11.3](./summariser-G11-T11.3.md)

- [ ] **Done**

Running the backend `CacheManager` and the introspect `CacheManager` over one shared JSONL fixture, each driven by the same injected deterministic fake `SummaryEngine`, yields byte-identical `session_summaries` rows.

| | |
|--|--|
| Test | `tests/test_introspect_parity.py::test_session_summaries_agree` — ingest the shared fixture into two caches with a `FakeSummaryEngine` injected into both; `SELECT content_hash, task_summary, patterns, decisions_values, model, human_event_count … ORDER BY project_id, session_id` from each and assert `backend_rows == introspect_rows` |
| Implements | `.claude/skills/introspect/scripts/introspect_sessions.py` `session_summaries` DDL + `summarise_session` (mirroring `summaries.py`), wired into its ingest flow |
| Depends on | [T11.1](./summariser-G11-T11.1.md), [T2.1](./summariser-G2-T2.1.md) |
| Mocks | shared tiny fixture + an injected fake `SummaryEngine` (fixed 3-lens text keyed on input) in BOTH ingesters — deterministic without real `muninn_chat` |
