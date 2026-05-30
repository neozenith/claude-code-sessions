# T3.2: An operator sees no bare 'human' kinds in subagent transcripts

> **[« G3: Subagent message-kind prefixing](./tokenometrics-G3.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 3 in G3
>
> **Nav:** [« T3.1](./tokenometrics-G3-T3.1.md)  ·  [T3.3 »](./tokenometrics-G3-T3.3.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** After ingesting a subagent fixture file, every event from it has a `subagent-*` kind and none is bare `human`/`user_text`.
- **Test outline:**
  - File: `tests/test_msg_kind_subagent.py`
  - Name: `test_subagent_file_events_all_prefixed`
  - Asserts: `get_session_events()` for the subagent events → all kinds start with `subagent-`.
- **Implementation outline:**
  - File(s): `cache.py` (compute `is_subagent = is_sidechain or file_type in {subagent, agent_root}`, thread to `_parse_event`).
- **Mocks:** `none`
- **Depends on:** [T1.1](./tokenometrics-G1-T1.1.md), [T3.1](./tokenometrics-G3-T3.1.md)
