# T7.1: ~~The frontend zone classifier matches the backend bands~~ — DROPPED

> **[« G7: Frontend surfacing](./tokenometrics-G7.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 1 of 4 in G7
>
> **Nav:** « _(first)_  ·  [T7.2 »](./tokenometrics-G7-T7.2.md)


- [x] **Done** — _Dropped, no work required._
- **Status:** **DROPPED** per the G2 ADR "Quantitative ratio only — no zone labeling." There is no frontend zone classifier (`context-zone.ts` / `contextZone` / `SMART_ZONE_*`) to mirror, because the backend exposes only the raw `context_ratio`. The SessionDetail occupancy bar (T7.3) renders width ∝ `context_ratio` directly; the Performance histogram (T7.4) bins by raw ratio. No shared-constant contract is needed.
- **Depends on:** [T2.4](./tokenometrics-G2-T2.4.md)
