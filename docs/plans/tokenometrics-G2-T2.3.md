# T2.3: Window lookup is not fooled by substring collisions

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 6 in G2
>
> **Nav:** [« T2.2](./tokenometrics-G2-T2.2.md)  ·  [T2.4 »](./tokenometrics-G2-T2.4.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** A model id containing one key as a substring of another (e.g. `sonnet-4-5` vs `sonnet-4-6`, or a hypothetical `opus-4-50`) resolves to the correct window via longest-key-first matching.
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_window_no_substring_collision`
  - Asserts: `context_window("claude-sonnet-4-6")==1_000_000` and `("claude-sonnet-4-5-20250929")==200_000`.
- **Implementation outline:**
  - File(s): `pricing.py` (`sorted(..., key=len, reverse=True)`).
- **Mocks:** `none`
- **Depends on:** [T2.1](./tokenometrics-G2-T2.1.md)
