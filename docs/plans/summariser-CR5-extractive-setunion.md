# CR5: Extractive set-union rollup with frequency-weighting (alternative reduce operator)

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request / queued experiment (alternative to the abstractive merge family)
> - **Discovered in:** the ADR3.2 round-2 investigation — abstractive merges (strict/flat/reground)
>   overflow context, drift across tiers, and lose information at high compression. A "summaries of
>   summaries" tier collapses a whole month×all-projects into one narrow blurb (see Motivation).
> - **Status:** **IN PROGRESS (2026-06-03)** — promoted to the primary direction. L1 list-extraction
>   + L2 set-union/dedup implemented additively (modules `summary_json.parse_lens_lists`,
>   `summaries.THREE_LENS_LIST_GBNF`, `database/sqlite/claims.py`) with 10 passing unit tests; an
>   end-to-end experiment runner (`scripts/run_claims_experiment.py`) gathers real results into
>   `summariser-CR5-RESULTS.md`. Remaining: query/API + UI surfacing (CR5 step 5) and the
>   head-to-head vs the abstractive 64k baseline.
> - **Relates to:** [CR3](./summariser-CR3.md) (map-reduce — composes, see §5), [CR4](./summariser-SCORING.md)
>   (scoring — this CR needs different metrics), [ADR3.2](./summariser-ADR3.2-merge-strategy.md)
>   (the abstractive family this is an alternative to).

## Motivation

The abstractive rollup family asks an LLM to **rewrite** child summaries into new prose at every
tier. Three measured problems:

1. **Drift / non-associativity.** `summarise(A, summarise(B,C)) ≠ summarise(A,B,C)`. Each tier
   re-compresses, so higher tiers invent or drop content — the exact failure `reground` was bolted on
   to fight (by re-injecting source excerpts, which then *overflow context*).
2. **High-compression loss.** A real root-scope **monthly** rollup (flat, Qwen, 2026-06) reduced an
   entire month across all projects to: *"Add a new selector to capture the mlops_planit tag…"* — one
   arbitrary narrow point standing in for hundreds of sessions.
3. **No salience signal.** Abstractive blending discards *how often* something recurred — which is
   precisely the signal worth surfacing for "become a better architect."

## Sharpened to the primary direction (2026-06-02) — and a schema bug it fixes

This is no longer just an alternative to benchmark; it is the intended design. It also fixes a
**structural bug** in L1 extraction:

- **The bug:** `THREE_LENS_GBNF` makes each lens a single `string`, and `Summary` has three `str`
  fields — so every session is *forced* to emit exactly one task, one pattern, one decision. There is
  no way to say "this session expressed **no** decisions" or "it touched **three** patterns." The
  single-blob lens is wrong by construction.
