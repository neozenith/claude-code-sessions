# T4.1: An operator sees a response's tokens/sec

> - **Gap:** [G4: Response performance (TPS)](./tokenometrics-G4.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Next:** [T4.2](./tokenometrics-G4-T4.2.md)

- [x] **Done**

After ingesting a response whose blocks span a 2-second window from its triggering event, producing `output_tokens=200`, `get_session_events()` reports the head with `response_duration_ms≈2000` and `tps≈100`.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_session_timing.py::test_response_tps` — head event's `response_duration_ms` and `tps` from `get_session_events()` |
| Implements | `schema.py` (`response_duration_ms`), `cache.py:_annotate_responses` (`_delta_ms` from preceding event → last block), `backend.py:get_session_events` (derive `tps`) |
| Depends on | [T1.1](./tokenometrics-G1-T1.1.md) |
| Refactor | extract `_delta_ms` as a shared timestamp helper (reused by G5) |
