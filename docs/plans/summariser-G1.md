# G1: Variable-depth project hierarchy resolution

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** none
> - **Blocks:** [G3](./summariser-G3.md), [G7](./summariser-G7.md)
> - **Next:** [G2](./summariser-G2.md)

Resolves each project to its full home-relative path and the ordered chain of ancestor aggregation scopes (root → domain → …subdomains… → project), so summaries can roll up at every level of a variable-depth hierarchy.

## Context
Aggregation scope is **any prefix of a project's home-relative path**, and the hierarchy is variable depth:
`play`/`work`/`foss` are depth-1 (children are projects directly); `clients/<client_name>` is depth-2 (a client groups many projects); a domain may nest deeper until it reaches the **project**, which is the logical container of **sessions**.
Required aggregations: per project, per client (`clients/<name>`), across all clients (`clients`), per `work`/`play`/`foss`, and across all domains (root).
`extract_domain` (`config.py:39-58`) returns only the first segment — too flat — and naive dash-splitting of the encoded `project_id` is unsafe because segment names contain dashes; the authoritative path comes from `ProjectResolver`/`ProjectInfo.project_path` (`project_resolver.py:37-224`, sourced from `sessions-index.json`).

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/project_resolver.py` (py) | `scope_path_of(project_id) -> str` (home-relative project path, `/`-joined) and `ancestor_scopes(project_id) -> list[str]` (`['', 'clients', 'clients/acme', 'clients/acme/app']`, root first), derived from the resolved `project_path`. |
| `src/claude_code_sessions/config.py` (py) | Keep `extract_domain` for `BLOCKED_DOMAINS`; document that the hierarchy supersedes it for aggregation. |
| `tests/` (py) | Unit tests pinning depth-1 (`play/foo`) and depth-2 (`clients/acme/app`) ancestor chains, and that dashed segment names resolve via the authoritative path, not split. |

## Key logic
```python
def scope_path_of(project_id: str) -> str:
    """Home-relative '/'-joined project path, e.g. 'clients/acme/app' — from the
    resolved project_path, never from splitting the dash-encoded id."""

def ancestor_scopes(project_id: str) -> list[str]:
    """Root-first inclusive prefix chain: '' (all) → 'clients' → 'clients/acme'
    → 'clients/acme/app'. Every element is an aggregation scope_path."""
```

## ADR1.1: Domains are a variable-depth path hierarchy
- **Decision:** Aggregation scope is any prefix of a project's home-relative path. The roll-up tree is root (all domains) → first-segment domain → zero or more subdomain levels → project → session, with **variable depth per branch** (`play` depth 1, `clients/<name>` depth 2, deeper allowed). Scopes are derived from the resolved `ProjectInfo.project_path`, not from dash-splitting the encoded id.
- **Why:** The user aggregates at every level — per client and across all clients, per work/play/foss, and across all domains — so a fixed `{project, domain, all}` trichotomy is insufficient; a prefix-trie over the real paths models it exactly and extends to any future nesting (e.g. `work/<org>`).
- **Rejected:** Flat first-segment domain only (can't express per-client); hardcoding `clients` as two-deep (the user wants the general variable-depth rule, with `clients` merely illustrating the extension point); naive dash-split of `project_id` (mis-buckets dashed segment names).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T1.1](./summariser-G1-T1.1.md) | A depth-1 project resolves its home-relative scope path _(tracer)_ | — |
| [T1.2](./summariser-G1-T1.2.md) | A depth-1 project yields its root-first ancestor chain | [T1.1](./summariser-G1-T1.1.md) |
| [T1.3](./summariser-G1-T1.3.md) | A depth-2 project yields a four-level ancestor chain | [T1.2](./summariser-G1-T1.2.md) |
| [T1.4](./summariser-G1-T1.4.md) | A dashed segment resolves via the authoritative path, not id-split | [T1.3](./summariser-G1-T1.3.md) |
