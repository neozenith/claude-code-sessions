# T5.2: An operator sees active (working) time per turn

> **[« G5: Turn timing (idle / active)](./tokenometrics-G5.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 4 in G5
>
> **Nav:** [« T5.1](./tokenometrics-G5-T5.1.md)  ·  [T5.3 »](./tokenometrics-G5-T5.3.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `active_ms` for a turn = human prompt → that turn's final assistant head timestamp.
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_active_time_per_turn`
  - Asserts: `get_session_metrics()` turn `active_ms` matches the human→assistant-end span.
- **Implementation outline:**
  - File(s): `backend.py:get_session_metrics` (pair human → next assistant end).
- **Mocks:** `none`
- **Depends on:** [T5.1](./tokenometrics-G5-T5.1.md)
