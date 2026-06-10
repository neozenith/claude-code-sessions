/**
 * API Client for Claude Code Sessions backend
 *
 * Provides a type-safe, testable interface for making API requests.
 * All endpoints are prefixed with /api automatically.
 */

/** Configuration options for the API client */
export interface ApiClientConfig {
  /** Base URL for API requests (default: '/api') */
  baseUrl?: string
  /** Default timeout in milliseconds (default: 30000) */
  timeout?: number
}

/** Standard API error response */
export interface ApiError {
  status: number
  statusText: string
  message: string
  url: string
}

/** Result type for API operations - either success with data or failure with error */
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError }

/** The three lenses of a summary (G7). */
export interface SummaryLenses {
  task_summary: string
  patterns: string
  decisions_values: string
}

/** Discriminated summary payload — never a fabricated summary (G7, ADR7.1). */
export type SummaryResponse =
  | {
      status: 'summarised'
      lenses: SummaryLenses
      scope_path?: string
      scope_depth?: number
      strategy?: string
      model?: string
      child_count?: number
    }
  | { status: 'not_summarised' }

/** A (strategy, model) variant present in the roll-up table (eval picker). */
export interface SummaryVariant {
  strategy: string
  model: string
}

/** An immediate child scope in the trie. */
export interface ScopeChild {
  scope_path: string
  scope_depth: number
}

/** A project's resolved scope_path + root-first ancestor chain (G1). */
export interface ProjectScope {
  scope_path: string | null
  ancestor_scopes: string[]
}

// =========================================================================
// CR5 — Extractive set-union "Claims Explorer" types
// =========================================================================

/** A single extractive claim with its provenance (CR5).
 *
 * `count` is the number of source sessions the claim was extracted from
 * (its support); `sessions` are those session ids. Lenses rank claims by
 * `count` descending. */
export interface Claim {
  claim: string
  count: number
  sessions: string[]
}

/** A node in a lens's coarse→fine→leaf cluster tree (CR6 EVoC clustering).
 *
 * A node carries EITHER `children` (a coarse cluster, whose children are finer
 * clusters) OR `members` (a fine / single-level cluster, whose members are the
 * verbatim leaf claims) — never both. `name` is the LLM "common-thread" label;
 * `count` is the distinct-session salience (union over descendants). */
export interface ClusterNode {
  cluster_id: number
  layer: number
  name: string
  count: number
  sessions: string[]
  children?: ClusterNode[]
  members?: Claim[]
}

/** The claim lenses for a scope (CR6): each lens is a tree of named EVoC clusters
 * (tasks, patterns, decisions_values, and learnings). */
export interface ClaimLenses {
  tasks: ClusterNode[]
  patterns: ClusterNode[]
  decisions_values: ClusterNode[]
  learnings: ClusterNode[]
}

/** A roll-up of claims for a scope at a grain+bucket (GET /api/claims/scope).
 *
 * Discriminated on `status`: `not_summarised` carries no lenses/provenance,
 * so the explorer renders an empty state. */
export type ClaimRollup =
  | {
      status: 'summarised'
      scope_path: string
      grain: string
      bucket: string
      model: string
      lenses: ClaimLenses
      failure_count: number
      failed_sessions: string[]
      /** session_id → project_id, for building working SessionDetail back-links
       * (provenance session_ids alone can't address /sessions/:projectId/:sessionId). */
      session_projects: Record<string, string>
    }
  | { status: 'not_summarised' }

/** One bucket option for a scope/grain (GET /api/claims/buckets). */
export interface ClaimBucket {
  bucket: string
  n_claims: number
  total_count: number
}

/** One of a session's raw extracted claims, tagged with the fine cluster it belongs
 * to (CR6). `cluster_name`/`cluster_id` are null until the taxonomy is built. */
export interface SessionClaim {
  claim: string
  cluster_id: number | null
  cluster_name: string | null
}

/** A session's extracted claims under a model (GET /api/claims/session/...).
 *
 * The session lenses are the raw extracted claims (no counts — counts only exist
 * after the cluster roll-up), each carrying its cluster attribution. `failure` is
 * null on success or carries the extraction failure reason + raw excerpt. */
export interface SessionClaims {
  project_id: string
  session_id: string
  model: string
  lenses: {
    tasks: SessionClaim[]
    patterns: SessionClaim[]
    decisions_values: SessionClaim[]
    learnings: SessionClaim[]
  }
  failure: { reason: string; raw_excerpt: string } | null
}

