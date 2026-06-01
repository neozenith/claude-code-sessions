# G3: SummaryMerger abstraction + roll-up driver

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G1](./summariser-G1.md), [G2](./summariser-G2.md)
> - **Blocks:** [G4](./summariser-G4.md), [G5](./summariser-G5.md), [G6](./summariser-G6.md), [G7](./summariser-G7.md), [G10](./summariser-G10.md)
> - **Prev:** [G2](./summariser-G2.md)
> - **Next:** [G4](./summariser-G4.md)

Defines the `SummaryMerger` interface, the name→impl registry, the `rollup_summaries` schema, and the bottom-up driver that walks the variable-depth scope trie — the shared seam the three implementations ([G4](./summariser-G4.md)/[G5](./summariser-G5.md)/[G6](./summariser-G6.md)) plug into. Rollups and freshness are scoped by `(strategy, model_id)` so the [G10](./summariser-G10.md) benchmark can run every permutation side-by-side.

## Context
Per GraphRAG (Edge et al. 2024), lower-tier summaries are recursively merged upward; per Ou & Lapata (ACL 2025), naive summary-of-summaries **amplifies hallucinations** unless each merge re-grounds in source excerpts. The three strategies that embody those trade-offs are built behind this interface ([G4](./summariser-G4.md) strict, [G5](./summariser-G5.md) reground, [G6](./summariser-G6.md) flat) and chosen empirically ([G10](./summariser-G10.md)).
`muninn_chat` (G2 `SummaryEngine`) is the merge backend; `ancestor_scopes` (G1) supplies the variable-depth scope trie (every `scope_path` prefix is a roll-up node); the existing `agg` time-bucket truncation (`cache.py`) supplies day/week/month. A `(strategy, model)` rollup merges **only that model's** child summaries — you never mix model-A children into a model-B rollup.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/schema.py` (py) | New `rollup_summaries` table (keyed by `strategy`, `model`, `scope_path`, grain, bucket) + `SCHEMA_VERSION` "18"→"19". |
| `src/claude_code_sessions/database/sqlite/merge.py` (py, new) | `SummaryMerger` Protocol + `Summary`/`SourceExcerpts` types + `MERGER_REGISTRY` and `get_merger(name)` (fail-loud on unknown). No concrete mergers here — those are G4/G5/G6. |
| `src/claude_code_sessions/database/sqlite/summaries.py` (py) | `roll_up_scopes(conn, engine, strategy, model, granularity, level=None)`: deepest-first scope walk over the requested **level band** (leaf … root), model-scoped child selection, `source_hash` freshness scoped by `(model_id, strategy_id)`, writes `rollup_summaries`. |
| `src/claude_code_sessions/summarise_cli.py` (py) | `rollup` subcommand **decoupled from ingest** (`… summarise_cli rollup --strategy S --model M --level <leaf\|domain\|root\|…> --grain <day\|week\|month>`): runs one level band at one grain off existing `session_summaries`, for external cadence triggers. |
| `tests/test_summaries.py` (py) | Driver/registry/freshness/level-band tests using a registered in-test stub merger (the concrete mergers' correctness lives in G4/G5/G6). |

## Key logic
```sql
CREATE TABLE rollup_summaries (
    strategy TEXT NOT NULL,            -- 'strict' | 'reground' | 'flat' (collapses to one post-G10)
    model TEXT NOT NULL,               -- summariser GGUF model_id (family + parameter size) — part of the key
    scope_path TEXT NOT NULL,          -- variable-depth prefix: '' = root/all, 'clients', 'clients/acme', 'clients/acme/app'
    scope_depth INTEGER NOT NULL,      -- 0 = root; len(scope_path.split('/')) otherwise — drives bottom-up order
    time_granularity TEXT NOT NULL,    -- 'day' | 'week' | 'month' | 'all'
    time_bucket TEXT NOT NULL,         -- ISO bucket | '' for all-time
    task_summary TEXT NOT NULL,
    patterns TEXT NOT NULL,
    decisions_values TEXT NOT NULL,
    child_count INTEGER NOT NULL,      -- direct children merged (deeper scopes and/or sessions)
    source_hash TEXT NOT NULL,         -- hash of (strategy, model, child ids+content_hashes) → skip if unchanged
    generated_at TEXT NOT NULL,
    PRIMARY KEY (strategy, model, scope_path, time_granularity, time_bucket)
);
```

The driver runs **per `(strategy, model)`** and enumerates every distinct `scope_path` from `ancestor_scopes`, merging **deepest-first**: a project-leaf scope merges its `session_summaries` *for that model*; each ancestor merges its direct child scopes' roll-ups *for that strategy+model*. Root (`scope_path=''`) is the all-domains summary.

```python
class SummaryMerger(Protocol):
    name: str                       # registry key / flag value: 'strict' | 'reground' | 'flat'
    child_mode: ChildMode           # 'child_rollups' (strict/reground) | 'raw_sessions' (flat)
    wants_excerpts: bool            # True only for reground
    def merge(self, engine: SummaryEngine, model: str, children: list[Summary],
              excerpts: SourceExcerpts | None) -> Summary: ...
# Concrete impls live in G4 (strict), G5 (reground), G6 (flat). The driver selects one via
# get_merger(flag), then gathers children per `merger.child_mode` and supplies excerpts only
# when `merger.wants_excerpts` — so strategy choices stay in the impls, not the driver.
```

## ADR3.1: Defer strategy selection to an empirical benchmark
- **Decision:** Build all three merge strategies behind this single feature-flagged `SummaryMerger` interface; do **not** choose one by upfront reasoning. The winner is selected by the [G10](./summariser-G10.md) benchmark, after which a collapse step removes the losing implementations and the flag.
- **Why:** The fidelity/speed trade-off between GraphRAG-style merging and Ou & Lapata re-grounding is corpus- and model-dependent; measuring it on this data derisks the choice cheaply and avoids building production on an unvalidated assumption.
- **Rejected:** Committing to re-grounding upfront (likely best on fidelity but unmeasured on this corpus and slower — exactly the unjustified assumption the benchmark exists to test).

## ADR3.2: Production merge strategy — RESOLVED (2026-06-01)

Resolved by the [G10](./summariser-G10.md) decision gate on real benchmark evidence — full write-up
in **[ADR3.2 report](./summariser-ADR3.2-merge-strategy.md)**.

| Option | Pros | Cons |
|--------|------|------|
| strict (bottom-up, summaries only) | Cheapest, reuses tiers; bounded ancestor merges scale to high scopes | Drift compounds with height |
| reground (bottom-up + source excerpts) | **Best faithfulness — the only strategy visibly working (BLEU ~6–10× the others); advantage grows with depth** | Excerpt tokens overflow context at big buckets/scopes |
| flat (re-summarise raw per scope/bucket) | Simple DAG | Single all-descendants prompt overflows first at high/coarse scopes; never beat strict |

- **Decision (PROCEED):** **reground** is the production strategy, applied **grain/height-aware** —
  reground @ daily by default; reground at week/month/deep *where the context budget holds*
  (contingent on a 128k model like Llama-3.1-8B or [CR3](./summariser-CR3.md) batching); **strict**
  as the deterministic fallback when the excerpt budget is blown; **flat** deprecated to shallow
  scopes only. Mistral-7B rejected (8k context). See the [report](./summariser-ADR3.2-merge-strategy.md).
- **Consequence:** the G11 collapse keeps **two** strategies (reground primary + strict fallback),
  not one — the context-aware policy, not a single winner.

## ADR3.4: Roll-ups run per level band on an external cadence
- **Decision:** `roll_up_scopes` accepts a `level` band (and `granularity`) so each tier of the trie can be rolled up independently and on its own cadence — e.g. leaf/project rollups daily, domain/root rollups weekly — all manually triggered (ADR2.4), reading the `session_summaries` that exist to date.
- **Why:** Higher tiers change slowly and are expensive (largest prompts); pinning them to the same cadence as leaf rollups wastes compute. Per-level triggering lets the user match cadence to volatility, and eventual consistency means a weekly domain roll-up simply consumes whatever leaf tier exists.
- **Rejected:** One all-levels run per invocation (forces a single cadence); auto-running every level on ingest (the coupling ADR2.4 rejects).

## ADR3.3: Rollups are scoped by summariser model_id and strategy_id
- **Decision:** Both the `rollup_summaries` key and the `source_hash` freshness check include `model_id` and `strategy_id`. A child is only merged into a parent of the same `(strategy, model)`; changing either the model or the strategy yields a distinct row and a fresh computation.
- **Why:** During the benchmark the same scope is rolled up by many `(strategy, model)` permutations at once; without model/strategy in the key they would clobber each other, and freshness would falsely skip a permutation that merely shares source text.
- **Rejected:** Keying only by `(strategy, scope, grain, bucket)` (loses the model axis the benchmark sweeps); hashing only child content (a different model's children would false-match).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T3.1](./summariser-G3-T3.1.md) | The driver + a registered stub merger write one rollup row for a leaf scope _(tracer)_ | [T1.2](./summariser-G1-T1.2.md), [T2.1](./summariser-G2-T2.1.md) |
| [T3.2](./summariser-G3-T3.2.md) | An ancestor scope merges its child scopes' rollups bottom-up (deepest-first) | [T3.1](./summariser-G3-T3.1.md), [T1.2](./summariser-G1-T1.2.md) |
| [T3.3](./summariser-G3-T3.3.md) | `get_merger(flag)` selects an impl from the registry; unknown flag fails loudly | [T3.1](./summariser-G3-T3.1.md) |
| [T3.4](./summariser-G3-T3.4.md) | A (strategy, model) rollup merges only that model's child summaries | [T3.1](./summariser-G3-T3.1.md) |
| [T3.5](./summariser-G3-T3.5.md) | source_hash freshness scoped by (model, strategy) skips unchanged, recomputes on change | [T3.1](./summariser-G3-T3.1.md) |
| [T3.6](./summariser-G3-T3.6.md) | The root scope yields the all-domains rollup | [T3.2](./summariser-G3-T3.2.md) |
| [T3.7](./summariser-G3-T3.7.md) | `roll_up_scopes` runs only the requested level band (cadence control) | [T3.2](./summariser-G3-T3.2.md) |
