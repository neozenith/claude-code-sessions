# Code Style and Conventions

## Python (Backend)
- **Type hints**: Required for all functions (mypy strict mode)
- **Formatter**: ruff
- **Import style**: Absolute imports from `claude_code_sessions.`
- **Docstrings**: Google style for public functions
- **Testing**: pytest with FastAPI TestClient

## TypeScript/React (Frontend)
- **Import alias**: Use `@/` for `src/` imports (e.g., `@/hooks/useApi`)
- **Components**: Function components with TypeScript
- **Hooks**: Custom hooks in `hooks/` directory
- **State**: URL params for filters (via useSearchParams)
- **Styling**: Tailwind CSS classes, shadcn components
- **Testing**: Vitest

## SQL Queries (DuckDB)
- Stored in `src/claude_code_sessions/queries/*.sql`
- Use placeholders: `__PROJECTS_GLOB__`, `__DAYS_FILTER__`, `__PROJECT_FILTER__`
- Always handle NULL values with COALESCE
- Use `TRY_CAST` for safe type conversion
- CTEs for readable query structure

## Universal Filters Pattern
- Days filter: `?days=7` (0 or omitted = all time)
- Project filter: `?project={project_id}`
- Filters preserved in URL for shareable links
- Applied via `useFilters` hook in frontend
