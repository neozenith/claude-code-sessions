# Schema Timeline Visualization Spec

## Overview

Create a new visualization section called **Schema Timeline** that shows the evolution of JSON schema attributes over time in Claude Code session data.

This visualization will help identify:
- When new fields were introduced to the session schema
- When fields were deprecated or removed
- Schema version drift across Claude Code CLI versions

## Visual Design

### Axes
- **X-axis**: Time (event timestamps)
- **Y-axis**: JSON paths of attributes (e.g., `message.usage.input_tokens`, `isSidechain`, `agentId`)

### Grouping & Sorting
- Y-axis grouped by JSON path
- Vertically sorted by the **first appearance time** of each attribute (earliest at top)
- Color segmented by JSON path (each unique path gets a distinct color)

### Event Markers
- Each event rendered as a **circle**
- Opacity: **60%** (to show density/overlap)
- Size: Uniform (or optionally scaled by frequency)

### Hover Interaction
- Display: **Event timestamp**
- Display: **Claude Code version** (from `version` field, where available)
- Optionally show: Sample value of the attribute

## Data Requirements

### JSON Path Extraction
Extract all unique JSON paths from session JSONL files. Examples:
```
timestamp
type
uuid
parentUuid
sessionId
version
gitBranch
agentId
isSidechain
userType
cwd
requestId
message.model
message.id
message.type
message.role
message.usage.input_tokens
message.usage.output_tokens
message.usage.cache_creation_input_tokens
message.usage.cache_read_input_tokens
message.usage.cache_creation.ephemeral_5m_input_tokens
message.usage.cache_creation.ephemeral_1h_input_tokens
message.usage.service_tier
```

### Backend API
Create new endpoint: `GET /api/schema-timeline`

Query parameters:
- `days` (optional): Filter to last N days
- `project` (optional): Filter to specific project

Response format:
```json
{
  "paths": [
    {
      "json_path": "message.usage.service_tier",
      "first_seen": "2025-12-01T00:00:00Z",
      "last_seen": "2026-01-20T00:00:00Z",
      "event_count": 1234
    }
  ],
  "events": [
    {
      "timestamp": "2025-12-17T01:10:55.075Z",
      "json_path": "message.usage.input_tokens",
      "version": "2.0.71"
    }
  ]
}
```

## URL State Management
- Schema Timeline should support URL-based state
- Example: `/schema-timeline?days=30&project=play/claude/code/sessions`

## Implementation Notes

### Sampling Strategy
- Full dataset may be too large; implement sampling or aggregation
- Consider: Show first N occurrences per path per day
- Or: Aggregate to daily/hourly buckets with count

### Performance
- Use DuckDB's JSON path extraction capabilities
- Consider pre-computing path metadata in a separate query

---

## Self-Validation Requirements

**Copy-paste this entire spec.md verbatim and reload after any compaction event.**

### Testing Protocol

Iterate until ALL feature requests are addressed and you can evidence that they are addressed via:

1. **Playwright Screenshots**
   - Take screenshots using Playwright MCP
   - Evaluate screenshots visually to confirm:
     - X-axis shows time correctly
     - Y-axis shows JSON paths sorted by first appearance
     - Colors differentiate paths
     - Circles have 60% opacity
     - Hover shows timestamp and version

2. **Test Suite**
   - Write and run tests that demonstrate the capability
   - Backend tests for the new API endpoint
   - Frontend tests for the visualization component
   - Tests must actually pass when run

3. **Quality Controls**
   - All quality controls must pass:
     - `make format` - Code formatting
     - `make lint` - Linting (ruff + eslint)
     - `make typecheck` - Type checking (mypy + tsc)
     - `make test` - All tests passing
   - **DO NOT** disable checks or lower the quality bar

### Development Workflow

1. Start agentic dev servers:
   ```bash
   make agentic-dev-backend   # Port 8101
   make agentic-dev-frontend  # Port 5274
   ```

2. Sync latest data:
   ```bash
   make sync-projects
   ```

3. Iterate on implementation

4. Validate with Playwright MCP screenshots

5. Run full quality check:
   ```bash
   make format && make lint && make typecheck && make test
   ```

### Data Sync Reminder
Run `make sync-projects` periodically to rsync from `~/.claude/projects/` to get latest session data.
