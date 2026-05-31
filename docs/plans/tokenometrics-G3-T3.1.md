# T3.1: A caller gets a subagent-prefixed kind for subagent events

> - **Gap:** [G3: Subagent message-kind prefixing](./tokenometrics-G3.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Next:** [T3.2](./tokenometrics-G3-T3.2.md)

- [x] **Done**

`message_kind("user", False, "hi", is_subagent=True) == "subagent-human"`; with `is_subagent=False` it stays `"human"`.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_msg_kind_subagent.py::test_subagent_prefix_applied` — prefixed vs bare across a couple of base kinds |
| Implements | `pricing.py:message_kind` (new `is_subagent` param → `f"subagent-{base}"`) |
| Depends on | — |
