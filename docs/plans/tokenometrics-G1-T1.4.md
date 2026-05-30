# T1.4: A synthetic assistant event (no requestId) is its own head

> **[« G1: Response-level token accounting](./tokenometrics-G1.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 4 of 4 in G1
>
> **Nav:** [« T1.3](./tokenometrics-G1-T1.3.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** An assistant event with `requestId == null` (e.g. `<synthetic>`) is treated as its own head and its usage is retained.
- **Test outline:**
  - File: `tests/test_response_dedup.py`
  - Name: `test_null_request_id_is_own_head`
  - Asserts: via `get_session_events()` the null-requestId event is head; totals include it once.
- **Implementation outline:**
  - File(s): `cache.py:_annotate_responses` (null `request_id` branch).
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md)
