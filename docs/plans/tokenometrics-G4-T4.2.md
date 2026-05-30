# T4.2: TPS is absent when duration is unknown

> **[« G4: Response performance (TPS)](./tokenometrics-G4.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 2 in G4
>
> **Nav:** [« T4.1](./tokenometrics-G4-T4.1.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** When `response_duration_ms` is 0 or NULL (e.g. single-instant response or missing timestamp), `tps` is `None`, never a divide-by-zero or negative value.
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_tps_none_when_no_duration`
  - Asserts: `get_session_events()` head `tps is None` for a zero-duration fixture.
- **Implementation outline:**
  - File(s): `backend.py:get_session_events` (guard `duration_ms > 0`).
- **Mocks:** `none`
- **Depends on:** [T4.1](./tokenometrics-G4-T4.1.md)
