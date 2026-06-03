"""
Database Protocol for Claude Code Sessions analytics.

Defines the interface that all database backends must implement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from claude_code_sessions.database.sqlite.kg.payload import (
    KGCacheStats,
    KGPayload,
    SeedMetric,
)


@runtime_checkable
class Database(Protocol):
    """Interface for all data access in the Claude Code Sessions dashboard.

    Implementations may use SQLite, PostgreSQL, or any other backend.
    The API layer depends only on this protocol — never on a concrete class.
    """

    @property
    def projects_path(self) -> Path:
        """Resolved path to the projects data directory."""
        ...

    def get_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Overall usage summary with costs, event counts, subagent breakdown."""
        ...

    def get_daily_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Daily aggregated usage."""
        ...

    def get_weekly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Weekly aggregated usage."""
        ...

    def get_monthly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Monthly aggregated usage."""
        ...

    def get_hourly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Hourly usage breakdown for heatmap visualization."""
        ...

    def get_session_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Per-session token usage and cost details."""
        ...

    def get_sessions_list(
        self,
        *,
        days: int | None = None,
        project: str | None = None,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Sessions grouped by project with filtering and sorting."""
        ...

    def get_projects(self, *, days: int | None = None) -> list[dict[str, Any]]:
        """Project list aggregated by total cost, sessions, and events."""
        ...

    def get_top_projects_weekly(self, *, days: int | None = None) -> list[dict[str, Any]]:
        """Top projects by cost with weekly breakdown."""
        ...

    def get_timeline_events(
        self, project_id: str, *, days: int | None = None
    ) -> list[dict[str, Any]]:
        """Event-level timeline with cumulative output tokens for a project."""
        ...

    def get_schema_timeline(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """JSON path evolution timeline with version tracking."""
        ...

    def get_session_events(
        self, project_id: str, session_id: str, *, event_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        """All events for a specific session including subagent events."""
        ...

    def get_session_metrics(self, project_id: str, session_id: str) -> list[dict[str, Any]]:
        """Per-turn timing for a session's main thread: idle (assistant
        turn-end → next human prompt) and related spans, one row per
        assistant end-of-turn head."""
        ...

    def get_performance_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> dict[str, Any]:
        """Cross-session performance: per-model TPS rows + a context-ratio
        histogram, honoring the global days/project filters."""
        ...

    def get_session_summary(
        self, project_id: str, session_id: str, *, model: str
    ) -> dict[str, Any]:
        """The 3-lens summary for a session under ``model`` (G7).

        Returns a discriminated payload: ``{"status": "summarised", "lenses": {...}}``
        when a ``session_summaries`` row exists, else ``{"status": "not_summarised"}``
        — never a fabricated summary (ADR7.1)."""
        ...

    def get_rollup_summary(
        self,
        scope_path: str,
        time_granularity: str,
        time_bucket: str,
        *,
        strategy: str | None = None,
        model: str | None = None,
        days: int | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """The roll-up summary for a ``scope_path`` at a grain+bucket (G7).

        Optional ``strategy``/``model`` select a benchmark variant. Returns the
        ADR7.1 discriminated payload (``summarised`` with lenses, or
        ``not_summarised``)."""
        ...

    def list_scope_children(
        self, scope_path: str, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """The immediate child scopes of ``scope_path`` (next trie level only),
        derived from ingested projects and honoring the global days/project
        filters (G7)."""
        ...

    def list_summary_variants(self) -> list[dict[str, Any]]:
        """The distinct ``(strategy, model)`` pairs present in the roll-up table —
        the eval picker's option source (G7, ADR7.2)."""
        ...

    def get_project_scope(self, project_id: str) -> dict[str, Any]:
        """A project's resolved ``scope_path`` + root-first ancestor chain (G1),
        for the SessionDetail lineage breadcrumb (G9); ``scope_path`` is ``None``
        when unresolved."""
        ...

    # -- Extractive set-union claims (CR5) -----------------------------------

    def list_claim_models(self) -> list[str]:
        """Distinct models with extractive claim roll-ups (CR5)."""
        ...

    def list_claim_buckets(
        self, scope_path: str, grain: str, model: str, days: int | None = None
    ) -> list[dict[str, Any]]:
        """Time buckets for a scope×grain×model with claim/failure counts, restricted
        to the last-N-``days`` window (CR5)."""
        ...

    def get_claim_rollup(
        self, scope_path: str, grain: str, bucket: str, model: str, days: int | None = None
    ) -> dict[str, Any]:
        """Extractive roll-up for a scope×grain: per-lens claims ranked by COUNT +
        provenance, plus the parallel failure count (CR5). ``bucket`` empty = all claims
        set-unioned across buckets in the last-N-``days`` window; a set ``bucket`` drills
        down to that one bucket."""
        ...

    def get_session_claims(self, project_id: str, session_id: str, model: str) -> dict[str, Any]:
        """One session's L1 claims per lens, or its recorded failure (CR5)."""
        ...

    def get_session_rollup_memberships(
        self, project_id: str, session_id: str, model: str
    ) -> list[dict[str, Any]]:
        """Reverse provenance: roll-up buckets this session contributes to (CR5)."""
        ...

    def get_summarisation_coverage(
        self, model: str, scope: str | None = None, days: int | None = None
    ) -> dict[str, Any]:
        """Cache-summarisation completeness per project, optionally scoped to the
        explorer's current scope_path prefix and windowed to the last N ``days`` (CR5)."""
        ...

    def list_summary_buckets(
        self, scope_path: str, grain: str, strategy: str | None = None, model: str | None = None
    ) -> list[dict[str, Any]]:
        """Time buckets in the abstractive roll-up for a scope×grain (+ variant) (CR5)."""
        ...

    def list_claim_models_detail(self) -> list[dict[str, Any]]:
        """Models with claim data + on-disk registry models, flagged ``has_claims`` (CR5)."""
        ...

    def get_claims_coverage_pivot(
        self, model: str, grain: str, scope: str | None = None, days: int | None = None
    ) -> dict[str, Any]:
        """Done-vs-pending pivot (scope × bucket) at one grain, restricted to the
        subtree of ``scope`` (the explorer's page filter) and the last-N-``days``
        bucket columns, for the heatmap (CR5)."""
        ...

    def get_event_raw_json(self, project_id: str, session_id: str, event_uuid: str) -> str | None:
        """Fetch a single event's raw JSONL line from the source file on disk.

        Returns the raw line as stored in the JSONL source, or None if the
        event isn't found. This is an on-demand alternative to storing the
        raw payload in the cache — the ``events`` table tracks
        (source_file_id, line_number) which lets us seek to the right line.
        """
        ...

    def get_domains(self) -> dict[str, list[str]]:
        """Domain filtering status: available, blocked, and all discovered domains."""
        ...

    def is_project_blocked(self, project_id: str) -> bool:
        """Check if a project belongs to a blocked domain."""
        ...

    def get_calls_timeline(
        self,
        *,
        granularity: str,
        days: int | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        """Tool/skill/subagent/cli/rule call counts bucketed by time.

        Returns one row per ``(time_bucket, call_type)`` pair, with the
        total call count. Dashboards stack these into a time-series view.
        """
        ...

    def get_top_calls(
        self,
        *,
        call_type: str,
        days: int | None = None,
        project: str | None = None,
        limit: int = 20,
        exclude: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Top-N distinct ``call_name`` rows for a given call_type.

        Returns ``(call_name, call_count, session_count)`` sorted by
        call_count descending. Used for "top skills / CLIs / subagents"
        horizontal-bar charts.

        ``exclude`` is an optional list of ``call_name`` values to filter
        out before ranking — useful for CLI charts to hide noisy unix
        utilities like ``wc``/``head``/``grep`` that dominate counts
        without being useful signal.
        """
        ...

    def get_kg_er(
        self,
        *,
        resolution: float | None = None,
        top_n: int = 50,
        seed_metric: SeedMetric = "edge_betweenness",
        max_depth: int = 0,
        min_degree: int = 1,
        days: int | None = None,
        project: str | None = None,
    ) -> KGPayload:
        """Resolved-entity knowledge-graph payload for the cytoscape page.

        Returns the seed-and-expand subgraph of the canonical entity graph,
        optionally restricted to chunks within the last ``days`` days and/or
        belonging to ``project``. Filtering happens BEFORE seed-and-expand so
        the seeds and expansion run on the same subgraph the user sees.

        Raises ``KGDataMissing`` if the KG pipeline has not yet populated
        ``nodes`` / ``edges`` / ``leiden_communities``.
        """
        ...

    def get_kg_cache_stats(self) -> KGCacheStats:
        """Per-stage backlog snapshot of the cache → knowledge-graph pipeline.

        Global by design (not filtered by ``days`` / ``project``): the
        background indexer processes the entire projects tree, so a
        time-scoped backlog would misrepresent the remaining work. The
        ``indexer`` field is populated by the API route from the live
        ``IndexerService.status()``.
        """
        ...

    def search_events(
        self,
        query: str,
        *,
        days: int | None = None,
        project: str | None = None,
        msg_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Full-text search over event message content.

        Queries the ``events_fts`` FTS5 index and joins back to
        ``events`` to return project / session / timestamp context plus a
        relevance-ranked snippet. Returns an empty list for empty or
        whitespace-only queries.

        Results respect the global ``days`` and ``project`` filters — a
        project-scoped search looks at only that project's events, and a
        time-range limit caps how far back the match can come from.

        ``msg_kind`` optionally restricts results to a single derived
        message kind (``human``, ``assistant_text``, ``tool_use`` etc.).
        Applied server-side *before* ranking so the returned top-N is
        the actual top-N of that kind, not a post-filtered subset.
        """
        ...

    def semantic_search_events(
        self,
        query: str,
        *,
        days: int | None = None,
        project: str | None = None,
        msg_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Vector-similarity search over the HNSW chunk index.

        Embeds ``query`` server-side using the same GGUF model that built
        the index, then returns the nearest chunks ranked by cosine
        distance. Response shape matches ``search_events`` — same keys,
        with ``rank`` holding the distance (lower is closer, matching
        FTS5's BM25 convention where lower is more relevant).

        Results respect the ``days``/``project``/``msg_kind`` filters.
        Because the underlying index only embeds ``msg_kind='human'``
        events today, requesting any other ``msg_kind`` yields no hits.

        Returns an empty list for empty queries or when the embedding
        runtime isn't available (e.g. model not yet downloaded).
        """
        ...
