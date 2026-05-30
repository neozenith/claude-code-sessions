# T5.3: A reviewer sees a 'too-fast' flag only for implausibly quick replies

> **[« G5: Turn timing (idle / active)](./tokenometrics-G5.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 4 in G5
>
> **Nav:** [« T5.2](./tokenometrics-G5-T5.2.md)  ·  [T5.4 »](./tokenometrics-G5-T5.4.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** A human reply 1s after a 2,000-token response is `too_fast=true` (1s < 2000/8 = 250s); a reply 1s after a 50-token response is `too_fast=false` (below the 200-token floor).
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_too_fast_flag`
  - Asserts: both outcomes via `get_session_metrics()`.
- **Implementation outline:**
  - File(s): `pricing.py` (`READ_TOKENS_PER_SEC=8`, `TOO_FAST_MIN_TOKENS=200`), `backend.py:get_session_metrics` (compute `too_fast`).
- **Mocks:** `none`
- **Depends on:** [T5.1](./tokenometrics-G5-T5.1.md)
