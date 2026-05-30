# T2.2: A caller gets 200k for standard models and None for unknown

> **[« G2: Context-window utilization annotations](./tokenometrics-G2.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 6 in G2
>
> **Nav:** [« T2.1](./tokenometrics-G2-T2.1.md)  ·  [T2.3 »](./tokenometrics-G2-T2.3.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `context_window` returns `200_000` for opus-4-5 / sonnet-4-5 / haiku-4-5 and `None` for `<synthetic>` / empty / unrecognized ids.
- **Test outline:**
  - File: `tests/test_context_window.py`
  - Name: `test_window_200k_and_unknown`
  - Asserts: parametrized over the model ids → expected window / None.
- **Implementation outline:**
  - File(s): `pricing.py` (map entries; `None` fallback).
- **Mocks:** `none`
- **Depends on:** [T2.1](./tokenometrics-G2-T2.1.md)
