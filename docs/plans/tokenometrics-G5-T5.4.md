# T5.4: Machine latency is not counted as human idle

> **[« G5: Turn timing (idle / active)](./tokenometrics-G5.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 4 of 4 in G5
>
> **Nav:** [« T5.3](./tokenometrics-G5-T5.3.md)  ·  _(last)_ »


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** Gaps caused by `tool_result` events or subagent (`is_sidechain=1`) activity are excluded from `idle_ms` — only assistant-stop → human gaps count.
- **Test outline:**
  - File: `tests/test_session_timing.py`
  - Name: `test_tool_and_subagent_gaps_not_idle`
  - Asserts: a session with intervening tool_result/subagent events reports idle only for the genuine assistant→human gap.
- **Implementation outline:**
  - File(s): `backend.py:get_session_metrics` (restrict to `is_sidechain=0`; idle only after an `end_turn` head).
- **Mocks:** `none`
- **Depends on:** [T5.1](./tokenometrics-G5-T5.1.md)
