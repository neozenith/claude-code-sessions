# G8: Introspect-script parity

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G1](./tokenometrics-G1.md), [G2](./tokenometrics-G2.md), [G3](./tokenometrics-G3.md), [G4](./tokenometrics-G4.md), [G5](./tokenometrics-G5.md)
> - **Blocks:** none
> - **Prev:** [G7](./tokenometrics-G7.md)

Mirror every ingestion change in the standalone introspect script so both ingesters produce identical rows.

## Context

`.claude/skills/introspect/scripts/introspect_sessions.py` shares `SCHEMA_VERSION`
and keeps its own copy of the pricing/parse logic (per MEMORY.md),
so it must be updated in lockstep or the two caches diverge.

## Outputs

| File | Change |
|------|--------|
| `.claude/skills/introspect/scripts/introspect_sessions.py` | mirror the schema columns, requestId dedup/head, `CONTEXT_WINDOWS` + `context_ratio`, response duration, `subagent-` prefix, and `SCHEMA_VERSION` (`"15"` after G2) |
| `tests/` | cross-check both ingesters agree on a shared fixture |

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T8.1](./tokenometrics-G8-T8.1.md) | Both ingesters produce identical rows for a shared fixture | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T4.1](./tokenometrics-G4-T4.1.md) |
