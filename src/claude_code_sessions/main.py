from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from claude_code_sessions.config import (
    BACKEND_HOST,
    BACKEND_PORT,
    HOME_PROJECTS_PATH,
    PRICING_CSV_PATH,
    PROJECTS_PATH,
    QUERIES_PATH,
)

app = FastAPI(title="Claude Code Sessions Analytics")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_projects_path() -> Path:
    """Get the projects path, preferring local copy over home directory."""
    if PROJECTS_PATH.exists() and any(PROJECTS_PATH.iterdir()):
        return PROJECTS_PATH
    if HOME_PROJECTS_PATH.exists():
        return HOME_PROJECTS_PATH
    raise HTTPException(status_code=500, detail="No projects data found")


def execute_query(
    query_name: str, filters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Execute a SQL query and return results as list of dicts.

    Args:
        query_name: Name of the SQL query file (without .sql extension)
        filters: Optional dict of filter replacements (e.g., {"PROJECT_FILTER": "my-project"})
    """
    query_file = QUERIES_PATH / f"{query_name}.sql"
    if not query_file.exists():
        raise HTTPException(status_code=404, detail=f"Query {query_name} not found")

    sql = query_file.read_text()
    projects_path = get_projects_path()

    # Replace placeholder paths with actual paths
    sql = sql.replace("__PROJECTS_GLOB__", f"{projects_path}/**/*.jsonl")
    sql = sql.replace("__PRICING_CSV_PATH__", str(PRICING_CSV_PATH))

    # Apply filters if provided
    if filters:
        for key, value in filters.items():
            sql = sql.replace(f"__{key}__", value)

    try:
        conn = duckdb.connect(":memory:")
        result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]
        conn.close()

        return [dict(zip(columns, row, strict=False)) for row in result]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Claude Code Sessions Analytics API"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "projects_path": str(get_projects_path())}


@app.get("/api/summary")
async def get_summary() -> list[dict[str, Any]]:
    """Get overall usage summary."""
    return execute_query("summary")


@app.get("/api/usage/daily")
async def get_daily_usage() -> list[dict[str, Any]]:
    """Get daily usage breakdown."""
    return execute_query("by_day")


@app.get("/api/usage/weekly")
async def get_weekly_usage() -> list[dict[str, Any]]:
    """Get weekly usage breakdown."""
    return execute_query("by_week")


@app.get("/api/usage/monthly")
async def get_monthly_usage() -> list[dict[str, Any]]:
    """Get monthly usage breakdown."""
    return execute_query("by_month")


@app.get("/api/usage/sessions")
async def get_sessions() -> list[dict[str, Any]]:
    """Get per-session usage details."""
    return execute_query("sessions")


@app.get("/api/projects")
async def get_projects() -> list[dict[str, Any]]:
    """Get list of projects with usage stats."""
    data = execute_query("by_month")
    # Aggregate by project
    projects: dict[str, dict[str, Any]] = {}
    for row in data:
        proj = row.get("project_id", "unknown")
        if proj not in projects:
            projects[proj] = {
                "project_id": proj,
                "total_cost_usd": 0.0,
                "session_count": 0,
                "event_count": 0,
            }
        projects[proj]["total_cost_usd"] += float(row.get("total_cost_usd", 0))
        projects[proj]["session_count"] += int(row.get("session_count", 0))
        projects[proj]["event_count"] += int(row.get("event_count", 0))

    return list(projects.values())


@app.get("/api/usage/top-projects-weekly")
async def get_top_projects_weekly() -> list[dict[str, Any]]:
    """Get weekly usage for top 3 projects over last 8 weeks."""
    return execute_query("top_projects_weekly")


@app.get("/api/usage/hourly")
async def get_hourly_usage(days: int = 14) -> list[dict[str, Any]]:
    """Get hourly usage breakdown for configurable time range.

    Args:
        days: Number of days to query (default: 14)
    """
    return execute_query("by_hour", {"DAYS": str(days)})


@app.get("/api/drilldown/projects")
async def get_drilldown_projects() -> list[dict[str, Any]]:
    """Get project-level drill-down with timezone-aware aggregation."""
    return execute_query("drilldown_projects")


@app.get("/api/drilldown/sessions/{project_id}")
async def get_drilldown_sessions(project_id: str) -> list[dict[str, Any]]:
    """Get sessions for a specific project with timezone info."""
    return execute_query("drilldown_sessions", {"PROJECT_FILTER": project_id})


@app.get("/api/drilldown/events/{project_id}/{session_id}")
async def get_drilldown_events(project_id: str, session_id: str) -> list[dict[str, Any]]:
    """Get event-level details for a specific session."""
    return execute_query(
        "drilldown_events",
        {"PROJECT_FILTER": project_id, "SESSION_FILTER": session_id},
    )


@app.get("/api/drilldown/daily/{project_id}")
async def get_drilldown_daily_detail(project_id: str) -> list[dict[str, Any]]:
    """Get daily detail showing UTC vs Local timezone differences."""
    return execute_query("drilldown_daily_detail", {"PROJECT_FILTER": project_id})


# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)


if __name__ == "__main__":
    main()
