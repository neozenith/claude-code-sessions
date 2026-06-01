# T5.4: Machine latency is not counted as human idle

> - **Gap:** [G5: Turn timing (idle / active)](./tokenometrics-G5.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T5.3](./tokenometrics-G5-T5.3.md)

- [x] **Done**

Gaps caused by `tool_result` events or subagent (`is_sidechain=1`) activity are excluded from `idle_ms` — only assistant-stop → human gaps count.

| | |
|--|--|
| Test | `tests/test_session_timing.py::test_tool_and_subagent_gaps_not_idle` — a session with intervening tool_result/subagent events reports idle only for the genuine assistant→human gap |
| Implements | `backend.py:get_session_metrics` (restrict to `is_sidechain=0`; idle only after an `end_turn` head) |
| Depends on | [T5.1](./tokenometrics-G5-T5.1.md) |
