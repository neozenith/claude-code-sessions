from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
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


def build_filters(days: int | None = None, project: str | None = None) -> dict[str, str]:
    """Build filter dict for SQL query placeholders.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)

    Returns:
        Dict with DAYS_FILTER and PROJECT_FILTER keys for SQL replacement
    """
    filters: dict[str, str] = {}

    # Days filter
    if days and days > 0:
        filters["DAYS_FILTER"] = (
            f"AND TRY_CAST(timestamp AS TIMESTAMP) >= CURRENT_DATE - INTERVAL '{days} days'"
        )
    else:
        filters["DAYS_FILTER"] = ""

    # Project filter
    if project:
        # Escape single quotes in project ID to prevent SQL injection
        safe_project = project.replace("'", "''")
        filters["PROJECT_FILTER"] = (
            f"AND regexp_extract(filename, 'projects/([^/]+)/', 1) = '{safe_project}'"
        )
    else:
        filters["PROJECT_FILTER"] = ""

    return filters


def get_file_mtimes_df(projects_path: Path) -> pd.DataFrame:
    """Get file modification times as a pandas DataFrame.

    DuckDB can query this DataFrame directly by variable name - zero copy!

    Args:
        projects_path: Path to the projects directory

    Returns:
        DataFrame with columns: filename (str), mtime_date (str YYYY-MM-DD)
    """
    records = []
    for filepath in projects_path.glob("**/*.jsonl"):
        mtime = filepath.stat().st_mtime
        mtime_date = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
        # Use absolute path string to match what DuckDB's read_json_auto returns
        # when given an absolute glob path
        records.append({"filename": str(filepath.resolve()), "mtime_date": mtime_date})

    return pd.DataFrame(records)


def execute_query(
    query_name: str,
    filters: dict[str, str] | None = None,
    dataframes: dict[str, pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """Execute a SQL query and return results as list of dicts.

    Args:
        query_name: Name of the SQL query file (without .sql extension)
        filters: Optional dict of filter replacements (e.g., {"PROJECT_FILTER": "my-project"})
        dataframes: Optional dict of DataFrames to register with DuckDB.
                   Keys are table names, values are DataFrames.
                   DuckDB can then query these directly in SQL (zero-copy!).
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

        # Register DataFrames with DuckDB - they become queryable tables
        if dataframes:
            for table_name, df in dataframes.items():
                conn.register(table_name, df)

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
async def get_summary(days: int | None = None, project: str | None = None) -> list[dict[str, Any]]:
    """Get overall usage summary.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters = build_filters(days, project)
    return execute_query("summary", filters)


@app.get("/api/usage/daily")
async def get_daily_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    """Get daily usage breakdown.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters = build_filters(days, project)
    return execute_query("by_day", filters)


@app.get("/api/usage/weekly")
async def get_weekly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    """Get weekly usage breakdown.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters = build_filters(days, project)
    return execute_query("by_week", filters)


@app.get("/api/usage/monthly")
async def get_monthly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    """Get monthly usage breakdown.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters = build_filters(days, project)
    return execute_query("by_month", filters)


@app.get("/api/usage/sessions")
async def get_sessions(days: int | None = None, project: str | None = None) -> list[dict[str, Any]]:
    """Get per-session usage details.

    Args:
        days: Number of days to filter (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters = build_filters(days, project)
    return execute_query("sessions", filters)


@app.get("/api/projects")
async def get_projects(days: int | None = None) -> list[dict[str, Any]]:
    """Get list of projects with usage stats.

    Args:
        days: Number of days to filter (None or 0 = all time).
              Use this to get projects active within the time range.
    """
    # Build filters - project filter not applicable here (we're listing all projects)
    filters = build_filters(days, None)
    data = execute_query("by_month", filters)
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

    # Sort by cost (highest first)
    sorted_projects = sorted(projects.values(), key=lambda p: p["total_cost_usd"], reverse=True)
    return sorted_projects


@app.get("/api/usage/top-projects-weekly")
async def get_top_projects_weekly(days: int | None = None) -> list[dict[str, Any]]:
    """Get weekly usage for top 3 projects.

    Args:
        days: Number of days to filter (None or 0 = all time, default shows last 56 days/8 weeks)
    """
    filters: dict[str, str] = {}
    # Default to 56 days (8 weeks) if no filter specified
    effective_days = days if days is not None else 56
    if effective_days and effective_days > 0:
        filters["DAYS_FILTER"] = (
            f"AND TRY_CAST(timestamp AS TIMESTAMP) >= "
            f"CURRENT_DATE - INTERVAL '{effective_days} days'"
        )
    else:
        filters["DAYS_FILTER"] = ""
    return execute_query("top_projects_weekly", filters)


@app.get("/api/usage/hourly")
async def get_hourly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    """Get hourly usage breakdown for configurable time range.

    Args:
        days: Number of days to query (None or 0 = all time)
        project: Project ID to filter by (None = all projects)
    """
    filters: dict[str, str] = {}
    # Add days filter - 0 or None means all time
    # Note: Uses local timezone for hourly view
    if days and days > 0:
        filters["DAYS_FILTER"] = (
            f"AND TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE "
            f"'Australia/Melbourne' >= CURRENT_DATE - INTERVAL '{days} days'"
        )
    else:
        filters["DAYS_FILTER"] = ""

    # Add project filter
    if project:
        safe_project = project.replace("'", "''")
        filters["PROJECT_FILTER"] = (
            f"AND regexp_extract(filename, 'projects/([^/]+)/', 1) = '{safe_project}'"
        )
    else:
        filters["PROJECT_FILTER"] = ""

    return execute_query("by_hour", filters)


@app.get("/api/timeline/events/{project_id}")
async def get_timeline_events(project_id: str, days: int | None = None) -> list[dict[str, Any]]:
    """Get event-level timeline data for a specific project.

    Returns individual events with cumulative output tokens per session,
    ordered by session first event time for timeline visualization.

    Args:
        project_id: The project ID to filter events for
        days: Optional number of days to filter (None = all time)
    """
    filters = {"PROJECT_FILTER": project_id}
    # Add days filter - 0 or None means all time
    if days and days > 0:
        filters["DAYS_FILTER"] = f"AND timestamp_utc >= NOW() - INTERVAL '{days} days'"
    else:
        filters["DAYS_FILTER"] = ""
    return execute_query("timeline_events", filters)


@app.get("/api/schema-timeline")
async def get_schema_timeline(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    """Get schema timeline data showing JSON path evolution over time.

    Returns one marker per day per JSON path. Uses file modification time
    as fallback for records without timestamps. All timestamps are truncated
    to day level for cleaner visualization.

    Args:
        days: Optional number of days to filter (None = all time)
        project: Optional project ID to filter
    """
    filters: dict[str, str] = {}

    # Add days filter
    if days and days > 0:
        filters["DAYS_FILTER"] = f"AND event_date >= CURRENT_DATE - INTERVAL '{days} days'"
    else:
        filters["DAYS_FILTER"] = ""

    # Add project filter
    if project:
        filters["PROJECT_FILTER"] = f"AND project_id = '{project}'"
    else:
        filters["PROJECT_FILTER"] = ""

    # Get file mtimes as DataFrame - DuckDB queries this directly (zero-copy!)
    projects_path = get_projects_path()
    file_mtimes_df = get_file_mtimes_df(projects_path)

    return execute_query(
        "schema_timeline",
        filters,
        dataframes={"file_mtimes": file_mtimes_df},
    )


# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)


if __name__ == "__main__":
    main()
