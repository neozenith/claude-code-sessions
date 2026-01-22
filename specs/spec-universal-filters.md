# Universal Filters Implementation Spec

## Goal

Implement robust, tested global filters (time range and project) that work consistently across:
1. **All API endpoints** (DuckDB query level)
2. **All frontend visualizations**
3. **URL parameter synchronization**
4. **Cross-section navigation**

## Filter Definitions

### Time Range Filter (Relative)

A relative time range from "now" that includes:

| Option Index | Value | Label |
|--------------|-------|-------|
| 0 | `1` | Last 24 hours |
| 1 | `3` | Last 3 days |
| 2 | `7` | Last 7 days |
| 3 | `14` | Last 14 days |
| 4 | `30` | Last 30 days (default) |
| 5 | `90` | Last 90 days |
| 6 | `180` | Last 180 days |
| 7 | `0` | All Time |

**URL Parameter**: `days=<value>` (omitted for default 30)

### Project Filter

Either:
- **All Projects** (no filtering) - value: empty/null
- **Specific Project ID** - value: URL-encoded project path (e.g., `play%2Fclaude-code-sessions`)

**URL Parameter**: `project=<encoded_project_id>` (omitted for "All Projects")

## Architecture

### Visualization Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ App                                                                          │
│ ┌─────────────┐                                                              │
│ │ Layout.tsx  │ ← Contains global filter dropdowns                          │
│ │ useFilters()│ ← URL-synced state for `days` and `project`                 │
│ └─────────────┘                                                              │
│       │                                                                      │
│       ▼                                                                      │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Section (Page)                                                          │ │
│ │ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐      │ │
│ │ │ Visualization 1   │ │ Visualization 2   │ │ Visualization 3   │      │ │
│ │ │ useApi(endpoint1) │ │ useApi(endpoint2) │ │ useApi(endpoint3) │      │ │
│ │ └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘      │ │
│ │           │                     │                     │                │ │
│ └───────────┼─────────────────────┼─────────────────────┼────────────────┘ │
└─────────────┼─────────────────────┼─────────────────────┼──────────────────┘
              │                     │                     │
              ▼                     ▼                     ▼
     ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
     │ GET /api/...   │   │ GET /api/...   │   │ GET /api/...   │
     │ ?days=7        │   │ ?days=7        │   │ ?days=7        │
     │ &project=xxx   │   │ &project=xxx   │   │ &project=xxx   │
     └────────┬───────┘   └────────┬───────┘   └────────┬───────┘
              │                     │                     │
              ▼                     ▼                     ▼
     ┌────────────────────────────────────────────────────────┐
     │ DuckDB Query                                            │
     │ WHERE ... __DAYS_FILTER__ __PROJECT_FILTER__           │
     └────────────────────────────────────────────────────────┘
```

### Visualization Data Mapping

A utility script maintains a mapping of all Section → Visualization → API relationships:

**Script**: `scripts/visualisation_data_mapper.py`
**Output**: `docs/visualisation_data_mapping.json`

The mapping JSON structure:
```json
{
  "sections": [
    {
      "id": 0,
      "name": "Dashboard",
      "path": "/",
      "file": "frontend/src/pages/Dashboard.tsx",
      "visualizations": [
        {
          "id": 0,
          "name": "Summary Stats Cards",
          "apiEndpoint": "/api/summary",
          "apiFile": "src/claude_code_sessions/main.py:get_summary",
          "queryFile": "src/claude_code_sessions/queries/summary.sql"
        },
        {
          "id": 1,
          "name": "Monthly Cost Chart",
          "apiEndpoint": "/api/usage/monthly",
          "apiFile": "src/claude_code_sessions/main.py:get_monthly_usage",
          "queryFile": "src/claude_code_sessions/queries/by_month.sql"
        }
      ]
    }
  ],
  "metadata": {
    "generated_at": "2025-01-21T12:00:00Z",
    "total_sections": 9,
    "total_visualizations": 20,
    "total_api_endpoints": 12
  }
}
```

## Requirements

### R1: API-Level Filter Support

**R1.1**: All Data APIs MUST accept `days` and `project` query parameters:
- `days` (int, optional): 0 = all time, positive int = last N days
- `project` (str, optional): URL-decoded project ID to filter by

**R1.2**: All SQL query templates MUST include both filter placeholders:
```sql
WHERE ...
  __DAYS_FILTER__
  __PROJECT_FILTER__
