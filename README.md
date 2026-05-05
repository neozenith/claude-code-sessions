# Claude Code Sessions Analytics

FastAPI + React dashboard for visualizing Claude Code session usage, costs,
full-text + semantic search, and a knowledge graph derived from
`~/.claude/projects/` JSONL files. Backed by an incrementally-built SQLite
cache at `~/.claude/cache/introspect_sessions.db` containing usage rollups,
FTS5 indexes, sentence-transformer embeddings (sqlite-vec), and a Leiden-
clustered entity-relation graph.

## Architecture Diagrams

Each lens below has a simplified overview (always visible) and a detailed
reference (collapsed). Diagrams render natively on GitHub / GitLab — no
pre-rendered PNG step. Color encoding is consistent across all three:
🟦 source · 🟪 process · 🟧 storage · 🟩 output.

### System architecture

```mermaid
flowchart LR
    JSONL[("~/.claude/projects/<br/>JSONL logs")]:::source
    API["FastAPI<br/>:8100 / :8101"]:::process
    CACHE[("~/.claude/cache/<br/>SQLite index")]:::storage
    UI["React + Vite<br/>:5273 / :5274"]:::output

    JSONL -->|ingest| API
    API -->|read/write| CACHE
    API -->|JSON| UI

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

*4 nodes — the end-to-end data path in one line.*

<details>
<summary>📋 Detailed architecture (subgraphs by responsibility)</summary>

```mermaid
flowchart TB
    JSONL[("~/.claude/projects/<br/>JSONL logs")]:::source
    RSYNC["rsync to ./projects/<br/>(optional local copy)"]:::source

    subgraph Backend["Backend (src/claude_code_sessions/)"]
        INGEST["CacheManager<br/>mtime-based scan"]:::process
        PARSE["_parse_event +<br/>compute_event_costs"]:::process
        ENRICH["Enrichment<br/>sync_chunks + sync_embeddings +<br/>sync_kg (NER, RE, clusters,<br/>communities, labels)"]:::process
        DB["SQLiteDatabase<br/>query layer"]:::process
        API["FastAPI + uvicorn<br/>main.py"]:::process
    end

    CACHE[("~/.claude/cache/<br/>introspect_sessions.db<br/>events / agg / event_calls /<br/>event_edges / FTS5 /<br/>chunks + embeddings /<br/>entities + relations +<br/>kg nodes/edges/communities")]:::storage

    subgraph Frontend["Frontend (React + Vite)"]
        ROUTES["Routes<br/>Dashboard / Daily / Weekly /<br/>Monthly / Hourly / Hour-of-Day /<br/>Sessions (list, project, detail) /<br/>Timeline / Schema Timeline /<br/>Search / Knowledge Graph"]:::output
        CHARTS["Plotly.js + shadcn/ui"]:::output
    end

    JSONL --> RSYNC
    JSONL --> INGEST
    RSYNC --> INGEST
    INGEST --> PARSE
    PARSE --> CACHE
    CACHE --> ENRICH
    ENRICH --> CACHE
    DB --> CACHE
    API --> DB
    API --> ROUTES
    ROUTES --> CHARTS

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

</details>

### Data flow — JSONL to charts

