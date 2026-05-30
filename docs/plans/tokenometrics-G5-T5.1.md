# T5.1: An operator sees idle time between assistant stop and next prompt

> **[« G5: Turn timing (idle / active)](./tokenometrics-G5.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 4 in G5
>
> **Nav:** « _(first)_  ·  [T5.2 »](./tokenometrics-G5-T5.2.md)


- [x] **Done**
- **Cycle:** RED → GREEN → REFACTOR
- **Behavior:** For a session where the assistant ends its turn (`stop_reason='end_turn'`) at t0 and the human submits the next prompt at t0+30s, `get_session_metrics()` reports that turn's `idle_ms≈30000`. (Tracer bullet for the LEAD timing query.)
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_idle_between_turns`
  - Asserts: `get_session_metrics(project, session)` turn list contains `idle_ms≈30000`.
- **Implementation outline:**
  - File(s): `backend.py:get_session_metrics` (LEAD window over `is_sidechain=0` events), `protocol.py` (add method), `schema.py` (`idx_events_session_ts`).
- **Mocks:** `none`
- **Refactor candidates:** share the `_delta_ms` helper from T4.1.
- **Depends on:** [T4.1](./tokenometrics-G4-T4.1.md)
