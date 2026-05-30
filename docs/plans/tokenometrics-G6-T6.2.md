# T6.2: A client can fetch the performance summary, scoped by filters

> **[« G6: Query layer & API endpoints](./tokenometrics-G6.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 3 in G6
>
> **Nav:** [« T6.1](./tokenometrics-G6-T6.1.md)  ·  [T6.3 »](./tokenometrics-G6-T6.3.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `GET /api/performance?days=7&project=X` returns `by_model` rows (avg/median TPS, idle/active) and a `zone_histogram` {smart, caution, danger}, scoped to the filter.
- **Test outline:**
  - File: `tests/test_performance_api.py`
  - Name: `test_performance_summary_endpoint`
  - Asserts: shape + that a project filter narrows the rows.
- **Implementation outline:**
  - File(s): `main.py` (route), `backend.py:get_performance_summary`, `protocol.py`.
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T5.1](./tokenometrics-G5-T5.1.md)
