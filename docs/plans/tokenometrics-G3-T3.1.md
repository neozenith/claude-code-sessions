# T3.1: A caller gets a subagent-prefixed kind for subagent events

> **[« G3: Subagent message-kind prefixing](./tokenometrics-G3.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 3 in G3
>
> **Nav:** « _(first)_  ·  [T3.2 »](./tokenometrics-G3-T3.2.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `message_kind("user", False, "hi", is_subagent=True) == "subagent-human"`; with `is_subagent=False` it stays `"human"`. (Tracer bullet for the prefix rule.)
- **Test outline:**
  - File: `tests/test_msg_kind_subagent.py`
  - Name: `test_subagent_prefix_applied`
  - Asserts: prefixed vs bare across a couple of base kinds.
- **Implementation outline:**
  - File(s): `pricing.py:message_kind` (new `is_subagent` param → `f"subagent-{base}"`).
- **Mocks:** `none`
- **Depends on:** none