```mermaid
flowchart LR
    S["Claude JSONL<br/>events"]:::source
    I["Ingest +<br/>enrich"]:::process
    D[("events +<br/>event_calls")]:::storage
    AGG[("agg<br/>(pre-rollups)")]:::storage
    KG[("FTS + embeddings +<br/>KG nodes/edges")]:::storage
    API["API layer"]:::process
    UI["Charts +<br/>Search + KG"]:::output

    S --> I --> D
    D --> AGG
    D --> KG
    AGG --> API
    D --> API
    KG --> API
    API --> UI

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

*7 nodes — ingest writes to fact tables, the same pass enriches them with FTS / embeddings / KG, and the API joins both worlds for the dashboard.*

<details>
<summary>📋 Detailed data flow (per-function pipeline)</summary>

```mermaid
flowchart LR
    S1[("JSONL files")]:::source
    DISC["discover_files"]:::process
    NEED["get_files_needing_update<br/>(mtime / size diff)"]:::process
    PARSE["_parse_event"]:::process
    COST["compute_event_costs<br/>(hardcoded pricing)"]:::process
    EXTRACT["extract_calls<br/>(tool/skill/subagent/cli/<br/>rule/make_target/<br/>uv_script/bun_script)"]:::process
    EDGES["parent_uuid /<br/>prompt_id linking"]:::process

    subgraph Core["SQLite cache - core fact tables"]
        EV[("events +<br/>events_fts")]:::storage
        EC[("event_calls")]:::storage
        EE[("event_edges")]:::storage
        AGG[("agg (hourly/daily/<br/>weekly/monthly)")]:::storage
        SESS[("sessions + projects")]:::storage
    end

    ENRICH["Enrichment pass<br/>sync_chunks &gt; sync_embeddings &gt;<br/>sync_kg(NER, RE, resolve,<br/>communities, labels)"]:::process

    subgraph Enriched["SQLite cache - enrichment tables"]
        CHUNKS[("event_message_chunks +<br/>event_message_chunks_fts")]:::storage
        EMB[("entity_vec_map<br/>(sqlite-vec)")]:::storage
        ENTS[("entities + relations +<br/>ner_chunks_log + re_chunks_log")]:::storage
        KGT[("nodes + edges +<br/>entity_clusters +<br/>leiden_communities +<br/>community_labels")]:::storage
    end

    API["FastAPI endpoints"]:::process
    UI["React + Plotly /<br/>Search / KG"]:::output

    S1 --> DISC --> NEED --> PARSE
    PARSE --> COST --> EV
    PARSE --> EXTRACT --> EC
    PARSE --> EDGES --> EE
    EV --> AGG
    EV --> SESS
    EV --> ENRICH
    ENRICH --> CHUNKS
    ENRICH --> EMB
    ENRICH --> ENTS
    ENRICH --> KGT
    AGG --> API
    SESS --> API
    EC --> API
    EE --> API
    CHUNKS --> API
    EMB --> API
    ENTS --> API
    KGT --> API
    API --> UI

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

</details>

### API request/response flow

```mermaid
sequenceDiagram
    participant F as Frontend
    participant API as FastAPI
    participant DB as SQLite cache

    F->>+API: GET /api/summary?days=30
    API->>+DB: SELECT from agg
    DB-->>-API: aggregates
    API-->>-F: JSON
```

*The canonical read path — dashboard endpoints all follow this shape.*

<details>
<summary>📋 Detailed API flow (every endpoint family)</summary>

```mermaid
sequenceDiagram
    participant F as Frontend
    participant API as FastAPI
    participant DB as SQLite cache

    Note over F,DB: Startup
    F->>API: GET /api/health
    API-->>F: {status, projects_path}

    Note over F,DB: Summary & time-series (agg reads)
    F->>+API: /api/summary, /api/usage/{daily,weekly,monthly,hourly}
    API->>+DB: SELECT from agg WHERE granularity = ?
    DB-->>-API: bucketed rows
    API-->>-F: JSON

    Note over F,DB: Sessions & per-session metrics
    F->>+API: GET /api/sessions?project=...
    API->>+DB: sessions LEFT JOIN event_calls CTEs<br/>(tool/skill/make counts + top_skill)
    DB-->>-API: session rows with call metrics
    API-->>-F: JSON

    Note over F,DB: Timeline
    F->>+API: GET /api/timeline/events/:project
    API->>+DB: Window-function SELECT on events
    DB-->>-API: events with cumulative tokens
    API-->>-F: JSON

    Note over F,DB: Call analytics (event_calls fact table)
    F->>+API: GET /api/calls/timeline, /api/calls/top
    API->>+DB: GROUP BY on event_calls
    DB-->>-API: counts / top-N names
    API-->>-F: JSON

    Note over F,DB: Search (FTS5 + semantic)
    F->>+API: GET /api/search?q=...
    API->>+DB: events_fts BM25 UNION<br/>chunks_fts UNION<br/>vec_distance(entity_vec_map)
    DB-->>-API: ranked hits
    API-->>-F: JSON

    Note over F,DB: Knowledge graph
    F->>+API: GET /api/kg/er?resolution=...
    API->>+DB: load_kg_er<br/>(nodes + edges + communities)
    DB-->>-API: graph payload
    API-->>-F: JSON
```

</details>

### Knowledge graph & search pipeline

