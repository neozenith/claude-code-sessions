# T1.3: A single-block response is its own head with usage intact

> **[« G1: Response-level token accounting](./tokenometrics-G1.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 4 in G1
>
> **Nav:** [« T1.2](./tokenometrics-G1-T1.2.md)  ·  [T1.4 »](./tokenometrics-G1-T1.4.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** A response logged as one event keeps its full `output_tokens` and is marked head.
- **Test outline:**
  - File: `tests/test_response_dedup.py`
  - Name: `test_single_block_response_intact`
  - Asserts: `get_session_events()` shows the lone event as head with original tokens; `get_session_usage()` total unchanged.
- **Implementation outline:**
  - File(s): `cache.py:_annotate_responses` (group of size 1 → head, no zeroing).
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md)
