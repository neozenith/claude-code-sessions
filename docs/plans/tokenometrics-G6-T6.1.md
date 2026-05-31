# T6.1: A client can fetch per-session turn metrics over HTTP

> - **Gap:** [G6: Query layer & API endpoints](./tokenometrics-G6.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Next:** [T6.2](./tokenometrics-G6-T6.2.md)

- [x] **Done**

`GET /api/sessions/{projectId}/{sessionId}/metrics` returns 200 with a per-turn list (each having `idle_ms`, `active_ms`, `tps`, `too_fast`) and a session summary.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_session_metrics_api.py::test_session_metrics_endpoint` — FastAPI `TestClient` GET returns 200 and the documented JSON shape for a fixture session |
| Implements | `main.py` (route), `backend.py:get_session_metrics`, `protocol.py` |
| Depends on | [T5.1](./tokenometrics-G5-T5.1.md) |
