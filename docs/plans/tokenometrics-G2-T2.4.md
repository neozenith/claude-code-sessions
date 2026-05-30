# T2.4: A caller gets the right zone from percentage bands

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 4 of 6 in G2
>
> **Nav:** [« T2.3](./tokenometrics-G2-T2.3.md)  ·  [T2.5 »](./tokenometrics-G2-T2.5.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `context_zone(tokens, 200_000)` returns `"smart"` at 40k (20%), `"caution"` at 110k (55%), `"danger"` at 150k (75%).
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_zone_percentage_bands`
  - Asserts: the three band outcomes for a 200k window.
- **Implementation outline:**
  - File(s): `pricing.py` (`SMART_ZONE_*` constants + `context_zone`).
- **Mocks:** `none`
- **Depends on:** [T2.1](./tokenometrics-G2-T2.1.md)
