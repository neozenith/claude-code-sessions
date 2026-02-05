# Project Overview: claude-code-sessions

## Purpose
FastAPI + React dashboard for visualizing Claude Code session usage and costs from `~/.claude/projects/` JSONL files using DuckDB.

## Tech Stack

### Backend
- **FastAPI** - API framework
- **DuckDB** - Analytics database (in-memory queries on JSONL files)
- **uv** - Package and environment management
- **ruff** - Formatting and linting
- **mypy** - Strict type checking

### Frontend
- **React 18** + **Vite** - UI framework and build tool
- **Tailwind CSS** - Styling
- **shadcn/ui** - Component library
- **Plotly.js** - Charts
- **Lucide React** - Icons
- **Vitest** - Test runner

## Directory Structure
```
claude-code-sessions/
├── src/claude_code_sessions/  # FastAPI backend
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Configuration
│   └── queries/               # SQL query files (DuckDB)
├── frontend/                  # React + Vite frontend
│   └── src/
│       ├── components/ui/     # shadcn components
│       ├── pages/             # Dashboard pages
│       ├── hooks/             # Custom hooks (useFilters, useApi)
│       └── lib/               # Utilities and API client
├── tests/                     # Python tests (pytest)
├── projects/                  # rsync'd copy of ~/.claude/projects/
├── pyproject.toml             # Python dependencies (uv)
└── Makefile                   # Command central
```

## Data Schema

### Session JSONL Structure
Files located at: `projects/{project_id}/{session_id}.jsonl`
Subagent files at: `projects/{project_id}/{session_id}/subagents/{agent_id}.jsonl`

Key fields:
- `uuid` - Unique event identifier
- `parentUuid` - Links to parent event (tree structure)
- `sessionId` - Session ID
- `type` - Event type (user, assistant, system)
- `timestamp` - ISO8601 timestamp
- `agentId` - Agent identifier (for subagents)
- `isSidechain` - Boolean indicating subagent
- `slug` - Human-readable agent name
- `message` - Contains model, usage, content
