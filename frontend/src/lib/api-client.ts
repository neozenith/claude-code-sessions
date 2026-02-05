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
  async getSessions(params?: { days?: number; project?: string }): Promise<ApiResult<SessionListItem[]>> {
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
}

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
  // Token usage
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  // Source file info
  filepath: string
  line_number: number
  is_subagent_file: boolean
  // Raw message JSON for expandable view
  message_json: unknown
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