/** One roll-up a session is a member of (GET /api/claims/session/.../memberships). */
export interface RollupMembership {
  scope_path: string
  scope_depth: number
  grain: string
  bucket: string
  n_claims: number
}

/** Per-project claim-extraction coverage row (GET /api/claims/coverage). */
export interface CoverageProject {
  project_id: string
  scope_path: string | null
  domain: string
  total: number
  summarised: number
  failed: number
  pending: number
  pct_complete: number
}

/** Claim-extraction coverage across all projects (GET /api/claims/coverage). */
export interface Coverage {
  model: string
  overall: {
    total: number
    summarised: number
    failed: number
    pending: number
    pct_complete: number
  }
  projects: CoverageProject[]
}

/** One model row from GET /api/claims/models/detail.
 *
 * Lists ALL panel models, not just those with extracted claims —
 * `has_claims:false` rows are still selectable (the explorer shows the
 * not_summarised empty state when a no-data model is picked). */
export interface ClaimModelDetail {
  model: string
  has_claims: boolean
}

/** One cell of the coverage pivot (GET /api/claims/coverage-pivot).
 *
 * A (scope_path × bucket) intersection with its session/claim/failure counts
 * and a tri-state `status` rolling those up to done / failed / pending. */
export interface CoverageCell {
  scope_path: string
  bucket: string
  sessions: number
  claims: number
  failures: number
  status: 'done' | 'failed' | 'pending'
}

/** The done-vs-pending coverage pivot for a model+grain (GET /api/claims/coverage-pivot).
 *
 * `scopes` (y-axis) and `buckets` (x-axis) are the axis label arrays; `cells`
 * is the sparse list of intersections. Consumers densify into a z-matrix. */
export interface CoveragePivot {
  model: string
  grain: string
  scopes: string[]
  buckets: string[]
  cells: CoverageCell[]
}

/** One systematic failure mode rolled up from the parallel failure stream
 * (GET /api/claims/failures) — counts + a representative sample for triage (CR5). */
export interface FailureCategory {
  category: string
  count: number
  pct: number
  sample_reason: string
  sample_excerpt_tail: string
  sample_sessions: { project_id: string; session_id: string }[]
}

/** The categorised failure-mode roll-up for a model/scope/days slice (CR5 distillation). */
export interface FailureAnalysis {
  model: string | null
  total: number
  categories: FailureCategory[]
  by_model: Record<string, number>
}

/** Reindex worker state (POST /api/claims/reindex, GET /api/claims/reindex/status).
 *
 * A single-flight extractive reindex over one scope slice. `state` drives the
 * polling loop: the client polls /status while `running`, stops on
 * `done`/`error`/`idle`. */
export interface ReindexStatus {
  state: 'idle' | 'running' | 'done' | 'error'
  scope_path: string
  grain: string
  model: string
  sessions_total: number
  sessions_done: number
  failures: number
  rollups_written: number
  message: string
  error: string | null
}

/** POST /api/claims/reindex response — the accepted/rejected start signal.
 *
 * `already_running` is true when a reindex was in flight and this request was
 * a no-op (single-flight). Carries the same status fields so the caller can
 * seed its polling loop immediately. */
export interface ReindexStart {
  state: ReindexStatus['state']
  already_running: boolean
  scope_path?: string
  grain?: string
  model?: string
  sessions_total?: number
  sessions_done?: number
  failures?: number
  rollups_written?: number
  message?: string
  error?: string | null
}

/**
 * Creates an ApiError from a failed Response
 */
export function createApiError(response: Response, message?: string): ApiError {
  return {
    status: response.status,
    statusText: response.statusText,
    message: message || `HTTP error ${response.status}: ${response.statusText}`,
    url: response.url,
  }
}

/**
 * Creates an ApiError from a network or other error
 */
export function createNetworkError(url: string, error: unknown): ApiError {
  const message = error instanceof Error ? error.message : 'Network request failed'
  return {
    status: 0,
    statusText: 'Network Error',
    message,
    url,
  }
}

/**
 * Type guard to check if an ApiResult is successful
 */
export function isApiSuccess<T>(result: ApiResult<T>): result is { ok: true; data: T } {
  return result.ok === true
}

/**
 * Type guard to check if an ApiResult is an error
 */
export function isApiError<T>(result: ApiResult<T>): result is { ok: false; error: ApiError } {
  return result.ok === false
}

