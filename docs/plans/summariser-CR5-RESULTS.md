# CR5 Extractive Set-Union — Experiment Results

Model **Qwen3.5-2B** @ n_ctx=65536; scope `play/claude-code-sessions`; since 2026-05-26; limit 12. Generated 2026-06-02T14:06:48.704366+00:00.

## L1 — session claim extraction
- sessions extracted: **9** ok, 3 failed (LLM calls = 12)
- total claims: **126**  (~14.0/session)
- per lens: tasks=43, patterns=36, decisions_values=47

## L2 — set-union dedup (NO LLM calls; exact + embedding-cosine only)
- raw L1 claims: **126** → project-scope month clusters: **108** (dedup compression at one scope)
- rows written: day=327, week=324, month=324

## Salience — top claims by COUNT (the signal abstractive merging discards)

### ROOT (all) — month grain

**tasks**
- (1×) Analyze the session summary hierarchy to identify L1 and L2+ aggregation steps
- (1×) Analyze the plan-gap skill failure and root cause
- (1×) Gather results from summariser-CR5-extractive-setunion.md
- (1×) Apply new ADR formatting rules to all plan spec files
- (1×) Implement extractive set-union benchmark experiment
- (1×) Create linked subdocuments for each gap section (tokenometrics-G<n>-T<x.y>.md)
- (1×) Validate session summary extraction logic for tasks, decisions, and patterns
- (1×) Create the summariser-cr1.md retro documentation

**patterns**
- (2×) Markdown documentation structure
- (1×) Aggregation hierarchy patterns
- (1×) Context window partitioning patterns
- (1×) ADR decision records
- (1×) Entity extraction patterns
- (1×) Agentic skills need explicit evidence gates
- (1×) Software refactoring patterns
- (1×) Agentic workflow planning

**decisions_values**
- (1×) Implement entity extraction to replace entity type extraction
- (1×) Decisions to collapse Execution Plan into a TOC section in the main document
- (1×) Prioritize extractive set-union over map-reduce for summarisation
- (1×) Decisions to prioritize human review content in separate documents
- (1×) Use L1 summarisation followed by L2+ aggregation
- (1×) Decisions to separate planning documents into smaller, focused files for better readability
- (1×) Validate session summary extraction logic before aggregation
- (1×) Decisions to use ADR format with unique IDs for decision records

### `play/claude-code-sessions` — month grain

**tasks**
- (1×) Analyze the session summary hierarchy to identify L1 and L2+ aggregation steps
- (1×) Analyze the plan-gap skill failure and root cause
- (1×) Gather results from summariser-CR5-extractive-setunion.md
- (1×) Apply new ADR formatting rules to all plan spec files
- (1×) Implement extractive set-union benchmark experiment
- (1×) Create linked subdocuments for each gap section (tokenometrics-G<n>-T<x.y>.md)
- (1×) Validate session summary extraction logic for tasks, decisions, and patterns
- (1×) Create the summariser-cr1.md retro documentation

**patterns**
- (2×) Markdown documentation structure
- (1×) Aggregation hierarchy patterns
- (1×) Context window partitioning patterns
- (1×) ADR decision records
- (1×) Entity extraction patterns
- (1×) Agentic skills need explicit evidence gates
- (1×) Software refactoring patterns
- (1×) Agentic workflow planning

**decisions_values**
- (1×) Implement entity extraction to replace entity type extraction
- (1×) Decisions to collapse Execution Plan into a TOC section in the main document
- (1×) Prioritize extractive set-union over map-reduce for summarisation
- (1×) Decisions to prioritize human review content in separate documents
- (1×) Use L1 summarisation followed by L2+ aggregation
- (1×) Decisions to separate planning documents into smaller, focused files for better readability
- (1×) Validate session summary extraction logic before aggregation
- (1×) Decisions to use ADR format with unique IDs for decision records

## L1 extraction failures (recorded as data)
- 962675c9: no balanced JSON object found in model output
- d758df26: no balanced JSON object found in model output
- d7bf669c: no balanced JSON object found in model output