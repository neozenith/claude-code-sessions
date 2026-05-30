# T2.5: The absolute-token override supersedes percentage on 1M windows

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 5 of 6 in G2
>
> **Nav:** [« T2.4](./tokenometrics-G2-T2.4.md)  ·  [T2.6 »](./tokenometrics-G2-T2.6.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** On a 1,000,000 window, `context_zone(50_000, ...)` is `"caution"` (5% but ≥32k abs) and `context_zone(70_000, ...)` is `"danger"` (7% but ≥64k abs); `context_zone(tokens, None)` is `None`.
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_zone_absolute_override`
  - Asserts: the override outcomes + None window.
- **Implementation outline:**
  - File(s): `pricing.py:context_zone` (`worse_of` percentage/absolute).
- **Mocks:** `none`
- **Depends on:** [T2.4](./tokenometrics-G2-T2.4.md)