/**
 * Low-level fetch wrapper with proper error handling
 *
 * @param url - Full URL to fetch
 * @param options - Fetch options (method, headers, body, etc.)
 * @returns ApiResult with typed data or error
 */
export async function fetchJson<T>(
  url: string,
  options: RequestInit = {}
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...options.headers,
      },
      ...options,
    })

    if (!response.ok) {
      // Try to parse error body for more details
      let message: string | undefined
      try {
        const errorBody = await response.json()
        message = errorBody.detail || errorBody.message || errorBody.error
      } catch {
        // Body wasn't JSON, use default message
      }
      return { ok: false, error: createApiError(response, message) }
    }

    const data = await response.json()
    return { ok: true, data: data as T }
  } catch (error) {
    return { ok: false, error: createNetworkError(url, error) }
  }
}

/**
 * API Client class for Claude Code Sessions backend
 *
 * Provides typed methods for all API endpoints with proper error handling.
 */
export class ApiClient {
  private baseUrl: string

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.baseUrl ?? '/api'
  }

  /**
   * Build the full URL for an endpoint
   */
  private buildUrl(endpoint: string, params?: Record<string, string | number | undefined>): string {
    const url = `${this.baseUrl}${endpoint}`
    if (!params) return url

    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.set(key, String(value))
      }
    })

    const queryString = searchParams.toString()
    return queryString ? `${url}?${queryString}` : url
  }

  /**
   * GET request to an endpoint
   */
  async get<T>(endpoint: string, params?: Record<string, string | number | undefined>): Promise<ApiResult<T>> {
    const url = this.buildUrl(endpoint, params)
    return fetchJson<T>(url, { method: 'GET' })
  }

  /**
   * POST request to an endpoint
   */
  async post<T, B = unknown>(endpoint: string, body?: B): Promise<ApiResult<T>> {
    const url = this.buildUrl(endpoint)
    return fetchJson<T>(url, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  // =========================================================================
  // Typed endpoint methods
  // =========================================================================

  /** Health check endpoint */
  async health(): Promise<ApiResult<{ status: string }>> {
    return this.get('/health')
  }

  /** Get usage summary */
  async getSummary(params?: { days?: number; project?: string }): Promise<ApiResult<SummaryData[]>> {
    return this.get('/summary', params)
  }

  /** Get daily usage data */
  async getDailyUsage(params?: { days?: number; project?: string }): Promise<ApiResult<UsageData[]>> {
    return this.get('/usage/daily', params)
  }

  /** Get weekly usage data */
  async getWeeklyUsage(params?: { days?: number; project?: string }): Promise<ApiResult<UsageData[]>> {
    return this.get('/usage/weekly', params)
  }

  /** Get monthly usage data */
  async getMonthlyUsage(params?: { days?: number; project?: string }): Promise<ApiResult<UsageData[]>> {
    return this.get('/usage/monthly', params)
  }

  /** Get hourly usage data */
  async getHourlyUsage(params?: { days?: number; project?: string }): Promise<ApiResult<HourlyData[]>> {
    return this.get('/usage/hourly', params)
  }

  /** Get top projects weekly data */
  async getTopProjectsWeekly(params?: { days?: number }): Promise<ApiResult<TopProjectWeekly[]>> {
    return this.get('/usage/top-projects-weekly', params)
  }

  /** Get projects list */
  async getProjects(): Promise<ApiResult<ProjectInfo[]>> {
    return this.get('/projects')
  }

  /** Get timeline events for a project */
  async getTimelineEvents(projectId: string, params?: { days?: number }): Promise<ApiResult<TimelineEvent[]>> {
    return this.get(`/timeline/events/${encodeURIComponent(projectId)}`, params)
  }

  /** Get schema timeline data */
  async getSchemaTimeline(params?: { days?: number }): Promise<ApiResult<SchemaEvent[]>> {
    return this.get('/schema-timeline', params)
  }

  /** Get sessions list */
  async getSessions(params?: {
    days?: number
    project?: string
    sort_by?: 'last_active' | 'events' | 'subagents' | 'cost'
    sort_order?: 'asc' | 'desc'
  }): Promise<ApiResult<SessionListItem[]>> {
    return this.get('/sessions', params)
  }

  /** Get session events for a specific session */
  async getSessionEvents(
    projectId: string,
    sessionId: string,
    params?: { event_uuid?: string }
  ): Promise<ApiResult<SessionEvent[]>> {
    return this.get(
      `/sessions/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}`,
      params
    )
  }

  /** Per-model TPS rows + context-ratio histogram, scoped by days/project. */
  async getPerformanceSummary(params?: {
    days?: number
    project?: string
  }): Promise<ApiResult<PerformanceSummary>> {
    return this.get('/performance', params)
  }

  /** Immediate child scopes of a scope_path (next trie level) — the explorer
   * breadcrumb drill-down (CR5; consolidated under /claims with the /summaries page). */
  async listScopeChildren(params: {
    path: string
    days?: number
    project?: string
  }): Promise<ApiResult<ScopeChild[]>> {
    return this.get('/claims/scope/children', params)
  }

  /** The 3-lens abstractive summary for a session under a model (retained for the
   * SessionDetail comparison card; the abstractive scope explorer was retired). */
  async getSessionSummary(
    projectId: string,
    sessionId: string,
    params: { model: string },
  ): Promise<ApiResult<SummaryResponse>> {
    return this.get(
      `/summaries/session/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}`,
      params,
    )
  }

  /** Distinct (strategy, model) variants present in the roll-up table (G7). */
  async listSummaryVariants(): Promise<ApiResult<SummaryVariant[]>> {
    return this.get('/summaries/variants')
  }

  /** A project's resolved scope_path + ancestor chain — hard-pins the explorer scope
   * to the global Project filter, and drives the SessionDetail lineage breadcrumb. */
  async getProjectScope(projectId: string): Promise<ApiResult<ProjectScope>> {
    return this.get('/claims/scope/of-project', { project_id: projectId })
  }

  /** Per-turn idle/active/tps/too_fast + a session summary. */
  async getSessionMetrics(
    projectId: string,
    sessionId: string,
  ): Promise<ApiResult<SessionMetrics>> {
    return this.get(
      `/sessions/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}/metrics`,
    )
  }

  /** On-demand raw JSONL line for a single event (not stored in cache). */
  async getEventRawJson(
    projectId: string,
    sessionId: string,
    eventUuid: string,
  ): Promise<ApiResult<EventRawJson>> {
    return this.get(
      `/sessions/${encodeURIComponent(projectId)}` +
        `/${encodeURIComponent(sessionId)}` +
        `/events/${encodeURIComponent(eventUuid)}/raw`,
    )
  }

  /** Call counts bucketed by time and call_type for stacked time-series charts. */
  async getCallsTimeline(params: {
    granularity: 'daily' | 'weekly' | 'monthly' | 'hourly'
    days?: number
    project?: string
  }): Promise<ApiResult<CallsTimelineRow[]>> {
    return this.get('/calls/timeline', params)
  }

  /** Top-N distinct call_name rows for a given call_type.
   *
   * `exclude` accepts an array and is joined with commas for the query
   * string — useful for filtering noisy unix utilities out of the CLI chart.
   */
  async getTopCalls(params: {
    call_type: CallType
    days?: number
    project?: string
    limit?: number
    exclude?: string[]
  }): Promise<ApiResult<TopCallRow[]>> {
    const { exclude, ...rest } = params
    const query: Record<string, string | number | undefined> = { ...rest }
    if (exclude && exclude.length > 0) {
      query.exclude = exclude.join(',')
    }
    return this.get('/calls/top', query)
  }

  /** Search event content.
   *
   * Two ranking modes, dispatched on ``mode``:
   * - ``'keyword'`` (default): FTS5 BM25 over events_fts. Snippet
   *   includes `<mark>…</mark>` highlights; rank is BM25 score.
   * - ``'semantic'``: HNSW vector KNN against chunks_vec. Server embeds
   *   the query via the GGUF model, so the client never sees vectors.
   *   Snippet is the verbatim chunk text; rank is cosine distance.
   *
   * Both modes share the same response shape. Empty / whitespace-only
   * queries return [] (backend short-circuits).
   *
   * ``msg_kind`` is applied server-side before LIMIT (keyword) or
   * before the KNN fetch's candidate cap (semantic).
   */
  async searchEvents(params: {
    q: string
    days?: number
    project?: string
    msg_kind?: MessageKind
    limit?: number
    mode?: SearchMode
  }): Promise<ApiResult<SearchResultRow[]>> {
    return this.get('/search', params)
  }

  /** Per-stage backlog of the cache → knowledge-graph pipeline.
   *
   * Global by design — the response is NOT scoped to the dashboard's
   * days/project filters, because the indexer processes the whole
   * projects tree. The `indexer` field carries the live background-indexer
   * status (phase / error), so a crashed pipeline surfaces here.
   */
  async getKgCacheStats(): Promise<ApiResult<KGCacheStats>> {
    return this.get('/kg/cache-stats')
  }

  // =========================================================================
  // CR5 — Claims Explorer endpoints
  // =========================================================================

  /** Distinct models present in the extractive claims table (CR5). */
  async listClaimModels(): Promise<ApiResult<string[]>> {
    return this.get('/claims/models')
  }

  /** Bucket options for a scope at a grain, within the last-N-`days` window (CR5). */
  async getClaimBuckets(params: {
    path: string
    grain?: string
    model?: string
    days?: number
  }): Promise<ApiResult<ClaimBucket[]>> {
    return this.get('/claims/buckets', params)
  }

  /** The set-union claim roll-up for a scope at a grain (CR5). Empty `bucket` =
   * all claims unioned across the last-N-`days` window; a set `bucket` drills down. */
  async getClaimRollup(params: {
    path: string
    grain?: string
    bucket?: string
    model?: string
    days?: number
  }): Promise<ApiResult<ClaimRollup>> {
    return this.get('/claims/scope', params)
  }

  /** A single session's extracted claims under a model (CR5). */
  async getSessionClaims(
    projectId: string,
    sessionId: string,
    params: { model?: string },
  ): Promise<ApiResult<SessionClaims>> {
    return this.get(
      `/claims/session/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}`,
      params,
    )
  }

  /** The roll-ups a session is a member of, for the SessionDetail back-link (CR5). */
  async getSessionMemberships(
    projectId: string,
    sessionId: string,
    params: { model?: string },
  ): Promise<ApiResult<RollupMembership[]>> {
    return this.get(
      `/claims/session/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}/memberships`,
      params,
    )
  }

  /** Claim-extraction coverage (overall + per-project) for a model, scoped + windowed
   * to the last N `days` (CR5). */
  async getClaimsCoverage(params?: {
    model?: string
    scope?: string
    days?: number
  }): Promise<ApiResult<Coverage>> {
    return this.get('/claims/coverage', params)
  }

  /** All panel models with a `has_claims` flag (CR5). Unlike `listClaimModels`,
   * this includes models that have no extracted claims yet, so the selector can
   * label and still offer them. */
  async listClaimModelsDetail(): Promise<ApiResult<ClaimModelDetail[]>> {
    return this.get('/claims/models/detail')
  }

  /** The done-vs-pending coverage pivot (scopes × buckets) for a model+grain,
   * restricted to the subtree of `scope` and the last-N-`days` columns (CR5). */
  async getClaimsCoveragePivot(params: {
    model?: string
    grain?: string
    scope?: string
    days?: number
  }): Promise<ApiResult<CoveragePivot>> {
    return this.get('/claims/coverage-pivot', params)
  }

  /** Categorised failure-mode roll-up of the parallel failure stream, filtered by
   * model/scope/days — the failure-distillation panel (CR5). */
  async getClaimFailures(params?: {
    model?: string
    scope?: string
    days?: number
  }): Promise<ApiResult<FailureAnalysis>> {
    return this.get('/claims/failures', params)
  }

  /** Kick off an extractive reindex of one scope slice (single-flight) (CR5). */
  async startClaimsReindex(params: {
    path: string
    grain: string
    model: string
    limit?: number
  }): Promise<ApiResult<ReindexStart>> {
    const query: Record<string, string | number | undefined> = {
      path: params.path,
      grain: params.grain,
      model: params.model,
      limit: params.limit ?? 25,
    }
    return this.post(`/claims/reindex${this.queryString(query)}`)
  }

  /** Live status of the reindex worker, for the polling loop (CR5). */
  async getClaimsReindexStatus(): Promise<ApiResult<ReindexStatus>> {
    return this.get('/claims/reindex/status')
  }

  /** Encode a query object as a leading-`?` string (reused by POST endpoints
   * that carry their params in the query string, not the body). */
  private queryString(params: Record<string, string | number | undefined>): string {
    const search = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        search.set(key, String(value))
      }
    })
    const qs = search.toString()
    return qs ? `?${qs}` : ''
  }
}

