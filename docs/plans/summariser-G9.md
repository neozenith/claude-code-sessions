# G9: SessionDetail evaluation — 18-kind filter + summary lineage

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G7](./summariser-G7.md), [G8](./summariser-G8.md)
> - **Blocks:** [G10](./summariser-G10.md)
> - **Prev:** [G8](./summariser-G8.md)
> - **Next:** [G10](./summariser-G10.md)

Turns SessionDetail into an evaluation surface: a single flat selector over all 18 `msg_kind` values, plus a lineage breadcrumb linking the session up and down its scope hierarchy to the summaries. Built before the benchmark so the [G10](./summariser-G10.md) human review can cross-check a summary against the very prompts that produced it.

## Context
`msg_kind` has exactly 18 canonical values — 9 base kinds × {main, `subagent-`} (`pricing.py:message_kind`). The frontend types them (`api-client.ts:549-565`) but SessionDetail exposes only `MSG_KIND_OPTIONS` (10 base entries, `message-kinds.ts:18-29`) and a separate `Scope` toggle (tokenometrics T7.2).
Evaluating faithfulness means reading a session's summary next to its `msg_kind='human'` prompts and navigating to the project/domain/root roll-ups that summary feeds. The `ScopeBreadcrumb` (G8) over `scope_path` (G1) provides that up/down lineage; this gap mounts it on SessionDetail and links to the session summary via the G7 API.

## Outputs
| File | Change |
|------|--------|
| `frontend/src/lib/message-kinds.ts` (ts) | Expand `MSG_KIND_OPTIONS` to 19 entries (All + 18); retire the `Scope`/`matchesKindFilter` composition. |
| `frontend/src/pages/SessionDetail.tsx` (tsx) | Single dropdown drives `?msg=` (full kind values incl. `subagent-*`); mount `ScopeBreadcrumb` linking session → project → …ancestors… → root summaries; show the session's 3-lens summary card. |
| `frontend/src/lib/message-kinds.test.ts` (ts) | Option-count + filter-matching tests for the 18 values. |
| `frontend/e2e/session-detail-filter.spec.ts` (ts) | Update from "10 options" to 19; assert a `subagent-*` selection round-trips; assert the breadcrumb links to the explorer scope. |

## ADR9.1: Single flat 19-option dropdown; remove the scope toggle
- **Decision:** SessionDetail exposes one `<select>` listing "All messages" + the 18 canonical `msg_kind` values; the separate `Scope` toggle (tokenometrics T7.2) is removed and `?msg=` carries the full kind value (e.g. `subagent-thinking`).
- **Why:** Literally the brief — "select from each of the now 18 types"; one control, every kind directly selectable.
- **Rejected:** Keeping the toggle alongside the dropdown (two overlapping controls); grouped optgroups (nicer but unnecessary markup for the brief's literal ask). The `matchesKindFilter` scope composition becomes dead code and is removed.
- **Superseded:** the tokenometrics T7.2 scope-toggle composition.

## ADR9.2: Lineage breadcrumb unifies session ↔ scope navigation
- **Decision:** Reuse the G8 `ScopeBreadcrumb` on SessionDetail so a session links up to its project/subdomain/domain/root summaries and back down — one consistent up/down lineage navigation across both pages.
- **Why:** The user evaluates "from the Session Details page too"; a shared breadcrumb makes the variable-depth data structure traversable and shows how a session relates to each roll-up tier it feeds.
- **Rejected:** A SessionDetail-only ad-hoc link (duplicates navigation, drifts from the explorer's breadcrumb).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T9.1](./summariser-G9-T9.1.md) | A developer sees MSG_KIND_OPTIONS expose all 19 entries _(tracer)_ | — |
| [T9.2](./summariser-G9-T9.2.md) | Selecting subagent-thinking filters the timeline and round-trips `?msg=` | [T9.1](./summariser-G9-T9.1.md) |
| [T9.3](./summariser-G9-T9.3.md) | The scope composition is retired; filter matches the full kind value | [T9.1](./summariser-G9-T9.1.md) |
| [T9.4](./summariser-G9-T9.4.md) | The e2e spec covers the 19-option flat dropdown | [T9.1](./summariser-G9-T9.1.md), [T9.2](./summariser-G9-T9.2.md) |
| [T9.5](./summariser-G9-T9.5.md) | A user sees the session's 3-lens summary card on SessionDetail | [T9.1](./summariser-G9-T9.1.md), [T7.1](./summariser-G7-T7.1.md) |
| [T9.6](./summariser-G9-T9.6.md) | A user navigates the scope lineage via the ScopeBreadcrumb on SessionDetail | [T9.1](./summariser-G9-T9.1.md), [T8.2](./summariser-G8-T8.2.md) |