- **The fix (L1):** each lens becomes a **list of 0..N atomic claims**:
  - `tasks` — the task(s) being attempted (empty / one / many);
  - `decisions_values` — value judgements expressed, esp. where the user explains *the why* in reply
    to the assistant (valuing X over Y); empty / one / many;
  - `patterns` — software/architectural patterns at play, **even if unnamed** (the macro category of
    the problem); empty / one / many.
  - `learnings` — what to carry forward to improve **process** and **skill** and to systematically
    reduce **failure modes** (e.g. "verify n_ctx before a long run", "read the source not the binary
    output"); empty / one / many. This lens turns each session into a retrospective: the dedup +
    COUNT rollup then surfaces *recurring* learnings as the highest-salience process improvements.

### The two tiers

- **L1 = session extraction** → three claim-lists per session (the only tier that calls the LLM to
  *create* content). Empty lists are valid and common.
- **L2+ = every coarser grain** (project → … → root; day → week → month) = **extractive set-union**
  of the child claim-lists with **COUNT attribution**. No re-summarisation; union is associative so
  it is correct at any batch depth (composes with [CR3](./summariser-CR3.md)). COUNT(claim) across
  the grouped children is the repetition/salience signal — "this pattern recurred in 40 sessions."

### Storage / schema (v20 bump) — DECIDED: normalised claims tables

One row per claim (not JSON-in-column) — chosen so COUNT, embedding-based dedup, and provenance
drill-down are first-class. Built **additively** alongside the existing abstractive tables/strategies
(which stay green) until the new path is proven, then the abstractive family is deprecated.

```sql
-- L1: one row per extracted claim
CREATE TABLE session_claims (
    project_id TEXT NOT NULL, session_id TEXT NOT NULL, model TEXT NOT NULL,
    lens TEXT NOT NULL,                 -- 'tasks' | 'patterns' | 'decisions_values' | 'learnings'
    claim_index INTEGER NOT NULL,       -- ordinal within (session,lens); preserves order
    claim TEXT NOT NULL,
    embedding BLOB,                     -- lazily populated for dedup (muninn_embed)
    content_hash TEXT NOT NULL,         -- session freshness guard (ADR2.3)
    generated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session_id, model, lens, claim_index)
);
-- a session with zero claims for a lens simply has no rows for that lens (empty list = no rows)

-- L2+: one row per deduped claim-cluster at a scope×grain×bucket, with salience + provenance
CREATE TABLE rollup_claims (
    strategy TEXT NOT NULL, model TEXT NOT NULL,
    scope_path TEXT NOT NULL, scope_depth INTEGER NOT NULL,
    time_granularity TEXT NOT NULL, time_bucket TEXT NOT NULL,
    lens TEXT NOT NULL,
    claim_index INTEGER NOT NULL,       -- rank within lens (by count desc)
    claim TEXT NOT NULL,                -- cluster representative
    count INTEGER NOT NULL,             -- salience = # of children expressing it
    source_session_ids TEXT NOT NULL,   -- JSON array, provenance / drill-down
    source_hash TEXT NOT NULL, generated_at TEXT NOT NULL,
    PRIMARY KEY (strategy, model, scope_path, time_granularity, time_bucket, lens, claim_index)
);
```

**Build sequence (additive, each a green TDD step):** (1) list-valued GBNF + `parse_lens_lists`;
(2) schema v20 + `session_claims`; (3) `extract_session_claims` (L1 writer); (4) `rollup_claims` +
set-union merger reading session_claims, dedup via `muninn_extract_er`, COUNT + provenance; (5) query/API
+ UI surfacing of counts; (6) benchmark vs the abstractive 64k baseline (dedup precision/recall, salience).



Treat each lens of a summary as a **list of atomic claims** (bullet points), not prose. The rollup
**reduce** becomes:

```
union(child claim-lists) → dedup near-identical claims → COUNT duplicates (salience) → rank/prune
```

- **Not re-summarisation** — claims are collected, not rewritten, so they stay verbatim/grounded.
- **Compression by dedup + pruning**, not lossy paraphrase: keep top-N claims by `count × recency`.
- **COUNT = upvotes**: "this pattern appeared in 40 sessions" is the centrality signal abstractive
  merging throws away (and it's the canonical MapReduce shape — word-count).
- **Provenance**: each claim carries its source session IDs → drill-down + grounding by construction.

### Why this is architecturally better (associativity)

`union` is **associative and commutative**, so the map-reduce partitioning ([CR3](./summariser-CR3.md))
is *trivially correct* at any batching order/depth — no "summary-of-summaries" asymmetry. The reduce
no longer needs the whole subtree in one context window; only the *dedup of similar claims* needs
comparison, and similar claims are few. This **dissolves the context-overflow problem** that the
n_ctx/excerpt-budget work has been fighting all along, rather than patching it.

## Dedup engine — reuse `muninn_extract_er` (prior art in `sqlite-vector-graph/src/llama_er.c`)

Claim-dedup *is* entity resolution where the "entity name" is a bullet-point claim. The ER pipeline
already implements the cheap→expensive cascade we want:

1. **KNN blocking (HNSW)** — only compare embedding-near claim pairs (avoid O(n²)).
2. **Scoring cascade (pure C)** — exact match → `1.0`; lowercase-exact → `0.9`; else
   `jw_weight·JaroWinkler + (1−jw_weight)·cosine`. Most merges resolve here with **zero LLM calls**.
3. **Optional LLM judge on the borderline band** — only when `borderline_delta > 0`, only for pairs
   scoring in `[match_threshold − borderline_delta, match_threshold]`. The "fractional last-resort"
   cost knob.
4. **Leiden clustering + edge-betweenness cleanup** — group claims into dedup clusters and cut weak
   bridges so `A~B~C` chains don't over-merge when `A≁C`.

Knobs (`dist_threshold`, `jw_weight`, `borderline_delta`, `eb_threshold`) are exactly the tuning
surface for "how aggressive is the dedup, and how much LLM budget." A cluster → one representative
claim + `count` (sum of member provenance) + merged source IDs.

## Scope of work

| Ticket | Behaviour |
|--------|-----------|
| CR5.1 | **Claim schema** — session extraction emits each lens as a list of atomic claims (≤~1 sentence each) with source session IDs, instead of one prose blob. (The 3 lenses are already list-shaped.) |
| CR5.2 | **Set-union merger** — a `SummaryMerger` whose `merge` is union-of-claim-lists (no LLM); registered as strategy `setunion`. Associative → safe under CR3 batching. |
| CR5.3 | **Claim dedup via `muninn_extract_er`** — feed the unioned claims as ER "entities"; cluster; collapse each cluster to a representative + `count` + provenance. Tune `dist_threshold`/`jw_weight`/`borderline_delta`. |
| CR5.4 | **Salience prune** — keep top-N claims per lens by `count × recency`; carry `count` through to the API/UI as the upvote signal. |
| CR5.5 | **Benchmark** — different metrics than CR4: **dedup precision/recall** vs a hand-labelled claim set; **salience ranking** quality; LLM-call budget vs abstractive. Compare against the 64k abstractive baseline. |

## Notes / decisions

- **Composes with, doesn't replace, the scope/time tree.** Same hierarchy (ADR1.1); different node
  operator. `setunion` is a 4th strategy alongside strict/reground/flat.
- **Grounding for free** → the [CR4](./summariser-SCORING.md) "rollup grounding" anxiety mostly goes
  away (claims are extracted, not invented), so the benchmark pivots to dedup/salience quality.
- **The LLM judge stays bounded and optional** (binary "same claim?" — consistent with the project's
  "no numeric LLM judge; binary only" rule).
- **Faithful map-reduce reduce step.** If a coarse combine still needs *some* abstraction, prefer
  union+dedup over re-summarisation precisely because it preserves the associativity + provenance.

## Results & findings (2026-06-03) — first real run

Raw data: [summariser-CR5-RESULTS.md](./summariser-CR5-RESULTS.md). Run: Qwen3.5-2B @ n_ctx=65536,
scope `play/claude-code-sessions`, last 7 days, 12 sessions.

**The bug fix is confirmed.** Lenses are now genuinely variable-length lists, not one-each:
across 9 successfully-extracted sessions — **tasks=43, patterns=36, decisions_values=47** (≈4.8 / 4.0
/ 5.2 per session). `decisions_values` is the *richest* lens, matching the hypothesis that the
developer's *why*-reasoning is dense signal. Empty/short lists occur naturally where there's nothing
to say. The old schema would have forced exactly 9/9/9 single blobs.

**Set-union + COUNT + provenance works end-to-end.** L2 wrote 324 month / 324 week / 327 day
`rollup_claims` rows across the scope trie, each with a `count` and `source_session_ids`. At one scope
(project, month) 126 raw claims → 108 clusters.

**LLM-budget win (the headline cost result).** L1 used **12 LLM calls** (one per session); **L2 used
ZERO** (dedup is exact-match + embedding-cosine only). The abstractive path makes an LLM call at
*every* merge node — here ~324 month rollup nodes alone, plus week and day. So extractive aggregation
is ~2 orders of magnitude cheaper at L2 *and* grounded by construction (claims are real, not rewritten).

**Caveat — salience needs scale.** With only 9 distinct sessions the COUNT signal is weak (mostly
1×, one 2× "Markdown documentation structure"). Dedup compression (126→108) is modest because the
sample is small and varied. The thesis — repetition surfaces what matters — only bites at larger N;
this run proves the *mechanism*, not yet the *signal strength*.

**Finding — 25% L1 failure to harden.** 3/12 sessions returned "no balanced JSON object." Diagnosed
as **not** input overflow (the failed sessions were 1.5k–27k chars, incl. a tiny 1.5k one), so it is
the **list grammar / `max_tokens=512` decode** — the array grammar needs the same dial-in CR2 did for
the single-string grammar (raise the claims token cap and/or bound array length, and capture raw
output to confirm truncation vs malformed). Recorded as data, not hidden.

### Remaining for a full CR5.5 verdict
- Harden L1 list extraction (the 25% failure) and re-run for a clean rate.
- Dedup **precision/recall** vs a hand-labelled claim set (needs manual labels) — not yet done.
- Head-to-head vs the abstractive 64k baseline (that run was killed) — qualitative only so far:
  extractive claims are readable + grounded + counted, vs the abstractive month-root collapsing to one
  narrow blurb.
- Swap the Python exact+cosine dedup for the full `muninn_extract_er` cascade (CR5.3) at scale.

## Web interface + failure stream (2026-06-03) — built & evidenced

**Parallel failure stream.** L1 parse failures are recorded to `session_claim_failures` (reason +
raw excerpt, content-hash guarded) and re-raised; `rollup_failures()` rolls them up to
`rollup_claim_failures` (failed-session COUNT + provenance per scope×grain) parallel to the claim
roll-up. Surfaced in the API (`failure_count`) and UI. Operator can now triage "correct failure"
(genuinely empty) vs prompt-refinement — the 25% rate is tracked data, never silent loss.

**Backend (TDD, all green).** Query layer in `backend.py` + `Database` protocol + 6 endpoints in
`main.py`: `/api/claims/{models,buckets,scope,session/{p}/{s},session/{p}/{s}/memberships,coverage}`.
Reverse provenance uses a `json_each` join over `source_session_ids`. **462 backend tests pass**
(incl. `tests/test_claims_api.py`), mypy + ruff clean.

**Frontend.** `ClaimsExplorer.tsx` (route `/claims`) is now the **single** summarisation interface —
the abstractive `/summaries` explorer was retired (page + route + nav archived, `/summaries`
redirects to `/claims`; the shared scope-resolver endpoints moved to `/api/claims/scope/{children,
of-project}`; the abstractive backend stays frozen, just unsurfaced). It carries model/grain/bucket
selectors + scope-trie breadcrumb drill-down + four lens cards (tasks / patterns / decisions_values /
learnings) ranked by COUNT with provenance links + failures badge; `CacheSummarisation.tsx`
completeness panel; `SessionDetail.tsx` gains an "Included in these summaries" cross-reference card
(reverse provenance, deep-links back to `/claims`).

**Global filters fold into the explorer** (consistency with every other page):
- **Default view = "all claims at this grain"** — with no bucket selected the roll-up is the
  set-union of claims across *every* bucket in the window (fixes the old empty `(all)` default).
- **Last-N-days window** — `days` restricts the aggregate + bucket selector + heatmap columns +
  coverage, snapped to whole buckets (grain⊥days, matching the Daily/Weekly/Monthly convention).
  An explicit `?bucket=` is a deliberate drill-down and overrides the window.
- **Project hard-pin** — the global Project filter resolves (`/claims/scope/of-project`) to the
  project's leaf `scope_path`, overrides `?path=`, and locks the breadcrumb (cleared to regain the
  hierarchy).

Gates: tsc 0 errors, production build OK, 100 vitest, eslint clean, 472 backend pytest, ruff+mypy
clean, e2e specs pass (incl. the windowed-aggregate note + repointed `/claims` breadcrumb).

**Evidence — live run-through over real data** (Qwen3.5-2B, `play/claude-code-sessions`, month
`2026-05-01`, 96 claims), screenshots in `frontend/e2e-screenshots/`:
- `cr5-claims-explorer.png` — ranked claims with `(N×)` count badges + provenance session links.
- `cr5-cache-summarisation.png` — "Qwen3.5-2B · 0.6% complete · 8 summarised · 0 failed · 1,441
  pending · 1,449 total" + per-project table.
- `cr5-sessiondetail-crossref.png` — a session shown as included in roll-ups at every scope×grain
  (root/play/project × day/week/month), back-linking to the explorer.
- `cr5-claims-4lens-explorer.png` — the four-lens layout incl. the Learnings lens.
- `cr5-claims-windowed-aggregate.png` — the default "all month claims set-unioned across <window>"
  aggregate view (no bucket selected) with the window note.
- `cr5-claims-project-hardpin.png` — the global Project filter hard-pinning the scope to
  `play/claude-code-sessions`, breadcrumb shown static with a `pinned` marker, Summaries nav gone.
- `cr5-claims-variable-depth-subdomain.png` — variable mixed-depth within one domain: `play` holds
  both flat leaves AND a `play/gh-webpages/<project>` sub-branch; the explorer drills `All / play /
  gh-webpages → wcag-visualiser` and the heatmap surfaces both the intermediate `play/gh-webpages`
  aggregation scope and the leaf. Depth-agnostic by construction (`scope_path_of` /
  `ancestor_scopes` work off the authoritative path; set-union rolls a depth-3 leaf into its
  depth-1 domain). Locked by `tests/test_claims_api.py::*mixed_depth*` / `*variable*depth*`.

(`make ci` is green on every code gate — mypy/ruff/eslint/tsc/vitest/pytest/e2e — except a
pre-existing `npm audit --audit-level=high` transitive-dep advisory, unrelated to this work.)

## Explorer refinements (2026-06-03, review feedback)

Addressed a round of UI feedback — all backend TDD'd (467 backend tests), frontend tsc/build/vitest
(99 tests) + eslint green:

- **Sortable lens columns** — each lens sortable by COUNT or claim text, asc/desc (default count desc).
- **Model registry in selector** — `/api/claims/models/detail` lists data-backed models *and* on-disk
  registry models (Llama-3.1-8B etc.) flagged `(no data)`, so you can switch to Llama and trigger it.
- **Done-vs-pending Plotly heatmap** — `/api/claims/coverage-pivot` → a scope × time-bucket heatmap
  (done/failed/pending) on the explorer; this is the "pivot table" view and also surfaces the project
  hierarchy *sliced by the selected grain*.
- **Manual (re)trigger** — `POST /api/claims/reindex?path&grain&model` runs L1 extraction over the
  slice's sessions + the set-union + failure roll-ups on a background thread (`claims_reindex.py`,
  single-flight, status-polled), mirroring `/api/kg/reindex`. A "Reindex this slice" button + live
  status on the explorer. **Evidenced live**: POST→`running`→model loads→`extracting` with
  `sessions_done`/`failures` climbing (a failed session is counted into the parallel failure stream,
  not fatal to the job).
