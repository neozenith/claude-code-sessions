# Suggested Commands for claude-code-sessions

## Installation
```bash
make install              # Install all dependencies (backend + frontend)
make install-backend      # uv sync --all-groups
make install-frontend     # npm --prefix frontend install
```

## Development (AI Agent Ports)
```bash
make agentic-dev-backend  # Port 8101
make agentic-dev-frontend # Port 5274
```

## Development (Human Ports)
```bash
make dev-backend          # Port 8100
make dev-frontend         # Port 5273
```

## Code Quality
```bash
make format               # Format with ruff
make lint                 # Lint with ruff + eslint
make typecheck            # mypy + tsc
make test                 # Run all tests (pytest + vitest)
```

## Data
```bash
make sync-projects        # rsync from ~/.claude/projects/
```

## Important Notes
- **Never cd** into subdirectories - use relative paths from project root
- Use `uv run` for Python commands
- Use `npm --prefix frontend` for frontend commands
- AI agents should always use the agentic ports (8101, 5274)
