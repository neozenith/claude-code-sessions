# G8: Summaries explorer page

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G7](./summariser-G7.md)
> - **Blocks:** [G9](./summariser-G9.md), [G10](./summariser-G10.md)
> - **Prev:** [G7](./summariser-G7.md)
> - **Next:** [G9](./summariser-G9.md)

A new React page that navigates the variable-depth scope trie (root → domain → …subdomains… → project → session) at a chosen time grain, reading the three lenses and drilling up/down via a breadcrumb + child links — all state in the URL. Built before the benchmark because the [G10](./summariser-G10.md) human-evaluation tier reads summaries here.

## Context
Pages register in `App.tsx` (route) + `Layout.tsx` (nav item); global filters via `useFilters`, page-local state via `useSearchParams` (CLAUDE.md URL-as-state rules). The Performance page (`pages/Performance.tsx`) is the template for a filtered analytics page; e2e specs live in `frontend/e2e/`.
Scope is the variable-depth `scope_path` (G1); the page reads `list_scope_children` (G7) to render the next level and provides the **scope breadcrumb** component reused by SessionDetail (G9). During evaluation it exposes a strategy/model selector ([ADR7.2](./summariser-G7.md)); the selector is removed post-collapse. Summaries are prose (three lenses), so this page is card/text oriented rather than Plotly-chart oriented.

## Outputs
| File | Change |
|------|--------|
| `frontend/src/pages/Summaries.tsx` (tsx, new) | `?path=` scope breadcrumb + child-scope list, `?grain=`/`?bucket=` selectors, optional `?strategy=`/`?model=` eval selectors, three-lens cards, drilldown links. |
| `frontend/src/components/ScopeBreadcrumb.tsx` (tsx, new) | Reusable up/down lineage breadcrumb over `scope_path` (root → … → project → session), shared with SessionDetail (G9). |
| `frontend/src/App.tsx` (tsx) | Route `/summaries`. |
| `frontend/src/components/Layout.tsx` (tsx) | Nav item (Lucide icon). |
| `frontend/src/lib/api-client.ts` (ts) | Typed `getScopeSummary` / `getSessionSummary` / `listScopeChildren` / `listSummaryVariants` methods + response types. |
| `frontend/e2e/summaries.spec.ts` (ts, new) | Page renders the three lenses; scope/grain/strategy deep-link via URL; breadcrumb drills up and down. |

## ADR8.1: Page-local `?path=`/`?grain=`/`?bucket=`, reuse global `?project=`/`?days=`
- **Decision:** Scope path, grain, bucket (and the eval-only `strategy`/`model`) are page-local params managed via `useSearchParams`; the global `?project=`/`?days=` filters are reused through `useFilters`. Page-local params are omitted at their defaults and do not leak into sidebar nav links.
- **Why:** Exactly the documented URL-as-state global-vs-page-local split (CLAUDE.md), enabling deep links and deterministic e2e setup.
- **Rejected:** A single composite param (breaks the established split and the `filterSearchString` nav-link contract).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T8.1](./summariser-G8-T8.1.md) | A user opens /summaries and sees the three lenses for the default scope _(tracer)_ | [T7.1](./summariser-G7-T7.1.md) |
| [T8.2](./summariser-G8-T8.2.md) | ScopeBreadcrumb renders the root→…→project lineage | [T8.1](./summariser-G8-T8.1.md) |
| [T8.3](./summariser-G8-T8.3.md) | A user drills down via child links and up via ancestor crumbs | [T8.2](./summariser-G8-T8.2.md), [T7.6](./summariser-G7-T7.6.md) |
| [T8.4](./summariser-G8-T8.4.md) | A user deep-links ?path=&grain= and lands on that scope/grain | [T8.3](./summariser-G8-T8.3.md) |
| [T8.5](./summariser-G8-T8.5.md) | A user switches ?strategy=/?model= and the variant changes | [T8.4](./summariser-G8-T8.4.md), [T7.7](./summariser-G7-T7.7.md) |
| [T8.6](./summariser-G8-T8.6.md) | An un-summarised scope shows the not_summarised empty state | [T8.4](./summariser-G8-T8.4.md), [T7.4](./summariser-G7-T7.4.md) |
