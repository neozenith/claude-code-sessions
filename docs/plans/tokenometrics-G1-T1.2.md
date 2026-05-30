# T1.2: An operator can see exactly one response-head per requestId

> **[« G1: Response-level token accounting](./tokenometrics-G1.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 4 in G1
>
> **Nav:** [« T1.1](./tokenometrics-G1-T1.1.md)  ·  [T1.3 »](./tokenometrics-G1-T1.3.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** For an ingested multi-block response, exactly one returned event has `is_response_head == true`; the rest are `false`.
- **Test outline:**
  - File: `tests/test_response_dedup.py`
  - Name: `test_one_head_per_request_id`
  - Asserts: `get_session_events()` returns exactly one head among the blocks sharing a `requestId`.
- **Implementation outline:**
  - File(s): `cache.py:_annotate_responses` (head = last block); `backend.py:get_session_events` surfaces `is_response_head`.
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md)
