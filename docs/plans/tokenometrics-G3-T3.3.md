# T3.3: Main-thread human prompts remain unprefixed

> - **Gap:** [G3: Subagent message-kind prefixing](./tokenometrics-G3.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T3.2](./tokenometrics-G3-T3.2.md)

- [x] **Done**

A human prompt in a main session file keeps `msg_kind == "human"`.

| | |
|--|--|
| Test | `tests/test_msg_kind_subagent.py::test_main_session_human_unprefixed` — `get_session_events()` main human event kind is `"human"` |
| Implements | covered by T3.2 logic; this guards the negative case |
| Depends on | [T3.2](./tokenometrics-G3-T3.2.md) |
