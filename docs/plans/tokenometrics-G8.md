# G8: Introspect-script parity

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 8 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md), [G2](./tokenometrics-G2.md), [G3](./tokenometrics-G3.md), [G4](./tokenometrics-G4.md), [G5](./tokenometrics-G5.md)  ·  **Blocks:** none
>
> **Nav:** [« G7](./tokenometrics-G7.md)  ·  _(last)_ »

**Current:** `.claude/skills/introspect/scripts/introspect_sessions.py` shares `SCHEMA_VERSION` and has its own copy of pricing/parse logic (per MEMORY.md).

**Gap:** Mirror the schema columns, requestId dedup/head logic, context-window map, response duration, and `subagent-` prefix so both ingesters produce identical rows.

**Output(s):**
- `.claude/skills/introspect/scripts/introspect_sessions.py` (Python): mirrored schema + parsing changes; matching the current `SCHEMA_VERSION` (bumped per schema-changing gap — `"15"` after G2).
- `tests/` cross-check that the script and backend agree on a sample fixture.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T8.1](./tokenometrics-G8-T8.1.md) | Both ingesters produce identical rows for a shared fixture | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T4.1](./tokenometrics-G4-T4.1.md) |

