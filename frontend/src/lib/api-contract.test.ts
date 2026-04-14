/**
 * API Contract Tests
 *
 * Tests that the backend API responses match the TypeScript interfaces
 * the frontend depends on. Runs against a real server (not mocked).
 *
 * Both DuckDB and SQLite backends are tested by starting each on a
 * different port. The tests validate that required fields exist and
 * have the expected types — they don't compare exact values.
 *
 * Prerequisites:
 *   BACKEND_PORT=8101 uv run python -m claude_code_sessions.main --backend duckdb &
 *   BACKEND_PORT=8102 uv run python -m claude_code_sessions.main --backend sqlite &
 *
 * Or run via: npm run test:contract
 *
 * @vitest-environment node
 */
import { describe, it, expect, beforeAll } from 'vitest'

// DuckDB full-scans JSONL files per query — some queries are slow
const QUERY_TIMEOUT = 30_000

// Backend URLs — each backend runs on its own port
const DUCKDB_URL = process.env.DUCKDB_URL || 'http://localhost:8101'
const SQLITE_URL = process.env.SQLITE_URL || 'http://localhost:8102'

// Known project ID for filtering tests
const TEST_PROJECT = '-Users-joshpeak-play-claude-code-sessions'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fetchApi<T>(baseUrl: string, path: string): Promise<T> {
  const res = await fetch(`${baseUrl}/api${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`)
  return res.json() as Promise<T>
}

/** Assert every object in the array has the given keys with non-undefined values */
function assertHasFields(items: Record<string, unknown>[], fields: string[], label: string) {
  expect(items.length).toBeGreaterThan(0)
  const first = items[0]
  for (const field of fields) {
    expect(first, `${label}: missing field '${field}' in ${JSON.stringify(Object.keys(first))}`).toHaveProperty(field)
  }
}

/** Assert a field is a number (including 0) */
function assertNumeric(obj: Record<string, unknown>, field: string, label: string) {
  expect(typeof obj[field], `${label}.${field} should be number, got ${typeof obj[field]}`).toBe('number')
}

// ---------------------------------------------------------------------------
// Test each backend
// ---------------------------------------------------------------------------

const backends = [
  { name: 'duckdb', url: DUCKDB_URL },
  { name: 'sqlite', url: SQLITE_URL },
]

