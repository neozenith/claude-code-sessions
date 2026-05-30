# T7.1: The frontend zone classifier matches the backend bands

> **[« G7: Frontend surfacing](./tokenometrics-G7.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 4 in G7
>
> **Nav:** « _(first)_  ·  [T7.2 »](./tokenometrics-G7-T7.2.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** `contextZone(tokens, window)` in TS returns the same `smart`/`caution`/`danger`/`null` as the backend for the band + absolute-override cases (200k@55%→caution, 1M@50k→caution, 1M@70k→danger, null window→null). (Tracer bullet for the shared-constant contract.)
- **Test outline:**
  - File: `frontend/src/lib/context-zone.test.ts`
  - Name: `contextZone matches backend bands`
  - Asserts: the four parametrized cases via the exported `contextZone`.
- **Implementation outline:**
  - File(s): `frontend/src/lib/context-zone.ts` (mirror `SMART_ZONE_*` + `contextZone`).
- **Mocks:** `none`
- **Depends on:** [T2.4](./tokenometrics-G2-T2.4.md)
- **Refactor candidates:** colocate the threshold constants with a comment cross-referencing `pricing.py` to prevent drift.
