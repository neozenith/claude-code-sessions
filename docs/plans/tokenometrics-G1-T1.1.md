# T1.1: An operator can see a multi-block response counted once in session totals

> **[« G1: Response-level token accounting](./tokenometrics-G1.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 4 in G1
>
> **Nav:** « _(first)_  ·  [T1.2 »](./tokenometrics-G1-T1.2.md)


- [ ] **Done**
- **Cycle:** RED → GREEN → REFACTOR
- **Behavior:** After ingesting a session whose single response is logged as 3 content-block events that each repeat `output_tokens=100`, the session's reported total output tokens is `100`, not `300`. (Tracer bullet — proves the dedup path end-to-end through ingestion + query.)
- **Test outline:**
  - File: `tests/test_response_dedup.py`
  - Name: `test_multiblock_response_counted_once`
  - Asserts: build a fixture cache from an in-repo JSONL fixture, then `get_session_usage()` (public query) returns `total_output_tokens == 100` for that session.
- **Implementation outline:**
  - File(s): `schema.py` (add `request_id`, `stop_reason`, `is_response_head` + index, bump `SCHEMA_VERSION`), `cache.py` (`_parse_event` extracts `requestId`/`stop_reason`; `_annotate_responses` zeroes non-head usage; `_write_parsed` writes the columns).
  - Minimum code to make the deduped total correct.
- **Mocks:** `none` (real SQLite fixture cache; system boundary is the filesystem JSONL fixture, which is real and in-repo).
- **Refactor candidates:** extract `_USAGE_COLS` constant; pull group-by-requestId into a small pure helper for reuse by G8.
- **Depends on:** none
