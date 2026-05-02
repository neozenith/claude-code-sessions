import argparse
import logging
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from claude_code_sessions.config import (
    BACKEND_HOST,
    BACKEND_PORT,
    HOME_PROJECTS_PATH,
    PROJECTS_PATH,
)
from claude_code_sessions.database.sqlite.kg.payload import (
    VALID_SEED_METRICS,
    KGDataMissing,
    KGPayload,
    SeedMetric,
)

# Configure logging BEFORE importing the database layer — the import
# itself triggers cache construction (module-level SQLiteDatabase(...)
# instance below), which emits phase banners we want the user to see.
# Uvicorn later installs its own handlers for "uvicorn"/"uvicorn.access",
# but leaves everyone else alone, so this basicConfig governs our own
# log.info() calls for the rest of the process lifetime.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

from claude_code_sessions.database import Database, SQLiteDatabase  # noqa: E402

log = logging.getLogger(__name__)

app = FastAPI(title="Claude Code Sessions Analytics")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database backend — SQLite is now the only supported engine. Stored on
# ``app.state`` for lifecycle management and so test fixtures can swap it
# for an isolated in-memory instance without mutating a module-level
# global.
app.state.db = SQLiteDatabase(
    local_projects_path=PROJECTS_PATH,
    home_projects_path=HOME_PROJECTS_PATH,
)


def get_db() -> Database:
    """Typed accessor for the current database backend."""
    db: Database = app.state.db
    return db


