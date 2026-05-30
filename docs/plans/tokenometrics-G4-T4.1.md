# T4.1: An operator sees a response's tokens/sec

> **[« G4: Response performance (TPS)](./tokenometrics-G4.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 2 in G4
>
> **Nav:** « _(first)_  ·  [T4.2 »](./tokenometrics-G4-T4.2.md)


- [ ] **Done**
- **Cycle:** RED → GREEN → REFACTOR
- **Behavior:** After ingesting a response whose blocks span a 2-second window from its triggering event, producing `output_tokens=200`, `get_session_events()` reports the head with `response_duration_ms≈2000` and `tps≈100`. (Tracer bullet for duration + derived TPS.)
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_response_tps`
  - Asserts: head event's `response_duration_ms` and `tps` from `get_session_events()`.
- **Implementation outline:**
  - File(s): `schema.py` (`response_duration_ms`), `cache.py:_annotate_responses` (`_delta_ms` from preceding event → last block), `backend.py:get_session_events` (derive `tps`).
- **Mocks:** `none`
- **Refactor candidates:** extract `_delta_ms` as a shared timestamp helper (reused by G5).
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md)