- **/summaries no-data fixed** — the page defaulted `bucket=''` (no selector); added
  `/api/summaries/buckets` + a bucket selector that auto-selects the newest bucket → lens content now
  renders. A note links to the Claims explorer as the adopted (re)index path.

- **Cache Summarisation table** — added a **Domain** column + `scope_path` (derived from each
  project's resolved scope) and **sortable columns** (click any header, toggles asc/desc). The table
  is **filtered by the explorer's page-level scope** (`/api/claims/coverage?scope=<path>` — the
  breadcrumb `path` drives it), *not* a redundant table-local control. Live: root=65 → `play`=20 →
  `play/claude-code-sessions`=1 → `work`=16 projects as you navigate the trie; 6 sortable columns.

Evidence screenshots: `cr5-explorer-enhanced.png` (heatmap + reindex + sortable + Llama option),
`cr5-summaries-fixed.png` (lens data rendering), `cr5-cache-table-sortable.png` (domain column +
sort + domain filter).

- [x] **Implemented** — L1 list extraction + L2 set-union/dedup with `count`/provenance; parallel
  failure stream + roll-up; full web interface (explorer drill-down + SessionDetail cross-ref + cache
  completeness panel + sortable + coverage heatmap + manual reindex trigger; /summaries no-data fixed);
  35 unit/API/reindex tests + e2e; real results gathered + live trace-through evidenced.
- [ ] **Done (full benchmark)** — pending L1 hardening (the 25% JSON-fail), dedup precision/recall vs
  hand-labels, and the abstractive head-to-head.