/** Background-indexer phase — mirrors the PHASE_* constants in indexer.py. */
export type IndexerPhase = 'idle' | 'running' | 'completed' | 'cancelled' | 'failed'

/** Live status of the background indexer thread (from /api/health and
 * /api/kg/cache-stats). When `phase` is `failed`, `error` holds the
 * exception string that stopped the pipeline. */
export interface IndexerStatus {
  phase: IndexerPhase
  started_at: string | null
  finished_at: string | null
  error: string | null
}

/** One stage of the cache → KG pipeline (GET /api/kg/cache-stats).
 *
 * `eligible` is the upstream work available to this stage, `done` is how
 * much has been processed, `pending` is the backlog. `note` flags stages
 * that rebuild wholesale rather than tracking a true per-row backlog. */
export interface PipelineStage {
  key: string
  label: string
  eligible: number
  done: number
  pending: number
  percent: number
  note: string | null
}

/** Response from GET /api/kg/cache-stats — pipeline progress snapshot. */
export interface KGCacheStats {
  generated_at: string
  indexer: IndexerStatus
  files_on_disk: number
  source_files: number
  events_total: number
  chunks_total: number
  entities_total: number
  relations_total: number
  unique_entities: number
  nodes_total: number
  edges_total: number
  /** Communities at a single Leiden resolution (`display_resolution`), NOT
   * summed across resolutions — summing multi-counts the same nodes. */
  communities_total: number
  display_resolution: number | null
  stages: PipelineStage[]
}

