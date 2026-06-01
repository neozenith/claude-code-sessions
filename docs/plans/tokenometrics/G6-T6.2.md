# T6.2: A client can fetch the performance summary, scoped by filters

> - **Gap:** [G6: Query layer & API endpoints](./tokenometrics-G6.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T6.1](./tokenometrics-G6-T6.1.md)
> - **Next:** [T6.3](./tokenometrics-G6-T6.3.md)

- [x] **Done**

`GET /api/performance?days=7&project=X` returns `by_model` rows (avg/median TPS, idle/active) and a `ratio_histogram` (response-head counts binned by raw `context_ratio`), scoped to the filter. No zone labels (per the G2 ADR "Quantitative ratio only").

| | |
|--|--|
| Test | `tests/test_performance_api.py::test_performance_summary_endpoint` — shape + that a project filter narrows the rows |
| Implements | `main.py` (route), `backend.py:get_performance_summary`, `protocol.py` |
| Depends on | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T5.1](./tokenometrics-G5-T5.1.md) |
