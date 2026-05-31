# Tokenometrics doc style

Precise and concise: cut any token that doesn't change what the reader *does*; use Markdown structure, not bold labels; keep loop-time docs free of review-only context.

> Sources: [Diátaxis](https://diataxis.fr/reference/), [Google](https://developers.google.com/style/tables) & [Microsoft](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice) style guides, [Nygard ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) / [MADR](https://adr.github.io/madr/), [Gherkin](https://cucumber.io/docs/bdd/better-gherkin/), [SemBr](https://sembr.org/), [WebAIM headings](https://webaim.org/techniques/headings/), [GFM](https://github.github.com/gfm/).

## Rules (all tiers)

1. **Front-load.** First line states the outcome; readers scan F-pattern and may not scroll.
2. **Headings are verb-led sentence fragments**, sentence case, no end punctuation. An ID-prefixed heading separates the ID with a colon: `G<n>:`, `T<x.y>:`, `ADR<n>.<m>:`.
3. **No bold-pseudo-headings.** A `**Label:**` line becomes a real heading, a table column, or is deleted — bold isn't navigable structure (WCAG 1.3.1). (Inline bold *lead-ins* inside a definition-style list item are fine.)
4. **Container by shape.** ≥3-property records → table; sequences/sets → list; one idea → prose. Keep table cells short (no nested lists).
5. **Cut filler and constants.** No *currently* / *you can*; drop any field identical on every item (e.g. `Cycle: RED → GREEN`, `Mocks: none`). State a field only when it varies.
6. **Separate genres.** *Why* = short prose; *what* = austere table; *steps* = the loop. Don't blend the three in one paragraph.
7. **One observable behavior per ticket**, declarative `<actor> <outcome>`.
8. **ADRs are gap-scoped and bulleted.** Heading `ADR<n>.<m>: <concise decision>` (n = gap, m = 1-based within it); body is separate bullet lines — **Decision**, **Why**, optional **Rejected** / **Superseded**. No Pros/Cons table for a settled decision.
9. **Semantic line breaks in prose only** (one clause per line — clean agent diffs); tables and lists stay single-line.
10. **Self-contained, labeled chunks.** The test of a sentence: delete it — does the build change? If not, cut it.
11. **Fold meta, don't delete it.** Wrap the TOC and runner blocks in `<details>` — a human skims past, an agent still reads the source. (`md_toc` resolves headings through the fold, and anchors auto-expand the block.)
12. **Context economy.** The index, gaps, and tickets are the agent's loop working-set; review/background (Current & Desired State) lives in `-DISCOVERY.md`, not the index.
13. **Cross-link by ID.** Gap Depends/Blocks link to gap files; ticket Depends on links to ticket files; every doc back-links to the index.
14. **No `·` delimiter.** Humans don't write middots. Use commas in prose and table cells, a colon after a heading ID, and a multiline blockquote list for navigation — never an inline-delimited run.

## Document set

| File | Tier | Genre | Loaded |
|------|------|-------|--------|
| `tokenometrics.md` | index | navigation + framing + execution plan | loop entry |
| `tokenometrics-G<n>.md` | gap | explanation + reference + ticket pointers | per-gap work |
| `tokenometrics-G<n>-T<x.y>.md` | ticket | austere reference — one TDD slice | per-ticket work |
| `tokenometrics-DISCOVERY.md` | discovery | Current & Desired State | human review only |
| `tokenometrics-STYLE.md` | style | authoring contract (this file) | when editing the set |

---

## Tier 1 — Index (`tokenometrics.md`)

Genre: navigation + framing. Keep the diagrams and rolled-up tables; everything else is a pointer.

- Sections: Execution Plan, Overview, Gap Analysis (Gap Map + Dependencies + Gaps table), Decisions (ADRs), Success Measures, Negative Measures.
- The **TOC** and the **Execution Plan body** are each wrapped in `<details>` (collapsed for skim; the runner prompt stays at the top for the agent). Keep the `## Execution Plan` heading visible above its fold.
- A one-line **Background** blockquote points to `-DISCOVERY.md` (where Current/Desired State moved).
- Overview lists gaps as links + one-line outcomes. Progress, Gaps, and Success/Negative measures are tables; gap + ticket IDs are links.
- A **Decisions (ADRs)** table (columns **ADR, Decision, Why**; one row per ADR, the id linking to its gap) summarises every decision — a primary review lens.
- Diagrams (Overview deps, Gap Map, Dependencies) obey the mermaid gates; the Gap Map may run detail-density (see Diagrams).

---

## Tier 2 — Gap (`tokenometrics-G<n>.md`)

Genre: explanation (why) + reference (what) + pointer (tickets).

````markdown
# G<n>: <Title>

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G..](...), … — or none
> - **Blocks:** [G..](...), … — or none
> - **Prev:** [G..](...)
> - **Next:** [G..](...)