for (const backend of backends) {
  describe(`API Contract [${backend.name}]`, { timeout: QUERY_TIMEOUT }, () => {
    beforeAll(async () => {
      // Verify backend is running
      try {
        const res = await fetch(`${backend.url}/api/health`)
        if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
      } catch {
        throw new Error(
          `${backend.name} backend not running at ${backend.url}. ` +
          `Start with: BACKEND_PORT=${backend.url.split(':').pop()} ` +
          `uv run python -m claude_code_sessions.main --backend ${backend.name}`
        )
      }
    })

    // -- /api/summary -------------------------------------------------------

    describe('GET /api/summary', () => {
      it('returns array with grand_total_cost_usd', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/summary?days=30')
        expect(data).toBeInstanceOf(Array)
        expect(data.length).toBeGreaterThan(0)
        assertNumeric(data[0], 'grand_total_cost_usd', 'summary')
        assertNumeric(data[0], 'total_events', 'summary')
      })
    })

    // -- /api/usage/daily ---------------------------------------------------

    describe('GET /api/usage/daily', () => {
      it('matches UsageData interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/usage/daily?days=7')
        assertHasFields(data, [
          'project_id', 'model_id', 'time_bucket',
          'total_cost_usd', 'session_count', 'event_count',
          'total_input_tokens', 'total_output_tokens',
        ], 'daily')
        assertNumeric(data[0], 'total_cost_usd', 'daily')
        assertNumeric(data[0], 'total_input_tokens', 'daily')
        expect(typeof data[0].time_bucket).toBe('string')
      })

      it('respects project filter', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(
          backend.url, `/usage/daily?days=30&project=${TEST_PROJECT}`
        )
        for (const row of data) {
          expect(row.project_id).toBe(TEST_PROJECT)
        }
      })
    })

    // -- /api/usage/weekly --------------------------------------------------

    describe('GET /api/usage/weekly', () => {
      it('matches UsageData interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/usage/weekly?days=30')
        assertHasFields(data, [
          'project_id', 'model_id', 'time_bucket',
          'total_cost_usd', 'total_input_tokens', 'total_output_tokens',
        ], 'weekly')
      })
    })

    // -- /api/usage/monthly -------------------------------------------------

    describe('GET /api/usage/monthly', () => {
      it('matches UsageData interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/usage/monthly?days=90')
        assertHasFields(data, [
          'project_id', 'model_id', 'time_bucket',
          'total_cost_usd', 'total_input_tokens', 'total_output_tokens',
        ], 'monthly')
      })
    })

    // -- /api/usage/hourly --------------------------------------------------

    describe('GET /api/usage/hourly', () => {
      it('matches HourlyData interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/usage/hourly?days=7')
        assertHasFields(data, [
          'project_id', 'time_bucket', 'hour_of_day',
          'total_cost_usd', 'event_count',
        ], 'hourly')
        assertNumeric(data[0], 'hour_of_day', 'hourly')
      })
    })

    // -- /api/usage/top-projects-weekly -------------------------------------

    describe('GET /api/usage/top-projects-weekly', () => {
      it('matches TopProjectWeekly interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(
          backend.url, '/usage/top-projects-weekly'
        )
        assertHasFields(data, [
          'project_id', 'time_bucket', 'cost_usd',
          'event_count', 'session_count',
        ], 'top-projects-weekly')
        assertNumeric(data[0], 'cost_usd', 'top-projects-weekly')
      })
    })

    // -- /api/projects ------------------------------------------------------

    describe('GET /api/projects', () => {
      it('matches ProjectInfo interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/projects?days=30')
        assertHasFields(data, [
          'project_id', 'total_cost_usd', 'session_count', 'event_count',
        ], 'projects')
        assertNumeric(data[0], 'total_cost_usd', 'projects')
      })

      it('sorted by cost descending', async () => {
        const data = await fetchApi<Record<string, number>[]>(backend.url, '/projects?days=30')
        for (let i = 1; i < data.length; i++) {
          expect(data[i - 1].total_cost_usd).toBeGreaterThanOrEqual(data[i].total_cost_usd)
        }
      })
    })

    // -- /api/sessions ------------------------------------------------------

    describe('GET /api/sessions', () => {
      it('matches SessionListItem interface', async () => {
        const data = await fetchApi<Record<string, unknown>[]>(backend.url, '/sessions?days=30')
        assertHasFields(data, [
          'project_id', 'session_id',
          'first_timestamp', 'last_timestamp',
          'event_count', 'subagent_count',
          'total_input_tokens', 'total_output_tokens',
          'total_cost_usd',
        ], 'sessions')
      })
    })

    // -- /api/domains -------------------------------------------------------

    describe('GET /api/domains', () => {
      it('returns available, blocked, all arrays', async () => {
        const data = await fetchApi<Record<string, unknown>>(backend.url, '/domains')
        expect(data).toHaveProperty('available')
        expect(data).toHaveProperty('blocked')
        expect(data).toHaveProperty('all')
        expect(data.available).toBeInstanceOf(Array)
        expect(data.blocked).toBeInstanceOf(Array)
        expect(data.all).toBeInstanceOf(Array)
      })
    })

    // -- /api/health --------------------------------------------------------

    describe('GET /api/health', () => {
      it('returns status healthy', async () => {
        const data = await fetchApi<Record<string, unknown>>(backend.url, '/health')
        expect(data.status).toBe('healthy')
        expect(data).toHaveProperty('projects_path')
      })
    })
  })
}
