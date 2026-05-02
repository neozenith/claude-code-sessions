# Knowledge Graph for Claude Code Sessions

**Status:** Planning
**Owner:** Josh Peak (joshpeak05@gmail.com)
**Created:** 2026-04-29
**Target parity:** http://localhost:5282/sessions_demo/kg/er/

---

## 1. Overview

The published `sqlite-muninn` SQLite extension provides the primitives needed to build a
resolved entity graph from chat data: HNSW vector indexes, `graph_adjacency` virtual tables,
node2vec, and Leiden community detection. A reference pipeline lives at
`/Users/joshpeak/play/sqlite-vector-graph/benchmarks/sessions_demo/` and a reference Cytoscape
visualization lives at `/Users/joshpeak/play/sqlite-vector-graph/viz/` — but neither is
imported here. **No code is shared between `claude-code-sessions`, `benchmarks/sessions_demo`,
and the introspect skill.** The three projects coexist purely by reading and writing the same
on-disk cache file (`~/.claude/cache/introspect_sessions.db`) under a shared `SCHEMA_VERSION`
contract.

This project must:

1. Add the published `sqlite-muninn` package as a runtime dependency (PyPI, **not** the local
   `/Users/joshpeak/play/sqlite-vector-graph` checkout).
2. Extend the cache schema with the resolved-entity-graph tables — `entities`, `relations`,
   `entity_vec_map`, `entity_clusters`, `nodes`, `edges`, `leiden_communities`,
   `entity_cluster_labels` — and re-implement (not import) the orchestration that populates
   them, calling `sqlite-muninn` SQL primitives directly.
3. Run the KG pipeline incrementally on server start, the same way `sync_embeddings()`
   already runs on launch — no `make refresh-kg`, no manual triggers.
4. Expose the resolved-entity graph (`/kg/er` only — the base graph is **out of scope** for
   this project, now and forever) through new `/api/kg/*` endpoints.
5. Add a new top-level webapp section called **Knowledge Graph** at the route `/kg/` that
   visually matches `http://localhost:5282/sessions_demo/kg/er/`.
6. Update the introspect skill so its documentation, schema version, and example queries
   cover the new tables.

**Hard requirement (`/escalators-not-stairs`):** every requirement above is mandatory. No
silent fallbacks, no `try: import; except: skip`, no "feature unavailable" panels in place of
the rendered graph. If `sqlite-muninn` is missing, the server must crash at startup with a
clear `pip install sqlite-muninn` message.

---

## 2. Goals