# ---------------------------------------------------------------------------
# Exception handlers — convert database-layer errors to HTTP responses
# ---------------------------------------------------------------------------


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(_request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(LookupError)
async def lookup_error_handler(_request: Request, exc: LookupError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Routes — all data access goes through get_db()
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Claude Code Sessions Analytics API"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "projects_path": str(get_db().projects_path)}


@app.get("/api/summary")
async def get_summary(days: int | None = None, project: str | None = None) -> list[dict[str, Any]]:
    return get_db().get_summary(days=days, project=project)


@app.get("/api/usage/daily")
async def get_daily_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_daily_usage(days=days, project=project)


@app.get("/api/usage/weekly")
async def get_weekly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_weekly_usage(days=days, project=project)


@app.get("/api/usage/monthly")
async def get_monthly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_monthly_usage(days=days, project=project)


@app.get("/api/usage/sessions")
async def get_sessions(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_session_usage(days=days, project=project)


@app.get("/api/projects")
async def get_projects(days: int | None = None) -> list[dict[str, Any]]:
    return get_db().get_projects(days=days)


@app.get("/api/usage/top-projects-weekly")
async def get_top_projects_weekly(days: int | None = None) -> list[dict[str, Any]]:
    return get_db().get_top_projects_weekly(days=days)


@app.get("/api/usage/hourly")
async def get_hourly_usage(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_hourly_usage(days=days, project=project)


@app.get("/api/timeline/events/{project_id}")
async def get_timeline_events(
    project_id: str, days: int | None = None
) -> list[dict[str, Any]]:
    return get_db().get_timeline_events(project_id, days=days)


@app.get("/api/schema-timeline")
async def get_schema_timeline(
    days: int | None = None, project: str | None = None
) -> list[dict[str, Any]]:
    return get_db().get_schema_timeline(days=days, project=project)


@app.get("/api/sessions")
async def get_sessions_list(
    days: int | None = None,
    project: str | None = None,
    sort_by: str = "last_active",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    return get_db().get_sessions_list(
        days=days, project=project, sort_by=sort_by, sort_order=sort_order
    )


@app.get("/api/sessions/{project_id}/{session_id}")
async def get_session_events(
    project_id: str,
    session_id: str,
    event_uuid: str | None = None,
) -> list[dict[str, Any]]:
    return get_db().get_session_events(project_id, session_id, event_uuid=event_uuid)


@app.get("/api/sessions/{project_id}/{session_id}/events/{event_uuid}/raw")
async def get_event_raw_json(
    project_id: str,
    session_id: str,
    event_uuid: str,
) -> dict[str, Any]:
    """On-demand raw JSONL line for one event.

    The cache no longer stores ``raw_json`` (a 2+ GB duplicate of the source
    files). This endpoint reads the specific line from disk via the
    (filepath, line_number) coordinate recorded during ingestion.
    """
    line = get_db().get_event_raw_json(project_id, session_id, event_uuid)
    if line is None:
        return {"event_uuid": event_uuid, "raw_json": None, "found": False}
    return {"event_uuid": event_uuid, "raw_json": line, "found": True}


@app.get("/api/domains")
async def get_domains() -> dict[str, list[str]]:
    return get_db().get_domains()


# ---------------------------------------------------------------------------
# event_calls fact-table endpoints
# ---------------------------------------------------------------------------


@app.get("/api/calls/timeline")
async def get_calls_timeline(
    granularity: str = "daily",
    days: int | None = None,
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Call counts bucketed by (time, call_type) for stacked time-series charts."""
    return get_db().get_calls_timeline(granularity=granularity, days=days, project=project)


@app.get("/api/calls/top")
async def get_top_calls(
    call_type: str,
    days: int | None = None,
    project: str | None = None,
    limit: int = 20,
    exclude: str | None = None,
) -> list[dict[str, Any]]:
    """Top-N distinct call names for a given call_type.

    ``call_type`` is one of tool/skill/subagent/cli/rule/make_target.
    ``exclude`` is a comma-separated list of call names to filter out
    before ranking (useful for hiding noisy unix utilities from the
    CLI chart, e.g. ``?exclude=wc,head,tail,grep,echo``).
    """
    exclude_list = [s.strip() for s in exclude.split(",") if s.strip()] if exclude else None
    return get_db().get_top_calls(
        call_type=call_type,
        days=days,
        project=project,
        limit=limit,
        exclude=exclude_list,
    )


# ---------------------------------------------------------------------------
# Full-text search endpoint
# ---------------------------------------------------------------------------


@app.get("/api/search")
async def search_events(
    q: str = "",
    days: int | None = None,
    project: str | None = None,
    msg_kind: str | None = None,
    limit: int = 50,
    mode: str = "keyword",
) -> list[dict[str, Any]]:
    """Search across event message content.

    Two ranking modes are dispatched from this single endpoint so
    frontend code has a uniform response shape:

    * ``mode=keyword`` (default): FTS5 BM25 search over
      ``events_fts``. ``rank`` is a BM25 score (lower = more relevant).
      ``snippet`` includes ``<mark>…</mark>`` highlight tags.
    * ``mode=semantic``: HNSW vector KNN against the ``chunks_vec``
      index, using the same NomicEmbed GGUF that built the index to
      embed the query server-side. ``rank`` is cosine distance
      (lower = more similar). ``snippet`` is the matched chunk's text
      verbatim (no highlights — semantic matches don't localise to a
      token).

    Both modes respect the global ``days`` / ``project`` filters and
    the optional ``msg_kind`` filter. Empty / whitespace-only queries
    short-circuit to ``[]`` in the backend, so it's safe to call on
    every keystroke during debounce.

    Unknown mode values fall back to keyword search — a no-op today,
    but documented so future-us doesn't remove it and break clients
    that sent a typo.
    """
    db = get_db()
    if mode == "semantic":
        return db.semantic_search_events(
            q, days=days, project=project, msg_kind=msg_kind, limit=limit
        )
    return db.search_events(
        q, days=days, project=project, msg_kind=msg_kind, limit=limit
    )


# ---------------------------------------------------------------------------
# Knowledge graph endpoint (resolved-entity graph only)
# ---------------------------------------------------------------------------
# This project intentionally does NOT serve the base graph — only the
# entity-resolved variant — so there is no /api/kg/{table_id} dispatch
# and no /api/kg/tables discovery endpoint. One route, one response shape.
# Errors:
#   422 — KGDataMissing (pipeline hasn't populated nodes/edges yet)
#   400 — invalid seed_metric / out-of-range numeric param


@app.get("/api/kg/er")
async def kg_er(
    resolution: float | None = None,
    top_n: int = 50,
    seed_metric: str = "edge_betweenness",
    max_depth: int = 0,
    min_degree: int = 1,
    days: int | None = None,
    project: str | None = None,
) -> KGPayload:
    if seed_metric not in VALID_SEED_METRICS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid seed_metric {seed_metric!r}; "
                f"expected one of {list(VALID_SEED_METRICS)}"
            ),
        )
    try:
        return get_db().get_kg_er(
            resolution=resolution,
            top_n=top_n,
            seed_metric=cast(SeedMetric, seed_metric),
            max_depth=max_depth,
            min_degree=min_degree,
            days=days,
            project=project,
        )
    except KGDataMissing as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


def main() -> None:
    from claude_code_sessions import config

    parser = argparse.ArgumentParser(description="Claude Code Sessions Analytics API")
    parser.add_argument(
        "--block-domains",
        nargs="*",
        default=None,
        help="Domains to block (overrides BLOCKED_DOMAINS env var). "
        "E.g.: --block-domains work clients",
    )
    args = parser.parse_args()

    # CLI flag overrides env var
    if args.block_domains is not None:
        config.BLOCKED_DOMAINS = args.block_domains

    if config.BLOCKED_DOMAINS:
        log.warning("Domain filtering active — blocked domains: %s", config.BLOCKED_DOMAINS)

    # Backend is pre-initialised at module load (SQLite only). No runtime
    # swap needed here — the module-level ``app.state.db`` stands.
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)


if __name__ == "__main__":
    main()
