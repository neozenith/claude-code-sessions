# T2.1: A caller can resolve a 1M-window model's context window

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 6 in G2
>
> **Nav:** « _(first)_  ·  [T2.2 »](./tokenometrics-G2-T2.2.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `context_window("claude-opus-4-7")` returns `1_000_000`. (Tracer bullet for the mapping.)
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_window_1m_models`
  - Asserts: `context_window("claude-opus-4-7") == 1_000_000` (and opus-4-6/4-8, sonnet-4-6).
- **Implementation outline:**
  - File(s): `pricing.py` (`CONTEXT_WINDOWS` map + `context_window`).
- **Mocks:** `none`
- **Depends on:** none
