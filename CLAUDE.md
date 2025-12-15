# Claude Code Sessions Analytics

## Project Overview

FastAPI + React dashboard for visualizing Claude Code session usage and costs from `~/.claude/projects/` JSONL files using DuckDB.

## Architecture

```
claude-code-sessions/
├── src/claude_code_sessions/  # FastAPI + DuckDB backend
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Configuration
│   └── queries/               # SQL query files
├── frontend/                  # React + Vite + Tailwind + shadcn
│   └── src/
│       ├── components/ui/     # shadcn components
│       ├── pages/             # Dashboard pages
│       └── lib/utils.ts       # Utility functions
├── projects/                  # rsync'd copy of ~/.claude/projects/
├── pyproject.toml             # Python dependencies (uv)
└── Makefile                   # Command central
```

## Tech Stack

### Backend
- **FastAPI** - API framework
- **DuckDB** - Analytics database
- **uv** - Package and environment management
- **ruff** - Formatting and linting
- **mypy** - Strict type checking

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **shadcn/ui** - Component library
- **Plotly.js** - Charts
- **Lucide React** - Icons
- **Vitest** - Test runner

## Port Configuration

| Developer | Backend | Frontend |
|-----------|---------|----------|
| Human     | 8100    | 5273     |
| AI Agent  | 8101    | 5274     |

**Always use agentic ports when developing as an AI agent!**

## Commands

### Installation
```bash
make install              # Install all dependencies
make install-backend      # uv sync --all-groups
make install-frontend     # npm --prefix frontend install
```

### Development
```bash
# Human developer
make dev-backend          # Port 8100
make dev-frontend         # Port 5273

# AI agent (USE THESE!)
make agentic-dev-backend  # Port 8101
make agentic-dev-frontend # Port 5274
```

### Code Quality
```bash
make format               # Format with ruff
make lint                 # Lint with ruff + eslint
make typecheck            # mypy + tsc
make test                 # Run all tests
```

### Data
```bash
make sync-projects        # rsync from ~/.claude/projects/
```

## Important Rules

### Never Do
- `cd` into subdirectories in Makefile
- Use `requirements.txt` (use `pyproject.toml`)
- Use pip directly (use `uv`)

### Always Do
- Use `npm --prefix frontend` for frontend commands
- Use `uv run` for Python commands
- Stay at repo root for all operations
- Use `@/` import alias in frontend

## Data Schema

### Session JSONL Structure
```json
{
  "timestamp": "ISO8601",
  "message": {
    "model": "claude-sonnet-4-5-20250929",
    "usage": {
      "input_tokens": 1000,
      "output_tokens": 500,
      "cache_read_input_tokens": 200,
      "cache_creation_input_tokens": 100,
      "cache_creation": {
        "ephemeral_5m_input_tokens": 50
      }
    }
  }
}
```

### Pricing (per million tokens)
| Model | Input | Output | Cache Read | Cache Write 5m |
|-------|-------|--------|------------|----------------|
| claude-sonnet-4-5 | $3.00 | $15.00 | $0.30 | $3.75 |
| claude-opus-4 | $15.00 | $75.00 | $1.50 | $18.75 |
| claude-haiku-4-5 | $1.00 | $5.00 | $0.10 | $1.25 |

## Frontend Structure

### Pages (with Plotly charts)
- **Dashboard** - Summary cards, monthly cost bar chart
- **Daily** - Cost line chart, token stacked bars
- **Weekly** - Cost bars, session trends
- **Monthly** - Cost bars, model distribution pie
- **Projects** - Horizontal bar chart, data table

### shadcn Components
- Card, CardHeader, CardTitle, CardContent
- Button (with variants)
- More can be added from https://ui.shadcn.com

## API Endpoints

```
GET /api/health          # Health check
GET /api/summary         # Overall usage summary
GET /api/usage/daily     # Daily breakdown
GET /api/usage/weekly    # Weekly breakdown
GET /api/usage/monthly   # Monthly breakdown
GET /api/usage/sessions  # Per-session details
GET /api/projects        # Projects with stats
```

## Environment Variables

```bash
BACKEND_PORT=8000        # Backend port
BACKEND_HOST=0.0.0.0     # Backend host
PROJECTS_PATH=./projects # Path to projects data
```

## Session Memory

### Current State
- Project fully set up with uv + shadcn
- Backend in src/claude_code_sessions/
- Frontend with shadcn components configured

### Patterns to Remember
- Import paths use `@/` alias (e.g., `@/hooks/useApi`)
- All Python code must pass mypy strict mode
- Use Card component for chart containers
- Lucide icons for navigation

### Old backend/ Directory
The old `backend/` directory can be deleted - code has been moved to `src/claude_code_sessions/`.