```mermaid
flowchart LR
    EV[("events")]:::source
    CHUNK["chunk + FTS5"]:::process
    NER_RE["GLiNER NER + RE"]:::process
    RESOLVE["entity resolution<br/>(embed + cluster)"]:::process
    GRAPH[("KG nodes/edges +<br/>communities")]:::storage
    NAMING["Leiden +<br/>LLM naming"]:::process
    UI["Search +<br/>KG explorer"]:::output

    EV --> CHUNK --> NER_RE --> RESOLVE --> GRAPH --> NAMING --> UI
    CHUNK --> UI

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

*7 nodes — events feed both lexical search (FTS5) and a multi-stage knowledge graph pipeline that ends in named communities.*

<details>
<summary>📋 Detailed KG + search pipeline (per-table, per-phase)</summary>

```mermaid
flowchart TB
    EV[("events.body_text")]:::source

    subgraph Chunking["1. Chunk + lexical index"]
        CK["chunk_text<br/>(sliding window)"]:::process
        FTS5[("event_message_chunks +<br/>event_message_chunks_fts<br/>(FTS5 BM25)")]:::storage
        EVFTS[("events_fts<br/>(FTS5 on events)")]:::storage
    end

    subgraph Extract["2. NER + RE (sync_ner_re)"]
        GLINER["GLiNER2 NER"]:::process
        REMOD["RE prompt (LLM)"]:::process
        ENTS[("entities")]:::storage
        RELS[("relations")]:::storage
        NLOG[("ner_chunks_log /<br/>re_chunks_log")]:::storage
    end

    subgraph Resolve["3. Entity resolution"]
        EEMB["sync_entity_embeddings<br/>(sentence-transformer)"]:::process
        VEC[("entity_vec_map<br/>(sqlite-vec)")]:::storage
        CLU["sync_entity_clusters"]:::process
        CLUST[("entity_clusters +<br/>entity_cluster_labels")]:::storage
    end

    subgraph Graph["4. Graph + communities"]
        BUILD["build nodes/edges"]:::process
        NE[("nodes + edges")]:::storage
        LEI["sync_communities<br/>(Leiden)"]:::process
        LC[("leiden_communities")]:::storage
        CN["sync_community_labels<br/>(LLM)"]:::process
        CL[("community_labels")]:::storage
    end

    subgraph Serve["5. Read paths"]
        SEARCH["/api/search<br/>(FTS + semantic)"]:::output
        KGAPI["/api/kg/er<br/>(load_kg_er payload)"]:::output
    end

    EV --> CK --> FTS5
    EV --> EVFTS
    CK --> GLINER --> ENTS
    GLINER --> NLOG
    CK --> REMOD --> RELS
    REMOD --> NLOG
    ENTS --> EEMB --> VEC
    VEC --> CLU --> CLUST
    CLUST --> BUILD --> NE
    RELS --> BUILD
    NE --> LEI --> LC
    LC --> CN --> CL

    EVFTS --> SEARCH
    FTS5 --> SEARCH
    VEC --> SEARCH
    NE --> KGAPI
    CL --> KGAPI

    classDef source  fill:#1e40af,color:#ffffff
    classDef storage fill:#92400e,color:#ffffff
    classDef process fill:#5b21b6,color:#ffffff
    classDef output  fill:#047857,color:#ffffff
```

</details>

## Quick Start

### Installation
```bash
make install              # Install all dependencies
```

### Development

**For AI Agents (use agentic ports):**
```bash
make agentic-dev          # Backend: 8101, Frontend: 5274
```

**For Human Developers:**
```bash
make dev                  # Backend: 8100, Frontend: 5273
```

### Data Management
```bash
make sync-projects        # Sync from ~/.claude/projects/
```

## Tech Stack

**Backend:**
- FastAPI - API framework
- SQLite (stdlib `sqlite3`) - Cached analytics index, built incrementally from JSONL source files
- uv - Package management

**Frontend:**
- React 18 + TypeScript
- Vite - Build tool
- Tailwind CSS + shadcn/ui
- Plotly.js - Charts
- Lucide React - Icons

## Dashboard Features

- **Dashboard** - Summary cards, monthly cost trends, top skills / sub-agents / CLIs / make targets
- **Hourly** - Heatmaps and polar charts (DoW × HoD) with Melbourne timezone
- **Hour of Day** - Radial cost/token charts
- **Daily / Weekly / Monthly** - Diverging token bars by model with zero-aligned cost overlay
- **Sessions** - Three-level drill-down: list of all sessions, sessions grouped by project, and per-session detail with message-kind filter
- **Timeline** - Event-level scatterplot per project
- **Schema Timeline** - JSONL field-shape evolution over time
- **Search** - Mixed FTS5 + semantic search across every session and project
- **Knowledge Graph** - Entity-relation graph view with Leiden communities and LLM-generated labels

## Port Configuration

| Developer | Backend | Frontend |
|-----------|---------|----------|
| Human     | 8100    | 5273     |
| AI Agent  | 8101    | 5274     |

**Important:** Always use agentic ports (8101/5274) when developing as an AI agent!

## Commands Reference

```bash
# Development
make dev                  # Human dev (8100/5273)
make agentic-dev          # AI agent dev (8101/5274)
make dev-backend          # Backend only
make dev-frontend         # Frontend only

