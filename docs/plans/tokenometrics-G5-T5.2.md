# T5.2: An operator sees active (working) time per turn

> - **Gap:** [G5: Turn timing (idle / active)](./tokenometrics-G5.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T5.1](./tokenometrics-G5-T5.1.md)
> - **Next:** [T5.3](./tokenometrics-G5-T5.3.md)

- [x] **Done**

`active_ms` for a turn = human prompt → that turn's final assistant head timestamp.

| | |
|--|--|
| Test | `tests/test_session_timing.py::test_active_time_per_turn` — `get_session_metrics()` turn `active_ms` matches the human→assistant-end span |
| Implements | `backend.py:get_session_metrics` (pair human → next assistant end) |
| Depends on | [T5.1](./tokenometrics-G5-T5.1.md) |
