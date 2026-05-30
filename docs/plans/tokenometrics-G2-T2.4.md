# T2.4: A caller gets the context-utilization ratio (fraction of window used)

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 4 of 6 in G2
>
> **Nav:** [« T2.3](./tokenometrics-G2-T2.3.md)  ·  [T2.5 »](./tokenometrics-G2-T2.5.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `context_ratio(tokens, window)` returns the raw fraction `tokens / window` — e.g. `context_ratio(40_000, 200_000) == 0.2`, `context_ratio(150_000, 200_000) == 0.75` — and `None` when the window is unknown (`context_ratio(50_000, None) is None`). No categorical zone labeling (see G2 ADR: Quantitative ratio only).
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_context_ratio`
  - Asserts: the fraction for known windows (parametrized) and `None` for an unknown window.
- **Implementation outline:**
  - File(s): `pricing.py` (`context_ratio(tokens, window) -> float | None`).
- **Mocks:** `none`
- **Depends on:** [T2.1](./tokenometrics-G2-T2.1.md)
