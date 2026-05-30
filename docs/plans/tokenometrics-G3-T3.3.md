# T3.3: Main-thread human prompts remain unprefixed

> **[« G3: Subagent message-kind prefixing](./tokenometrics-G3.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 3 in G3
>
> **Nav:** [« T3.2](./tokenometrics-G3-T3.2.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** A human prompt in a main session file keeps `msg_kind == "human"`.
- **Test outline:**
  - File: `tests/test_msg_kind_subagent.py`
  - Name: `test_main_session_human_unprefixed`
  - Asserts: `get_session_events()` main human event kind is `"human"`.
- **Implementation outline:**
  - File(s): covered by T3.2 logic; this guards the negative case.
- **Mocks:** `none`
- **Depends on:** [T3.2](./tokenometrics-G3-T3.2.md)