/** Response shape from GET /api/sessions/{p}/{s}/events/{uuid}/raw */
export interface EventRawJson {
  event_uuid: string
  raw_json: string | null
  found: boolean
}

/** Discriminator on the event_calls fact table. */
export type CallType =
  | 'tool'
  | 'skill'
  | 'subagent'
  | 'cli'
  | 'rule'
  | 'make_target'
  | 'uv_script'
  | 'bun_script'

/** Row returned by GET /api/calls/timeline — one per (time_bucket, call_type). */
export interface CallsTimelineRow {
  time_bucket: string
  call_type: CallType
  call_count: number
}

/** Row returned by GET /api/calls/top — one per distinct call_name. */
export interface TopCallRow {
  call_name: string
  call_count: number
  session_count: number
}

/** Ranking mode for `/api/search`. Default is keyword (FTS5 BM25). */
export type SearchMode = 'keyword' | 'semantic'

/** Row returned by GET /api/search — one per matching event.
 *
 * ``snippet`` contains ``<mark>…</mark>`` tags around each matched token;
 * consumers render it via ``dangerouslySetInnerHTML`` on sanitized content
 * (the backend never embeds raw user message text — snippet is already
 * escaped by FTS5's snippet() function).
 *
 * ``rank`` is the BM25 score; lower means more relevant. Results are
 * pre-sorted by rank ascending.
 */