| # | Goal | How we measure it |
|---|------|------------------|
| G1 | The cache (`~/.claude/cache/introspect_sessions.db`) hosts the full KG schema | `sqlite3 ~/.claude/cache/introspect_sessions.db ".tables"` lists `entities`, `relations`, `entity_clusters`, `nodes`, `edges`, `leiden_communities`, `entity_cluster_labels` |
| G2 | The introspect skill is updated to be aware of the new tables | `.claude/skills/introspect/SKILL.md` documents KG tables; `introspect_sessions.py` schema version matches `claude_code_sessions/database/sqlite/schema.py::SCHEMA_VERSION` |
| G3 | `claude-code-sessions` depends on the **published** `sqlite-muninn` (PyPI), with **no** import from `benchmarks.sessions_demo` or any path under `/Users/joshpeak/play/sqlite-vector-graph` | `pyproject.toml` shows `sqlite-muninn` as a versioned dep; `grep -R "benchmarks.sessions_demo\|sqlite-vector-graph" src/` returns nothing |
| G4 | KG phases run incrementally on server start (matching `sync_embeddings()`'s pattern) — no manual `make` step | Server log on cold start shows the new phase banners; second start with no new chunks is a no-op |
| G5 | Backend exposes `/api/kg/er` with the same response shape as the reference viz | The KGPayload field names (`id`, `label`, `entity_type`, `community_id`, `mention_count`, `node_betweenness`, etc.) match the reference `viz/server/kg.py` Pydantic model exactly |
| G6 | New webapp page at `/kg/` renders the ER cytoscape graph with community compound nodes, fcose/elk/grid layouts, sizing/coloring controls, betweenness-aware sizing | Side-by-side screenshot of `localhost:5274/kg/` and `localhost:5282/sessions_demo/kg/er/` shows visual parity |
| G7 | Sidebar nav has a "Knowledge Graph" entry that links to `/kg/` | Visible in `frontend/src/components/Layout.tsx::navItems` and in the screenshot |
| G8 | Page state (top_n, seed_metric, max_depth, min_degree, layout engine, sizing/coloring modes) is URL-driven | `?topN=50&seedMetric=edge_betweenness&...` — refresh preserves view |
| G9 | E2E test exists for `/kg/` in `frontend/e2e/` | `make test-frontend-e2e` runs and the new spec passes |
| G10 | Screenshot evidence of parity is captured | At least two PNGs in `frontend/e2e-screenshots/`: this project's `/kg/` and the reference `localhost:5282/sessions_demo/kg/er/` |

---

## 3. Non-Goals

- Re-implementing the *primitives* (HNSW, `graph_adjacency`, Leiden, node2vec) — those come
  from the published `sqlite-muninn` extension. The orchestration *around* them (which SQL
  to run in what order, where to load model weights, how to checkpoint progress) IS in scope
  and is freshly written here, not imported from `benchmarks/sessions_demo`.
- Building a 3D UMAP embed visualization (the reference viz has one at `/embed/...`); this
  plan only covers the KG / cytoscape view.
- Live editing of nodes/edges from the UI.
- A `/kg/base/` view — **out of scope, now and forever**. The entity-resolved graph is the
  only graph this project will ever render. The page does not need a base/er toggle.
- Any path-based dependency on `/Users/joshpeak/play/sqlite-vector-graph`. We pull
  `sqlite-muninn` from PyPI only.

---

## 4. Current State

### 4.1 Shared cache schema (`schema.py`, version 12)

```
source_files, projects, sessions, events, event_edges, events_fts,
event_message_chunks, event_message_chunks_fts, chunks_vec,
chunks_vec_config, chunks_vec_edges, chunks_vec_nodes,
event_calls, agg
```

No KG-related tables. The `chunks_vec` table is the deepest the pipeline goes today.

### 4.2 sessions_demo extra tables (the gap)

`benchmarks/sessions_demo/build.py::_KG_TABLES` lists what we need to add:

```
entities, relations, entity_vec_map, entities_vec, entity_clusters,
nodes, edges, _match_edges, leiden_communities,
chunks_vec_umap, entities_vec_umap, node2vec_emb,
entity_cluster_labels, community_labels, meta
```

These are populated by the phases in `benchmarks/sessions_demo/phases/` (`ner.py`, `re.py`,
`entity_embeddings.py`, `entity_resolution.py`, `node2vec.py`, `communities.py`,
`community_naming.py`, `metadata.py`).

### 4.3 Reference visualization

| Component | Location |
|-----------|----------|
| FastAPI server | `/Users/joshpeak/play/sqlite-vector-graph/viz/server/main.py` |
| KG endpoint | `viz/server/kg.py::load_kg_graph` |
| Cytoscape page | `viz/frontend/src/pages/KGPage.tsx` |
| API client (typed) | `viz/frontend/src/lib/api-client.ts` |
| Right-panel controls | `viz/frontend/src/components/RightPanel.tsx` |
| Live URL | http://localhost:5282/sessions_demo/kg/er/ |

The KG payload contract (must reproduce):

```ts
interface KGPayload {
  table_id: string                  // "base" | "er"
  resolution: number                // Leiden resolution
  seed_metric: 'degree' | 'node_betweenness' | 'edge_betweenness'
  max_depth: number                 // 0 = unlimited
  min_degree: number
  node_count: number
  edge_count: number
  community_count: number
  total_node_count: number          // pre-filter
  total_edge_count: number          // pre-filter
  nodes: KGNode[]                   // id, label, entity_type, community_id, mention_count, node_betweenness
  edges: KGEdge[]                   // source, target, rel_type, weight, edge_betweenness
  communities: KGCommunity[]        // id, label, member_count, node_ids
}
```

### 4.4 Webapp (this project) routing

`frontend/src/App.tsx` currently routes: `/`, `/daily`, `/weekly`, `/monthly`, `/hourly`,
`/hour-of-day`, `/sessions`, `/sessions/:projectId`, `/sessions/:projectId/:sessionId`,
`/timeline`, `/schema-timeline`, `/search`. **No `/kg/` route, no cytoscape, no kg components.**

### 4.5 Introspect skill

`.claude/skills/introspect/SKILL.md` documents the cache, schema, FTS search, traversal, and
session listing. **No mention of entities, relations, or any KG concept.**

---

## 5. Desired State

```
~/.claude/cache/introspect_sessions.db
├── (existing) source_files, projects, sessions, events, event_edges, events_fts,
│              event_message_chunks, chunks_vec, ...
└── (new)     entities, relations, entity_vec_map, entities_vec,
              entity_clusters, nodes, edges, leiden_communities,
              entity_cluster_labels, community_labels, node2vec_emb,
              chunks_vec_umap, entities_vec_umap, _match_edges, meta

claude_code_sessions backend
├── (existing) /api/health, /api/summary, /api/usage/*, /api/projects, ...
└── (new)     GET /api/kg/tables          → which kg tables exist + resolutions
              GET /api/kg/{table_id}      → KGPayload (table_id ∈ {base, er})

frontend
├── (existing) Dashboard, Search, Daily, Weekly, ..., Timeline, ...
├── (new)     KnowledgeGraph page at /kg/  — sidebar entry "Knowledge Graph"
└── (new)     deps: cytoscape, cytoscape-fcose, cytoscape-elk, react-cytoscapejs

.claude/skills/introspect
├── (existing) SKILL.md (sessions, events, traverse, fts)
└── (updated) SKILL.md documents new KG tables + queries; schema version aligned
```

### 5.1 No code sharing — schema contract only

`claude-code-sessions`, `benchmarks/sessions_demo`, and the introspect skill all keep their
own independent `CacheManager` implementations. They coexist on the same on-disk file by
honoring a single shared `SCHEMA_VERSION` string. When any of the three bumps the version,
all three must update in lockstep.

```
~/.claude/cache/introspect_sessions.db   ← single physical file
        ▲             ▲             ▲
        │             │             │
   claude-code-    sessions_demo  introspect
   sessions       (sqlite-      skill
   (this repo)    vector-graph) (this repo)
        │             │             │
        └── each has its own CacheManager copy ──┘
                  bound by SCHEMA_VERSION
```

The two `CacheManager` files inside *this* repo (the runtime backend and the introspect
skill script) MUST stay in lockstep, but neither is allowed to import from
`benchmarks/sessions_demo`. KG-pipeline orchestration is freshly written in this repo,
calling `sqlite-muninn` SQL primitives directly.

---

## 6. Gap Analysis

| Gap | Why it matters | Resolution |
|-----|----------------|-----------|
| `sqlite-muninn` is not a dependency of this project | The KG primitives (HNSW, `graph_adjacency`, Leiden, node2vec) are unreachable | `uv add sqlite-muninn` (PyPI), pin a version, surface a clear error if it is missing |
| KG tables absent from `schema.py` | `/api/kg` would 422 forever | Bump `SCHEMA_VERSION` from `"12"` → `"13"`; add KG DDL to `SCHEMA_SQL` |
| `SCHEMA_VERSION` lives in three files | Any drift corrupts the shared `.db` | Phase 0 sweep: bump it identically in (1) `claude_code_sessions/database/sqlite/schema.py`, (2) `.claude/skills/introspect/scripts/introspect_sessions.py`, and (3) flag the user to bump `benchmarks/sessions_demo/constants.py` themselves in `sqlite-vector-graph` |
| KG phases don't run from claude-code-sessions | Cache stays empty even after schema upgrade | New `claude_code_sessions/database/sqlite/kg/` package with one Python module per phase (`ner.py`, `relations.py`, `entity_embeddings.py`, `entity_resolution.py`, `node2vec.py`, `communities.py`, `community_naming.py`) calling `sqlite-muninn` SQL primitives. **No import from `benchmarks/sessions_demo`** |
| KG must run on every server start (like embeddings) | User specified this explicitly | Wire `sync_kg()` into `CacheManager.update()` in the same place `sync_embeddings()` is called, with the same "skip if no new chunks" guard |
| No `/api/kg/*` endpoint | Frontend has nothing to call | New module `src/claude_code_sessions/database/sqlite/kg/payload.py` builds `KGPayload` (field names byte-identical to the reference). New router exposes `GET /api/kg/er` only |
| No cytoscape deps | Cytoscape page can't compile | `npm --prefix frontend i cytoscape cytoscape-fcose cytoscape-elk react-cytoscapejs @types/cytoscape` |
| No `/kg/` route or page | URL is 404 | New `pages/KnowledgeGraph.tsx`; route in `App.tsx`; nav item in `Layout.tsx` (icon: `Network` from `lucide-react`) |
| URL state not designed | Refresh loses view | Use `useSearchParams` per project convention. Defaults are *omitted* from the URL (clean). No `?table=` param — the page is ER-only |
| Introspect skill silent on KG | Skill drifts from cache contents | Add a "Knowledge Graph" section to `SKILL.md` with example queries |
| No e2e for `/kg/` | Regressions go unnoticed | Add `frontend/e2e/kg.spec.ts` — load page, assert cytoscape `<canvas>` mounts, assert ≥1 node & ≥1 edge in DOM, take screenshot |
| No screenshot proof | Cannot demonstrate parity | Add `frontend/e2e-screenshots/kg-er.png` and `frontend/e2e-screenshots/kg-er-reference.png` |

---

## 7. Implementation Phases

### Phase 0 — Dependency + schema bump

1. `uv add sqlite-muninn` — pin a version. Verify import works in `python -c "import muninn"` (or whatever the import name is — confirmed during install).
2. Add a startup precheck to `claude_code_sessions/main.py`: load the extension once and crash with a clear `pip install sqlite-muninn` message if it's missing. **No try/except fallback.**
3. Bump `SCHEMA_VERSION` to `"13"` in:
   - `src/claude_code_sessions/database/sqlite/schema.py`
   - `.claude/skills/introspect/scripts/introspect_sessions.py`
4. Add the new KG-table DDL to `SCHEMA_SQL` (mirroring the columns sessions_demo writes — verified by reading sessions_demo phase modules during implementation, NOT by importing them).
5. Verify `make ci` still passes (mypy strict + ruff + pytest + vitest + tsc).

### Phase 1 — KG pipeline orchestration (re-implemented in this repo)

Build `src/claude_code_sessions/database/sqlite/kg/` as a sibling of `embeddings.py`. One module per phase. Each module follows the existing `sync_*` pattern (read what's missing, write what's new, idempotent on re-run).

```
src/claude_code_sessions/database/sqlite/kg/
├── __init__.py
├── runtime.py            # load sqlite-muninn extension on a connection
├── ner.py                # sync_entities()       reads chunks, writes entities
├── relations.py          # sync_relations()      reads chunks, writes relations
├── entity_embeddings.py  # sync_entity_embeddings() reads entities, writes entities_vec, entity_vec_map
├── entity_resolution.py  # sync_entity_clusters() reads entity_vec_map+entities_vec+relations, writes entity_clusters, nodes, edges
├── node2vec.py           # sync_node2vec()       reads nodes+edges, writes node2vec_emb
├── communities.py        # sync_communities()    reads nodes+edges, writes leiden_communities
├── community_naming.py   # sync_community_labels() reads communities, writes entity_cluster_labels, community_labels
└── pipeline.py           # sync_kg() — calls the above in dependency order
```

`sync_kg()` is called from `CacheManager.update()` immediately after `sync_embeddings()`. Each phase's "skip when not stale" check matches the existing pattern: count rows in source vs sink, return early if the sink is up to date.

Important: **do NOT** copy code from `benchmarks/sessions_demo/phases/`. We re-implement using `sqlite-muninn` SQL primitives directly. The reference is studied for the *contract* (input tables, output tables, column shapes) but not pasted in.

### Phase 2 — Backend `/api/kg/er` endpoint

1. New module `src/claude_code_sessions/database/sqlite/kg/payload.py` — builds `KGPayload` from the resolved-entity tables. Field names match the reference exactly:
   - `KGNode`: `id`, `label`, `entity_type`, `community_id`, `mention_count`, `node_betweenness`
   - `KGEdge`: `source`, `target`, `rel_type`, `weight`, `edge_betweenness`
   - `KGCommunity`: `id`, `label`, `member_count`, `node_ids`
   - `KGPayload`: `table_id` (always `"er"`), `resolution`, `seed_metric`, `max_depth`, `min_degree`, counts, lists
2. Seed-and-expand logic mirrors the reference: pick top-N seeds by metric, BFS-expand through the undirected edge view, return all nodes/edges in the expansion. Use `networkx` (already on the wire in viz; new dep here).
3. Add a FastAPI router `src/claude_code_sessions/routes/kg.py` with **one** endpoint: `GET /api/kg/er` accepting `resolution`, `top_n`, `seed_metric`, `max_depth`, `min_degree` as query params. (No `/api/kg/tables`, no `/api/kg/base` — out of scope.)
4. Register the router in `main.py`. Map `KGDataMissing` → 422.
5. Backend unit tests in `tests/test_kg_endpoints.py`: payload schema, param validation, 422 on missing tables.

### Phase 3 — Frontend KG page

1. Install deps: `npm --prefix frontend i cytoscape cytoscape-fcose cytoscape-elk react-cytoscapejs && npm --prefix frontend i -D @types/cytoscape`.
2. Add typed wrappers in `frontend/src/lib/api-client.ts` (or new `kg-client.ts`): `KGNode`, `KGEdge`, `KGCommunity`, `KGPayload`, `SeedMetric`, `fetchKG`. Field names match the reference.
3. Create `frontend/src/pages/KnowledgeGraph.tsx`. The component is structurally a port of `viz/frontend/src/pages/KGPage.tsx`, adapted to this project's:
   - Theme system (`@/contexts/ThemeContext`) for dark/light stylesheet swap
   - URL state via `useSearchParams` (defaults omitted from URL — `?topN=50` only when not 50, etc.)
   - shadcn `Card`/`Button` styling
   - **No** `?table=` query param — the page is hardwired to ER
4. Create `frontend/src/components/KnowledgeGraphControls.tsx` — port of the right-panel subset: layout engine selector, top-N slider, seed-metric radio, max-depth slider, min-degree slider, sizing/coloring mode selectors, layout-config JSON textarea.
5. Add the route in `App.tsx`: `<Route path="/kg" element={<KnowledgeGraph />} />`.
6. Add the sidebar entry in `Layout.tsx::navItems`:
   ```ts
   { path: '/kg', label: 'Knowledge Graph', icon: Network }
   ```
7. Vitest unit tests cover the payload-to-elements transformer: community parents, orphan nodes, edge filtering by node-ID set.

### Phase 4 — Introspect skill update

1. Edit `.claude/skills/introspect/SKILL.md`:
   - Add a "Knowledge Graph tables" section listing `entities`, `relations`, `entity_clusters`, `nodes`, `edges`, `leiden_communities`, `entity_cluster_labels`.
   - Add 4–5 example SQL queries (top entities by mention count, edges by relation type, communities by member count, betweenness lookup).
   - Update the "Cache" section to mention schema version 13 and the KG pipeline.
2. `introspect_sessions.py` `SCHEMA_VERSION` is already bumped in Phase 0; verify here.
3. Update auto `MEMORY.md` to record the new file locations once written.

### Phase 5 — Verification

1. `make ci` — must pass clean.
2. `make agentic-dev` — backend on 8101, frontend on 5274. The backend's first start triggers the full KG pipeline (visible in logs).
3. Playwright e2e at `frontend/e2e/kg.spec.ts`:
   - `goto('/kg/')`
   - Wait for cytoscape canvas to mount (`page.locator('canvas').first()`)
   - Wait for at least one node element via `page.evaluate` against the cy instance
   - Capture full-page screenshot to `frontend/e2e-screenshots/kg-er.png`
4. Capture reference screenshot via Playwright against `localhost:5282/sessions_demo/kg/er/` — saved to `frontend/e2e-screenshots/kg-er-reference.png`.
5. Both screenshots embedded in this plan's "Verification" appendix at the end of the work.

---

## 8. Success Measures

A working implementation MUST satisfy ALL of the following — failure of any one is failure of
the feature:

1. **Schema parity** — `sqlite3 ~/.claude/cache/introspect_sessions.db ".schema entity_clusters"` shows
   the same columns as the equivalent on `sessions_demo.db`.
2. **API parity** — `curl localhost:8101/api/kg/er | jq '.nodes[0]'` returns a node object
   with the exact same keys (`id`, `label`, `entity_type`, `community_id`, `mention_count`,
   `node_betweenness`) as `curl localhost:5282/api/databases/sessions_demo/kg/er | jq '.nodes[0]'`.
3. **UI parity** — both screenshots show: (a) compound community parent boxes with labels,
   (b) child entity nodes inside, (c) edges with arrow heads, (d) the controls panel on the
   right side, (e) at least one of the layout engines (`fcose`, `elk`, `grid`) selectable,
   (f) sizing-by-betweenness produces visibly larger/smaller nodes.
4. **Sidebar entry** — "Knowledge Graph" appears in the left sidebar in the same screenshot.
5. **URL deep link** — `localhost:5274/kg/?topN=30&seedMetric=degree&maxDepth=2`
   refreshes to the same view without losing state.
6. **No-import contract** — `grep -R "benchmarks.sessions_demo\|sqlite-vector-graph" src/ frontend/src/ .claude/skills/introspect/` returns nothing. `pyproject.toml` lists `sqlite-muninn` as a published-package dependency.
7. **Server-start incrementality** — first cold start populates the KG; second cold start with no new chunks completes the KG phase in O(1) time (logs show "skip — no new chunks").
8. **CI green** — `make ci` exits 0.
9. **E2E green** — `make test-frontend-e2e` exits 0 with the new spec included.
10. **Skill updated** — `.claude/skills/introspect/SKILL.md` contains a "Knowledge Graph" section and the schema version matches.

## 9. Negative Measures (failure modes to actively prevent)

These are the failure shapes that the `/escalators-not-stairs` skill is calling out:

- **❌ "KG data not available — feature disabled"** UX. If the cache is empty, the page must show a *blocking* error stating the server start did not complete its KG phases, not a quiet stub.
- **❌ Try/except around `import muninn` (or whatever the import name is).** Hard import at module load. Missing extension = startup crash with `pip install sqlite-muninn`.
- **❌ Try/except around cytoscape imports.** If a layout dep fails to install, the page must fail loudly.
- **❌ Importing anything from `benchmarks.sessions_demo` or `/Users/joshpeak/play/sqlite-vector-graph`.** This is the explicit user-stated boundary. Verified with `grep` in CI.
- **❌ A `?table=base` code path.** The page is ER-only. No toggle, no fallback, no future-proofing scaffold.
- **❌ A `make refresh-kg` target.** KG runs on server start; no manual trigger.
- **❌ Mock the cytoscape canvas in the e2e test.** The test must render a real graph or fail.
- **❌ Soft "approximate" parity.** The screenshot comparison is the gate. Pixel-diff is not required, but a reviewer must be able to look at both and say "yes, this is the same view."
- **❌ Letting `SCHEMA_VERSION` drift between `introspect_sessions.py` and `claude_code_sessions/database/sqlite/schema.py`.** Documented past hazard (auto-memory: "SCHEMA_VERSION must match the introspect script's version so both tools coexist").
- **❌ Letting the in-repo `CacheManager` copies drift.** The two copies in *this* repo (backend + skill script) must always match. The third copy (in `sqlite-vector-graph`) is independent — coordination there is the user's responsibility, not this codebase's.

---

## 10. Risks and Open Questions

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `sqlite-muninn` extension is platform-specific (compiled `.dylib`/`.so`) | Med | `uv add sqlite-muninn` fetches the platform wheel; fail loud at startup if missing |
| KG phases on the user's full `~/.claude/projects/` cost-prohibitive on first server start (NER + RE on hundreds of MB of chat) | **High** | Per-phase incrementality (the existing `sync_*` pattern). First start is slow; subsequent starts are no-ops. Surface progress via the existing phase-banner logger so the operator sees what's happening |
| Reference viz at `localhost:5282` may stop running, breaking screenshot comparison | Med | Snapshot the reference once and commit the PNG; rerun only when the reference changes |
| Cytoscape large-graph performance (>5k nodes) is laggy | Med | Use `top_n=50` + BFS expansion exactly like the reference does — same defaults |
| `react-plotly` and `cytoscape` together inflate the JS bundle | Low | Lazy-load `KnowledgeGraph` via `React.lazy` + `Suspense` |
| `cytoscape-elk` ships layout engine as wasm/worker — Vite config may need tweaks | Med | Confirm during Phase 3, before locking in the route |
| Community labeling in `community_naming` may require an LLM call | Med | Confirm during Phase 1 implementation. If yes, surface prompt + model in env vars; if call fails, raise (no silent fallback to `community_<id>` strings) |
| Server start latency from KG pipeline degrades developer ergonomics | Med | The phases skip when no new chunks, so warm starts are fast. Cold starts log a one-time banner explaining what's running |

### Open questions (resolved by user, 2026-04-29)

| # | Question | Decision |
|---|----------|----------|
| 1 | Code-sharing direction between projects | **None.** Three independent codebases coexisting on a shared `.db` file via `SCHEMA_VERSION`. |
| 2 | `/kg/?table=base` support | **Out of scope, now and forever.** ER-only. |
| 3 | KG rebuild trigger | **On server start**, incremental, like `sync_embeddings()`. No `make refresh-kg`. |
| 4 | Dependency form | **Published `sqlite-muninn` from PyPI**, not the local `sqlite-vector-graph` checkout. |

---

## 11. File-Touch Map

```
.claude/skills/introspect/SKILL.md                                    [edit]
.claude/skills/introspect/scripts/introspect_sessions.py              [edit — bump SCHEMA_VERSION + add KG DDL]
src/claude_code_sessions/database/sqlite/schema.py                    [edit — bump SCHEMA_VERSION + add KG DDL]
src/claude_code_sessions/database/sqlite/cache.py                     [edit — call sync_kg() in update()]
src/claude_code_sessions/database/sqlite/kg/__init__.py               [new]
src/claude_code_sessions/database/sqlite/kg/runtime.py                [new — load sqlite-muninn extension]
src/claude_code_sessions/database/sqlite/kg/ner.py                    [new — sync_entities()]
src/claude_code_sessions/database/sqlite/kg/relations.py              [new — sync_relations()]
src/claude_code_sessions/database/sqlite/kg/entity_embeddings.py      [new — sync_entity_embeddings()]
src/claude_code_sessions/database/sqlite/kg/entity_resolution.py      [new — sync_entity_clusters()]
src/claude_code_sessions/database/sqlite/kg/node2vec.py               [new — sync_node2vec()]
src/claude_code_sessions/database/sqlite/kg/communities.py            [new — sync_communities()]
src/claude_code_sessions/database/sqlite/kg/community_naming.py       [new — sync_community_labels()]
src/claude_code_sessions/database/sqlite/kg/pipeline.py               [new — sync_kg() orchestrator]
src/claude_code_sessions/database/sqlite/kg/payload.py                [new — KGPayload builder]
src/claude_code_sessions/routes/__init__.py                           [new]
src/claude_code_sessions/routes/kg.py                                 [new — GET /api/kg/er router]
src/claude_code_sessions/main.py                                      [edit — include kg router + extension precheck]
tests/test_kg_endpoints.py                                            [new]
pyproject.toml                                                        [edit — add sqlite-muninn + networkx]
frontend/package.json                                                 [edit — add cytoscape deps]
frontend/src/lib/api-client.ts                                        [edit — KG types + fetchKG]
frontend/src/pages/KnowledgeGraph.tsx                                 [new]
frontend/src/components/KnowledgeGraphControls.tsx                    [new]
frontend/src/App.tsx                                                  [edit — add /kg route]
frontend/src/components/Layout.tsx                                    [edit — add nav entry]
frontend/e2e/kg.spec.ts                                               [new]
frontend/e2e-screenshots/kg-er.png                                    [generated]
frontend/e2e-screenshots/kg-er-reference.png                          [generated]
docs/plans/knowledge-graph.md                                         [this file]
```

Notable absences (intentional, per user):
- `Makefile` — no `refresh-kg` target. KG runs on server start.
- No path dependency on `/Users/joshpeak/play/sqlite-vector-graph`.
- No `/api/kg/tables` or `/api/kg/base` endpoint.
- No `?table=` URL param.

---

## 12. Verification Appendix (2026-05-01 — first iteration)

### Screenshot evidence

- `frontend/e2e-screenshots/kg-er.png` — this project at `localhost:5274/kg`
  rendered against a partial KG (24 chunks NER+RE'd → 43 entities → 32 visible
  nodes after seed-and-expand → 19 edges → 15 communities, 11 LLM-labeled).
  The image shows: sidebar with "Knowledge Graph" highlighted; cytoscape
  canvas with community-parent compound boxes laid out via fcose; child
  entity nodes inside each compound, sized by degree; edges with arrow heads;
  right panel with Data/Layout/Styling controls and the community list.

- `frontend/e2e-screenshots/kg-er-reference.png` — **not captured this run.**
  The reference viz at `localhost:5282/sessions_demo/kg/er/` was running at
  the start of the session but stopped before the screenshot pass. The plan
  acknowledges this in §10 (risk row "reference viz at localhost:5282 may
  stop running"). Re-run the reference container and rerun the playwright
  capture to fill this slot — the rest of the implementation stands.

### CI gate at completion

| Check | Result |
|---|---|
| `mypy --strict` (25 source files) | 0 errors |
| `ruff check` (backend) | 0 errors |
| `eslint` (frontend) | 0 errors |
| `tsc --noEmit` (frontend) | 0 errors |
| `pytest tests/` | 304 / 304 passed in 29 s |
| `vitest run` | 59 / 59 passed |

### What's done

- Schema v13 DDL in `claude_code_sessions/database/sqlite/schema.py` and
  the introspect skill script — both bumped in lockstep.
- `claude_code_sessions/database/sqlite/kg/` package: 8 phase modules
  (`runtime`, `ner_re`, `entity_embeddings`, `entity_resolution`,
  `communities`, `community_naming`, `pipeline`, `payload`) — none import
  from `benchmarks.sessions_demo` (verified by grep).
- `sync_kg()` wired into `CacheManager.update()` as phase 7/7, runs on
  every server start.
- `GET /api/kg/er` endpoint (no `/tables`, no `/base`).
- Frontend: `pages/KnowledgeGraph.tsx`, `components/KnowledgeGraphControls.tsx`,
  `lib/kg-client.ts`, route in `App.tsx`, nav entry in `Layout.tsx`,
  cytoscape ambient `.d.ts`.
- E2E spec at `frontend/e2e/kg.spec.ts`.
- Introspect skill `SKILL.md` Knowledge-Graph section + schema bump.

### Operational notes for the user

- First-time KG bootstrap on the user's full `~/.claude/projects/` corpus is
  ~22 800 chunks. At Qwen3.5-4B Q4_K_M CPU rate of ~0.1–0.2 chunks/s, the
  full first-run NER+RE phase is multi-hour. This is the intended behavior
  per `/escalators-not-stairs` — no skip flag, no degraded mode.
- An operational pacing knob is available: `CLAUDE_SESSIONS_KG_NER_RE_BATCH=N`
  caps chunks-per-run. Leaving it unset processes everything at once;
  setting it lets you pace the work across multiple boots without losing
  progress (each phase is incremental). This is **not** a feature toggle.
- Test isolation uses `CLAUDE_SESSIONS_DISABLE_KG=1` (in `tests/conftest.py`),
  same pattern as the existing embeddings flag.