```

**R1.3**: The `/api/projects` endpoint MUST support `days` parameter to return projects active within the time range.

**R1.4**: Project list in frontend MUST dynamically update when time range changes.

### R2: Frontend Filter Behavior

**R2.1**: All visualizations MUST call their APIs with current filter values.

**R2.2**: Filter changes MUST trigger re-fetch of all visualizations in the current section.

**R2.3**: Navigating between sections MUST preserve filter values.

**R2.4**: Filter values MUST be synced to URL parameters.

**R2.5**: Loading a URL with filter parameters MUST apply those filters immediately.

### R3: Testing Requirements

**R3.1**: Every API endpoint MUST have pytest tests covering:
- No filters (all time, all projects)
- Days filter only (various values)
- Project filter only
- Both filters combined
- Edge cases (invalid project, days=0)

**R3.2**: E2E tests using Playwright via Vitest MUST cover all permutations:
- 9 Sections × 8 Time Ranges × 2 Project options = 144 test cases

**R3.3**: Test ID format: `S{section}-V{vis}-T{time}-P{project}`
- Example: `S1-V0-T2-P0` = Section 1, Visualization 0, Time Range 2 (7 days), Project 0 (All)

**R3.4**: Screenshot naming: `{test_id}.png`
- Example: `S1-V0-T2-P0.png`

## File References

### Backend

| File | Purpose |
|------|---------|
| `src/claude_code_sessions/main.py` | FastAPI endpoints |
| `src/claude_code_sessions/queries/*.sql` | DuckDB query templates |
| `tests/test_api_filters.py` | API filter pytest tests |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/hooks/useFilters.ts` | Filter state and URL sync |
| `frontend/src/hooks/useApi.ts` | API data fetching with filters |
| `frontend/src/components/Layout.tsx` | Global filter dropdowns |
| `frontend/src/pages/*.tsx` | Section pages with visualizations |

### Testing

| File | Purpose |
|------|---------|
| `tests/test_api_filters.py` | Pytest tests for all API endpoints |
| `frontend/src/__tests__/e2e/filters.spec.ts` | Playwright e2e tests |

### Scripts & Docs

| File | Purpose |
|------|---------|
| `scripts/visualisation_data_mapper.py` | Generates visualization mapping |
| `docs/visualisation_data_mapping.json` | Current mapping state |

## Sections and Visualizations

| Section ID | Section Name | Path | Visualizations |
|------------|--------------|------|----------------|
| 0 | Dashboard | `/` | Summary Cards, Monthly Cost Chart, Top Projects |
| 1 | Daily Usage | `/daily` | Daily Cost Line, Token Breakdown Bars |
| 2 | Weekly Usage | `/weekly` | Weekly Cost Bars, Session Trends |
| 3 | Monthly Usage | `/monthly` | Monthly Cost Bars, Model Distribution |
| 4 | Hourly Usage | `/hourly` | Hourly Heatmap |
| 5 | Hour of Day | `/hour-of-day` | Hour Distribution Heatmap |
| 6 | Projects | `/projects` | Projects Table, Project Cost Bars |
| 7 | Timeline | `/timeline` | Event Timeline |
| 8 | Schema Timeline | `/schema-timeline` | Schema Evolution Timeline |

## API Endpoints

| Endpoint | Query File | Supports Days | Supports Project |
|----------|------------|---------------|------------------|
| `GET /api/summary` | `summary.sql` | ✅ | ✅ |
| `GET /api/usage/daily` | `by_day.sql` | ✅ | ✅ |
| `GET /api/usage/weekly` | `by_week.sql` | ✅ | ✅ |
| `GET /api/usage/monthly` | `by_month.sql` | ✅ | ✅ |
| `GET /api/usage/hourly` | `by_hour.sql` | ✅ | ✅ |
| `GET /api/usage/top-projects-weekly` | `top_projects_weekly.sql` | ✅ | N/A |
| `GET /api/usage/sessions` | `sessions.sql` | ✅ | ✅ |
| `GET /api/projects` | (aggregation) | ✅ | N/A |
| `GET /api/timeline/events/{project_id}` | `timeline_events.sql` | ✅ | (path param) |
| `GET /api/schema-timeline` | `schema_timeline.sql` | ✅ | ✅ |

## Failure Modes (Previously Observed)

### FM1: Filters Not Respected at API Level
**Symptom**: API called with parameters but returns unfiltered data
**Cause**: Endpoint receives params but doesn't pass to query
**Prevention**: Pytest tests for each endpoint verifying filtered results

### FM2: Filters Not Implemented in DuckDB Queries
**Symptom**: Query template lacks placeholder or placeholder not replaced
**Cause**: SQL template missing `__DAYS_FILTER__` or `__PROJECT_FILTER__`
**Prevention**: Linting script to verify all templates have placeholders

### FM3: Filters Not Forwarded from Frontend
**Symptom**: Frontend shows filters but API calls lack parameters
**Cause**: `buildApiQuery()` not called or result not used in fetch
**Prevention**: E2E tests that verify network requests include parameters

### FM4: No Test Coverage
**Symptom**: Regressions go undetected
**Cause**: Missing test suite
**Prevention**: Comprehensive pytest + Playwright test suites

### FM5: Difficult to Identify Which Visualization Failed
**Symptom**: "Tests failed" but unclear which exact scenario
**Cause**: Non-descriptive test names
**Prevention**: Unique test IDs (S#-V#-T#-P#) and per-test screenshots

## Implementation Checklist

### Phase 1: Backend Filter Support

- [ ] Add `__PROJECT_FILTER__` to all SQL templates
- [ ] Update all API endpoints to accept and apply `project` parameter
- [ ] Update `/api/projects` to accept `days` parameter
- [ ] Create `tests/test_api_filters.py` with comprehensive tests

### Phase 2: Frontend Filter Integration

- [ ] Verify `useFilters` hook correctly syncs all filter values to URL
- [ ] Verify `buildApiQuery` includes both `days` and `project`
- [ ] Verify all pages use filters in their API calls
- [ ] Add dynamic project list that updates based on time range

### Phase 3: Tooling

- [ ] Create `scripts/visualisation_data_mapper.py`
- [ ] Generate `docs/visualisation_data_mapping.json`

### Phase 4: E2E Testing

- [ ] Create `frontend/src/__tests__/e2e/filters.spec.ts`
- [ ] Implement test matrix (144 permutations)
- [ ] Add screenshot capture with unique IDs
- [ ] Integrate with Vitest

## Commands

```bash
# Backend development
make agentic-dev-backend   # Port 8101

# Frontend development
make agentic-dev-frontend  # Port 5274

# Run all tests
make test                  # Pytest + Vitest

# Run API tests only
uv run pytest tests/test_api_filters.py -v

# Run E2E tests only
npm --prefix frontend run test:e2e

# Generate visualization mapping
uv run python scripts/visualisation_data_mapper.py

# Quality checks
make typecheck
make lint
make format
```

## Success Criteria

1. ✅ All API endpoints accept and correctly apply `days` and `project` filters
2. ✅ All SQL queries include both filter placeholders
3. ✅ `tests/test_api_filters.py` passes with 100% endpoint coverage
4. ✅ Frontend project dropdown updates when time range changes
5. ✅ URL parameters persist across section navigation
6. ✅ Loading URL with parameters applies filters immediately
7. ✅ E2E test suite generates 144 screenshots with unique IDs
8. ✅ All tests pass in CI