export interface SearchResultRow {
  project_id: string
  session_id: string
  uuid: string | null
  event_type: string
  message_kind: MessageKind | null
  timestamp: string | null
  timestamp_local: string | null
  model_id: string | null
  snippet: string
  rank: number
}

// =========================================================================
// Shared API Response Types
// =========================================================================

/** Summary data from /api/summary */
export interface SummaryData {
  summary_level: string
  total_projects: number
  total_events: number
  total_input_tokens: number
  total_output_tokens: number
  grand_total_cost_usd: number
}

/** Common usage data shape for daily/weekly/monthly endpoints */
export interface UsageData {
  project_id: string
  model_id: string
  time_bucket: string
  total_cost_usd: number
  session_count: number
  event_count: number
  total_input_tokens: number
  total_output_tokens: number
}

/** Hourly usage data from /api/usage/hourly */
export interface HourlyData {
  project_id: string
  time_bucket: string
  hour_of_day: number
  total_cost_usd: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  session_count: number
  event_count: number
}

/** Top projects weekly data */
export interface TopProjectWeekly {
  project_id: string
  time_bucket: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  session_count: number
  event_count: number
  cost_per_session: number
}

/** Project info from /api/projects */
export interface ProjectInfo {
  project_id: string
  total_cost_usd: number
  session_count: number
  event_count: number
  total_tokens: number
}

/** Timeline event data */
export interface TimelineEvent {
  project_id: string
  session_id: string
  event_seq: number
  model_id: string
  event_type: string
  message_content: string
  timestamp_utc: string
  timestamp_local: string
  first_event_time: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  cache_5m_tokens: number
  total_tokens: number
  cumulative_output_tokens: number
}

