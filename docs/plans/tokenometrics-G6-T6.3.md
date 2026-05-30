# T6.3: An operator sees TPS and idle/active in the sessions list

> **[« G6: Query layer & API endpoints](./tokenometrics-G6.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 3 in G6
>
> **Nav:** [« T6.2](./tokenometrics-G6-T6.2.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `get_sessions_list()` rows include `avg_tps`, `total_idle_ms`, `total_active_ms`, `peak_context_ratio`.
- **Test outline:**
  - File: `tests/test_performance_api.py`
  - Name: `test_sessions_list_has_perf_columns`
  - Asserts: the keys exist with sane values for a fixture session.
- **Implementation outline:**
  - File(s): `schema.py` (sessions rollup columns), `cache.py:_compute_session_timing` (populate in `rebuild_aggregates`), `backend.py:get_sessions_list`.
- **Mocks:** `none`
- **Depends on:** [T5.1](./tokenometrics-G5-T5.1.md)