# Code Quality
make format               # Format with ruff
make lint                 # Lint all code
make typecheck            # Type check all code
make test                 # Run all tests

# Port Management
make port-debug           # Show port usage
make port-clean           # Kill processes on ports

# Utilities
make clean                # Clean build artifacts
```

## Data Schema

Session JSONL files contain:
- `timestamp` - ISO8601 format (UTC, converted to Australia/Melbourne for analysis)
- `message.model` - Claude model ID
- `message.usage` - Token usage metrics
  - `input_tokens`, `output_tokens`
  - `cache_read_input_tokens`
  - `cache_creation_input_tokens`
  - `cache_creation.ephemeral_5m_input_tokens`

## Pricing

Model pricing lives in [`src/claude_code_sessions/database/sqlite/pricing.py`](src/claude_code_sessions/database/sqlite/pricing.py) as a hardcoded dict keyed by model family (`opus`/`sonnet`/`haiku`). `compute_event_costs()` runs at ingest time and writes `total_cost_usd` directly onto each row of the SQLite `events` table — dashboard queries do plain `SUM(total_cost_usd)` with no runtime pricing lookup.

**Changing prices:** edit the dict, then rebuild the cache (bump `SCHEMA_VERSION` in `schema.py` or delete `~/.claude/cache/introspect_sessions.db`) so existing events get re-costed. The introspect skill at `.claude/skills/introspect/scripts/introspect_sessions.py` has its own copy of the same dict — keep in sync.

Source: [Anthropic Pricing](https://www.anthropic.com/pricing)

## API Endpoints

**Health & metadata**
- `GET /api/health` - Health check
- `GET /api/domains` - Domain-filtering status

**Usage rollups (read from `agg`)**
- `GET /api/summary` - Overall usage summary
- `GET /api/usage/daily` - Daily breakdown
- `GET /api/usage/weekly` - Weekly breakdown
- `GET /api/usage/monthly` - Monthly breakdown
- `GET /api/usage/hourly` - Hourly breakdown (last 14 days, Melbourne timezone)
- `GET /api/usage/sessions` - Per-session usage rollup
- `GET /api/usage/top-projects-weekly` - Top 3 projects (last 8 weeks)

**Sessions & timeline**
- `GET /api/sessions` - List all sessions with call/skill metrics
- `GET /api/sessions/{project_id}/{session_id}` - Single session detail
- `GET /api/sessions/{project_id}/{session_id}/events/{event_uuid}/raw` - Raw JSONL event payload
- `GET /api/projects` - Projects with stats (used for the sidebar project filter)
- `GET /api/timeline/events/{project_id}` - Per-project event timeline with cumulative tokens
- `GET /api/schema-timeline` - JSONL field-shape evolution over time

**Call analytics**
- `GET /api/calls/timeline` - Tool/skill/sub-agent/CLI/make-target call counts bucketed by time
- `GET /api/calls/top` - Top-N distinct call names for a given call_type

**Search & knowledge graph**
- `GET /api/search` - Mixed FTS5 + semantic search across events and chunks
- `GET /api/kg/er` - Entity-relation graph payload (nodes, edges, communities, labels)

## Development Notes

- All Python code must pass mypy strict mode
- Use `@/` import alias in frontend (e.g., `@/hooks/useApi`)
- Frontend uses shadcn/ui components with Tailwind CSS
- Backend uses uv for dependency management (not pip/requirements.txt)
- Stay at repo root for all operations (use `npm --prefix frontend`)


## Crontab

```sh
0 */2 * * * rsync -av ~/.claude/projects/ ~/play/claude-code-sessions/all-sessions/claude/projects/ >> ~/play/claude-code-sessions/logs/sync-$(date +\%Y\%m\%d).log 2>&1
0 */2 * * * rsync -av ~/.codex/sessions/ ~/play/claude-code-sessions/all-sessions/codex/projects/ >> ~/play/claude-code-sessions/logs/sync-$(date +\%Y\%m\%d).log 2>&1
0 */2 * * * rsync -av ~/.copilot/session-state/ ~/play/claude-code-sessions/all-sessions/copilot/projects/ >> ~/play/claude-code-sessions/logs/sync-$(date +\%Y\%m\%d).log 2>&1
```