/** Schema event data */
export interface SchemaEvent {
  event_date: string
  version: string | null
  json_path: string
  first_seen: string
  has_record_timestamp: boolean
  event_count: number
}

/** Session list item from /api/sessions */
export interface SessionListItem {
  project_id: string
  session_id: string
  first_timestamp: string
  last_timestamp: string
  event_count: number
  subagent_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
  filepath: string
  /** Counts of rows in the event_calls fact table that belong to this
   * session, per call_type. Used to render call-density ratios on the
   * ProjectSessions page (calls / events). Zero if no calls recorded. */
  tool_call_count: number
  skill_call_count: number
  make_target_call_count: number
  /** Most frequently invoked skill in this session. Ties broken
   * alphabetically. ``null`` if the session made no skill calls. */
  top_skill: string | null
}

/** The 9 fine-grained message kinds derived from event_type + is_meta + content shape */
export type BaseMessageKind =
  | 'human'              // user, not meta, string content — actual typed prompts
  | 'task_notification'  // user, not meta, string starting with <task-notification>
  | 'tool_result'        // user, not meta, tool_result list
  | 'user_text'          // user, not meta, text/other list
  | 'meta'               // user, isMeta=true — system-injected context
  | 'assistant_text'     // assistant, text list
  | 'thinking'           // assistant, thinking list
  | 'tool_use'           // assistant, tool_use list
  | 'other'              // progress / system / queue-operation / etc.

/**
 * A message kind, possibly prefixed `subagent-` when the event belongs to a
 * subagent context (G3). The base kind is recovered by stripping the prefix.
 */
export type MessageKind = BaseMessageKind | `subagent-${BaseMessageKind}`

/** Session event from /api/sessions/{project_id}/{session_id} */
export interface SessionEvent {
  // Core identification
  uuid: string | null
  parent_uuid: string | null
  event_type: string
  // Timestamps
  timestamp: string | null
  timestamp_local: string | null
  // Session/agent identification
  session_id: string | null
  is_sidechain: boolean
  agent_slug: string | null
  // Message content - can be string or array of content items
  message_role: string | null
  message_content: string | MessageContentItem[] | null
  model_id: string | null
  is_meta: boolean
  message_kind: MessageKind
  // Token usage
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  // Response-level accounting + context occupancy (tokenometrics G1/G2/G4).
  // is_response_head marks the one event per requestId that carries the
  // deduped usage; context_ratio is the raw window-utilization fraction
  // (null when the model window is unknown); tps is the head's tokens/sec.
  is_response_head: number
  context_tokens: number
  context_window: number | null
  context_ratio: number | null
  response_duration_ms: number | null
  tps: number | null
  // Source file info
  filepath: string
  line_number: number
  is_subagent_file: boolean
  // Raw message JSON for expandable view
  message_json: unknown
}

/** One turn from /api/sessions/{p}/{s}/metrics — an assistant end-of-turn head. */
export interface SessionMetricsTurn {
  uuid: string | null
  timestamp: string | null
  output_tokens: number
  response_duration_ms: number | null
  tps: number | null
  active_ms: number | null
  idle_ms: number | null
  too_fast: boolean
}

/** Session summary folded over the turns. */
export interface SessionMetricsSummary {
  turn_count: number
  total_idle_ms: number
  total_active_ms: number
  avg_tps: number | null
  too_fast_count: number
}

export interface SessionMetrics {
  turns: SessionMetricsTurn[]
  summary: SessionMetricsSummary
}

/** Per-model performance row from /api/performance. */
export interface PerfModelRow {
  model_id: string
  response_count: number
  avg_tps: number | null
  median_tps: number | null
  total_idle_ms: number
  total_active_ms: number
}

/** One context-ratio histogram bin (raw utilization fraction, no zone label). */
export interface RatioBin {
  bin_lo: number
  bin_hi: number
  count: number
}

export interface PerformanceSummary {
  by_model: PerfModelRow[]
  ratio_histogram: RatioBin[]
}

/** Message content item (for assistant messages with typed content) */
export interface MessageContentItem {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result' | string
  text?: string
  thinking?: string
  name?: string
  input?: Record<string, unknown>
  id?: string
  content?: string | MessageContentItem[]
  tool_use_id?: string
  is_error?: boolean
}

// =========================================================================
// Default singleton instance
// =========================================================================

/** Default API client instance */
export const apiClient = new ApiClient()
