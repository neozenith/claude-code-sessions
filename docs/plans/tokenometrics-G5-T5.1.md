# T5.1: An operator sees idle time between assistant stop and next prompt

> - **Gap:** [G5: Turn timing (idle / active)](./tokenometrics-G5.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Next:** [T5.2](./tokenometrics-G5-T5.2.md)

- [x] **Done**

For a session where the assistant ends its turn (`stop_reason='end_turn'`) at t0 and the human submits the next prompt at t0+30s, `get_session_metrics()` reports that turn's `idle_ms≈30000`.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_session_timing.py::test_idle_between_turns` — `get_session_metrics(project, session)` turn list contains `idle_ms≈30000` |
| Implements | `backend.py:get_session_metrics` (LEAD window over `is_sidechain=0` events), `protocol.py` (add method), `schema.py` (`idx_events_session_ts`) |
| Depends on | [T4.1](./tokenometrics-G4-T4.1.md) |
| Refactor | share the `_delta_ms` helper from T4.1 |