<1–2 sentences: what closing this gap delivers.>

## Context
<Current state and the binding constraint, 1–3 sentences, semantic line breaks.>

## Outputs
| File | Change |
|------|--------|
| `path` (lang) | <what changes> |

## Key logic            ← optional; include only when a snippet de-risks the work
```python
…
```

## ADR<n>.<m>: <concise decision summary>   ← gap-scoped id, one per settled ADR
- **Decision:** <full sentence>.
- **Why:** <1–2 sentences>.
- **Rejected:** <option (reason); …>           ← when options were weighed
- **Superseded:** <prior ADR withdrawn + why>  ← when a decision is reversed

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T<n>.1](./tokenometrics-G<n>-T<n>.1.md) | <behavior> | — |
````

Cut from the old format: the `**Current:** / **Gap:**` labels (fold into the lead + Context), the ADR Pros/Cons tables, and any Output line that just restates a ticket.

---

## Tier 3 — Ticket (`tokenometrics-G<n>-T<x.y>.md`)

Genre: austere reference. One behavior, one test, the implementation target, dependencies.

```markdown
# T<x.y>: <actor> <observable outcome>

> - **Gap:** [G<n>: <title>](./tokenometrics-G<n>.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T..](./..)        ← omit on the first ticket
> - **Next:** [T..](./..)        ← omit on the last ticket

- [ ] **Done**

<One sentence stating the precise, assertion-worthy contract — exact endpoint/args/return or the concrete fact the test checks.> <_(tracer bullet)_ — only on T<n>.1>

| | |
|--|--|
| Test | `path::test_name` — <assertion against the public interface> |
| Implements | `file` <symbol>, `file` |
| Depends on | [T..](./tokenometrics-G<a>-T<a>.<b>.md), … — or — |
| Mocks | <only if not `none`> |
| Refactor | <only if present> |
```

Cut from the old format: `**Cycle:** RED → GREEN` (every ticket is RGR — it's in the loop prompt), `**Mocks:** none` (state mocks only when non-empty), the `**Behavior:**` label (the title *is* the behavior; the lead sentence adds precision), and the 3-level Test/Implementation bullet nest (collapse to table rows).

---

## Discovery (`tokenometrics-DISCOVERY.md`)

Review/background only — the before/after architecture, not loaded during the implementation loop. Nav is a blockquote-list backlink to the index, followed by a one-line note marking it review-only. Holds `## Current State` and `## Desired State`, each with its Mermaid diagram.

## Diagrams

- Derive the palette from `.claude/skills/mermaidjs_diagrams/resources/color_theming.md`. Use **`fill` + `color` only, no `stroke`** — a same-hue stroke fails the 3:1 border check; pick fills dark enough for white text (greens ≥ `#166534`).
- Both gates are blockers, run before declaring a diagram done:
  - `mermaid_contrast.ts` — WCAG AA on every `classDef`/`style`.
  - `mermaid_complexity.ts` — medium density by default; the Gap Map may run detail-density (its 3×N current→gap→desired mapping is justified), captioned as such.

## Conventions

- **Dropped tickets:** strike the title in the gap Tickets table — `~~<behavior>~~ **Dropped** (reason)` — keep the ticket file and its `[x]` (no work owed), and record the reason in the index Progress.
- **Done state is data, not style:** a restyle never flips `[ ]`↔`[x]` — preserve whatever each file holds.
