# T10.7: A human records the binding PROCEED/ABANDON verdict

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T10.6](./summariser-G10-T10.6.md)
> - **Next:** [T10.8](./summariser-G10-T10.8.md)

- [ ] **Done**

_(non-code decision gate)_ The `/loop` STOPS at the [ADR3.2](./summariser-G3.md) gate; the user reads the top survivors in the explorer (G8) and against source prompts on SessionDetail (G9), applies the subjective threshold, and writes the binding PROCEED or ABANDON verdict into the report. No automated step crosses this line.

| | |
|--|--|
| Test | non-code gate — no automated test (human review via the G7/G8/G9 UI) |
| Implements | `docs/plans/summariser-G10-REPORT.md` (Tier-2 verdict section) — manual |
| Depends on | [T10.6](./summariser-G10-T10.6.md), [T8.6](./summariser-G8-T8.6.md), [T9.6](./summariser-G9-T9.6.md) |
