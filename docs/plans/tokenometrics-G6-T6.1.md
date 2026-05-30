# T6.1: A client can fetch per-session turn metrics over HTTP

> **[« G6: Query layer & API endpoints](./tokenometrics-G6.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 3 in G6
>
> **Nav:** « _(first)_  ·  [T6.2 »](./tokenometrics-G6-T6.2.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `GET /api/sessions/{projectId}/{sessionId}/metrics` returns 200 with a per-turn list (each having `idle_ms`, `active_ms`, `tps`, `too_fast`) and a session summary. (Tracer bullet for the metrics endpoint.)
- **Test outline:**
  - File: `tests/test_session_metrics_api.py`
  - Name: `test_session_metrics_endpoint`
  - Asserts: FastAPI `TestClient` GET returns 200 and the documented JSON shape for a fixture session.
- **Implementation outline:**
  - File(s): `main.py` (route), `backend.py:get_session_metrics`, `protocol.py`.
- **Mocks:** `none` (TestClient against a fixture-backed app).
- **Depends on:** [T5.1](./tokenometrics-G5-T5.1.md)
