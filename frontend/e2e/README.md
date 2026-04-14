# E2E Test Suite

End-to-end tests for Claude Code Sessions Analytics using Playwright.

## Site Map

```mermaid
graph LR
    subgraph "Navigation Sections"
        S0["S0: Dashboard<br/>/"]
        S1["S1: Daily<br/>/daily"]
        S2["S2: Weekly<br/>/weekly"]
        S3["S3: Monthly<br/>/monthly"]
        S4["S4: Hourly<br/>/hourly"]
        S5["S5: HourOfDay<br/>/hour-of-day"]
        S6["S6: Projects<br/>/projects"]
        S7["S7: Sessions<br/>/sessions"]
        S8["S8: Timeline<br/>/timeline"]
        S9["S9: SchemaTimeline<br/>/schema-timeline"]
    end

    subgraph "Session Sub-pages"
        S7a["S7a: ProjectSessions<br/>/sessions/:projectId"]
        S7b["S7b: SessionDetail<br/>/sessions/:projectId/:sessionId"]
    end

    S7 --> S7a --> S7b

    style S0 fill:#3B82F6,color:#fff
    style S1 fill:#10B981,color:#fff
    style S2 fill:#10B981,color:#fff
    style S3 fill:#10B981,color:#fff
    style S4 fill:#8B5CF6,color:#fff
    style S5 fill:#8B5CF6,color:#fff
    style S6 fill:#F59E0B,color:#000
    style S7 fill:#F59E0B,color:#000
    style S7a fill:#F59E0B,color:#000
    style S7b fill:#F59E0B,color:#000
    style S8 fill:#EC4899,color:#fff
    style S9 fill:#EC4899,color:#fff
```

## Screenshot Naming Convention

Every filter permutation generates a screenshot using the pattern:

```
E{id}{engine}-S{id}{route_name}-T{id}{time_bucket}-P{id}.png
```

**Examples:**
- `E1sqlite-S0dashboard-T430d-P0.png` — SQLite, Dashboard, 30 days, All Projects
- `E0duckdb-S1daily-T27d-P1.png` — DuckDB, Daily, 7 days, This Project
- `E1sqlite-S7sessions-T7all-P0.png` — SQLite, Sessions, All time, All Projects

| Axis | Values |
|------|--------|
| **E** (Engine) | `0duckdb`, `1sqlite` |
| **S** (Section) | `0dashboard`, `1daily`, `2weekly`, `3monthly`, `4hourly`, `5hourofday`, `6projects`, `7sessions`, `8timeline`, `9schematimeline` |
| **T** (Time Range) | `024h`, `13d`, `27d`, `314d`, `430d`, `590d`, `6180d`, `7all` |
| **P** (Project) | `0` (All Projects), `1` (Specific Project) |

**Full matrix:** 2 engines x 10 sections x 8 time ranges x 2 project options = **320 permutations**

### Permutation Matrix

```mermaid
block-beta
    columns 9
    block:header:9
        H["Screenshot Matrix: S{section}-T{time}-P{project}"]
    end
    space T0["T0<br/>24h"] T1["T1<br/>3d"] T2["T2<br/>7d"] T3["T3<br/>14d"] T4["T4<br/>30d"] T5["T5<br/>90d"] T6["T6<br/>180d"] T7["T7<br/>All"]

    S0["S0 Dashboard"] S0T0["P0 P1"] S0T1["P0 P1"] S0T2["P0 P1"] S0T3["P0 P1"] S0T4["P0 P1"] S0T5["P0 P1"] S0T6["P0 P1"] S0T7["P0 P1"]
    S1["S1 Daily"] S1T0["P0 P1"] S1T1["P0 P1"] S1T2["P0 P1"] S1T3["P0 P1"] S1T4["P0 P1"] S1T5["P0 P1"] S1T6["P0 P1"] S1T7["P0 P1"]
    S7["S7 Sessions"] S7T0["P0 P1"] S7T1["P0 P1"] S7T2["P0 P1"] S7T3["P0 P1"] S7T4["P0 P1"] S7T5["P0 P1"] S7T6["P0 P1"] S7T7["P0 P1"]

    style H fill:#1E293B,color:#fff
    style S0 fill:#3B82F6,color:#fff
    style S1 fill:#10B981,color:#fff
    style S7 fill:#F59E0B,color:#000
```

## Test Architecture

```mermaid
graph LR
    subgraph "Test Runner"
        PW["Playwright"]
    end

    subgraph "Web Server"
        VITE["Vite Dev<br/>:5274"]
        BE["Backend API<br/>:8101"]
    end

    subgraph "Backend Engine"
        DDB["DuckDB<br/>stateless"]
        SQL["SQLite<br/>cached"]
    end

    PW --> VITE
    VITE --> BE
    BE --> DDB
    BE --> SQL

    style PW fill:#E11D48,color:#fff
    style VITE fill:#646CFF,color:#fff
    style BE fill:#009688,color:#fff
    style DDB fill:#FFC107,color:#000
    style SQL fill:#2196F3,color:#fff
```

### Backend Selection

By default, **both backends run in a single test session** — Playwright starts
two server pairs (sqlite on :8101/:5274, duckdb on :8102/:5275) and runs every
test against both. Screenshots and logs are engine-prefixed for comparison.

```bash
# Both engines (default — full coverage)
make test-frontend-e2e

# Single engine (faster iteration)
make test-frontend-e2e-sqlite
make test-frontend-e2e-duckdb
```

## Test Files

| File | Scope | Tests |
|------|-------|-------|
| `filters.spec.ts` | Universal filters across all sections | Section loading, filter permutations, URL params, API verification |
| `project-sessions-sort.spec.ts` | `/sessions/:projectId` sorting | Column sort, URL deep-links, sort persistence |
| `session-detail-filter.spec.ts` | `/sessions/:projectId/:sessionId` message filter | Kind dropdown, URL params, deep-links |

## Global Filters

Every page shares two global filters managed by `useFilters` hook:

| Filter | URL Param | Default | Behavior |
|--------|-----------|---------|----------|
| Time Range | `?days=N` | 30 (omitted from URL) | 1, 3, 7, 14, 30, 90, 180, 0 (all) |
| Project | `?project=ID` | All (omitted from URL) | Encoded project ID |

Page-local filters (sort, message kind) are managed by individual components
and do NOT leak into sidebar navigation links.

## Running Tests

```bash
# Run all e2e tests
make test-frontend-e2e

# Run with Playwright UI (interactive debugging)
npm --prefix frontend run test:e2e:ui

# Run specific test file
npx --prefix frontend playwright test e2e/filters.spec.ts

# Run with headed browser (watch mode)
npx --prefix frontend playwright test --headed
```
