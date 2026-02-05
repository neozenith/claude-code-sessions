/**
 * Unit tests for api-client.ts
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  ApiClient,
  fetchJson,
  createApiError,
  createNetworkError,
  isApiSuccess,
  isApiError,
  type ApiResult,
} from './api-client'

describe('api-client', () => {
  // Mock fetch globally
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('createApiError', () => {
    it('creates an error from a Response object', () => {
      const mockResponse = {
        status: 404,
        statusText: 'Not Found',
        url: 'http://example.com/api/test',
      } as Response

      const error = createApiError(mockResponse)

      expect(error.status).toBe(404)
      expect(error.statusText).toBe('Not Found')
      expect(error.url).toBe('http://example.com/api/test')
      expect(error.message).toBe('HTTP error 404: Not Found')
    })

    it('uses custom message when provided', () => {
      const mockResponse = {
        status: 500,
        statusText: 'Internal Server Error',
        url: 'http://example.com/api/test',
      } as Response

      const error = createApiError(mockResponse, 'Database connection failed')

      expect(error.message).toBe('Database connection failed')
    })
  })

  describe('createNetworkError', () => {
    it('creates an error from an Error object', () => {
      const originalError = new Error('Network timeout')
      const error = createNetworkError('http://example.com/api/test', originalError)

      expect(error.status).toBe(0)
      expect(error.statusText).toBe('Network Error')
      expect(error.message).toBe('Network timeout')
      expect(error.url).toBe('http://example.com/api/test')
    })

    it('handles non-Error objects', () => {
      const error = createNetworkError('http://example.com/api/test', 'some string error')

      expect(error.message).toBe('Network request failed')
    })
  })

  describe('isApiSuccess / isApiError', () => {
    it('correctly identifies success result', () => {
      const successResult: ApiResult<string> = { ok: true, data: 'test' }
      const errorResult: ApiResult<string> = {
        ok: false,
        error: { status: 500, statusText: 'Error', message: 'Test', url: '' },
      }

      expect(isApiSuccess(successResult)).toBe(true)
      expect(isApiSuccess(errorResult)).toBe(false)
      expect(isApiError(successResult)).toBe(false)
      expect(isApiError(errorResult)).toBe(true)
    })
  })

  describe('fetchJson', () => {
    it('returns success result for valid JSON response', async () => {
      const mockData = { id: 1, name: 'test' }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockData,
      })

      const result = await fetchJson<typeof mockData>('http://example.com/api/test')

      expect(result.ok).toBe(true)
      if (result.ok) {
        expect(result.data).toEqual(mockData)
      }

      expect(mockFetch).toHaveBeenCalledWith('http://example.com/api/test', {
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
      })
    })

    it('returns error result for non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        url: 'http://example.com/api/test',
        json: async () => ({ detail: 'Resource not found' }),
      })

      const result = await fetchJson('http://example.com/api/test')

      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.error.status).toBe(404)
        expect(result.error.message).toBe('Resource not found')
      }
    })

    it('handles non-JSON error bodies gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        url: 'http://example.com/api/test',
        json: async () => {
          throw new Error('Invalid JSON')
        },
      })

      const result = await fetchJson('http://example.com/api/test')

      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.error.status).toBe(500)
        expect(result.error.message).toBe('HTTP error 500: Internal Server Error')
      }
    })

    it('returns network error for fetch failures', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'))

      const result = await fetchJson('http://example.com/api/test')

      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.error.status).toBe(0)
        expect(result.error.statusText).toBe('Network Error')
        expect(result.error.message).toBe('Failed to fetch')
      }
    })
  })

  describe('ApiClient', () => {
    let client: ApiClient

    beforeEach(() => {
      client = new ApiClient({ baseUrl: '/api' })
    })

    describe('buildUrl', () => {
      it('builds URL without params', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        })

        await client.get('/health')

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/health',
          expect.any(Object)
        )
      })

      it('builds URL with params', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.get('/usage/daily', { days: 30, project: 'test-project' })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/usage/daily?days=30&project=test-project',
          expect.any(Object)
        )
      })

      it('filters out undefined and empty params', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.get('/usage/daily', { days: 30, project: undefined, model: '' })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/usage/daily?days=30',
          expect.any(Object)
        )
      })
    })

    describe('typed endpoint methods', () => {
      it('health() calls correct endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        })

        const result = await client.health()

        expect(mockFetch).toHaveBeenCalledWith('/api/health', expect.any(Object))
        expect(result.ok).toBe(true)
      })

      it('getSummary() calls correct endpoint with params', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [{ total_cost_usd: 100 }],
        })

        await client.getSummary({ days: 30 })

        expect(mockFetch).toHaveBeenCalledWith('/api/summary?days=30', expect.any(Object))
      })

      it('getDailyUsage() calls correct endpoint', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.getDailyUsage({ days: 7, project: 'my-project' })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/usage/daily?days=7&project=my-project',
          expect.any(Object)
        )
      })

      it('getTimelineEvents() encodes project ID', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.getTimelineEvents('project/with/slashes', { days: 7 })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/timeline/events/project%2Fwith%2Fslashes?days=7',
          expect.any(Object)
        )
      })

      it('getSessions() calls correct endpoint with filters', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [
            {
              project_id: 'test-project',
              session_id: 'session-123',
              first_timestamp: '2026-02-05T01:00:00Z',
              last_timestamp: '2026-02-05T02:00:00Z',
              event_count: 100,
              subagent_count: 2,
              total_input_tokens: 5000,
              total_output_tokens: 3000,
              total_cost_usd: 0.50,
              filepath: '/path/to/session.jsonl',
            },
          ],
        })

        const result = await client.getSessions({ days: 30, project: 'test-project' })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/sessions?days=30&project=test-project',
          expect.any(Object)
        )
        expect(result.ok).toBe(true)
        if (result.ok) {
          expect(result.data).toHaveLength(1)
          expect(result.data[0].session_id).toBe('session-123')
          expect(result.data[0].event_count).toBe(100)
        }
      })

      it('getSessions() works without filters', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.getSessions()

        expect(mockFetch).toHaveBeenCalledWith('/api/sessions', expect.any(Object))
      })

      it('getSessionEvents() encodes project and session IDs', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [
            {
              uuid: 'event-uuid-123',
              parent_uuid: null,
              event_type: 'user',
              timestamp: '2026-02-05T01:00:00Z',
              timestamp_local: '2026-02-05T12:00:00+11:00',
              session_id: 'session-123',
              is_sidechain: false,
              agent_slug: null,
              message_role: 'user',
              message_content: 'Hello',
              model_id: null,
              input_tokens: 0,
              output_tokens: 0,
              cache_read_tokens: 0,
              cache_creation_tokens: 0,
              filepath: '/path/to/session.jsonl',
              line_number: 1,
              is_subagent_file: false,
              message_json: { role: 'user', content: 'Hello' },
            },
          ],
        })

        const result = await client.getSessionEvents('project/with/slashes', 'session-id-123')

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/sessions/project%2Fwith%2Fslashes/session-id-123',
          expect.any(Object)
        )
        expect(result.ok).toBe(true)
        if (result.ok) {
          expect(result.data).toHaveLength(1)
          expect(result.data[0].uuid).toBe('event-uuid-123')
          expect(result.data[0].event_type).toBe('user')
          expect(result.data[0].message_content).toBe('Hello')
        }
      })

      it('getSessionEvents() accepts event_uuid filter parameter', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        })

        await client.getSessionEvents('test-project', 'session-123', {
          event_uuid: 'filter-uuid-456',
        })

        expect(mockFetch).toHaveBeenCalledWith(
          '/api/sessions/test-project/session-123?event_uuid=filter-uuid-456',
          expect.any(Object)
        )
      })

      it('getSessionEvents() returns full event structure', async () => {
        const mockEvent = {
          uuid: 'assistant-uuid',
          parent_uuid: 'user-uuid',
          event_type: 'assistant',
          timestamp: '2026-02-05T01:01:00Z',
          timestamp_local: '2026-02-05T12:01:00+11:00',
          session_id: 'session-123',
          is_sidechain: false,
          agent_slug: null,
          message_role: 'assistant',
          message_content: [
            { type: 'thinking', thinking: 'Let me analyze...' },
            { type: 'text', text: 'Here is my response' },
            { type: 'tool_use', name: 'read_file', input: { path: '/test.txt' } },
          ],
          model_id: 'claude-sonnet-4-5',
          input_tokens: 1000,
          output_tokens: 500,
          cache_read_tokens: 200,
          cache_creation_tokens: 50,
          filepath: '/path/to/session.jsonl',
          line_number: 2,
          is_subagent_file: false,
          // message_json contains full raw event, not just the message field
          message_json: {
            type: 'assistant',
            uuid: 'assistant-uuid',
            parentUuid: 'user-uuid',
            message: { role: 'assistant', content: [], model: 'claude-sonnet-4-5' },
          },
        }

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => [mockEvent],
        })

        const result = await client.getSessionEvents('test-project', 'session-123')

        expect(result.ok).toBe(true)
        if (result.ok) {
          const event = result.data[0]
          // Verify all required fields are present
          expect(event.uuid).toBe('assistant-uuid')
          expect(event.parent_uuid).toBe('user-uuid')
          expect(event.event_type).toBe('assistant')
          expect(event.model_id).toBe('claude-sonnet-4-5')
          expect(event.input_tokens).toBe(1000)
          expect(event.output_tokens).toBe(500)
          expect(event.cache_read_tokens).toBe(200)
          expect(event.filepath).toBe('/path/to/session.jsonl')
          expect(event.line_number).toBe(2)
          expect(event.is_subagent_file).toBe(false)
          // Verify message_content array structure
          expect(Array.isArray(event.message_content)).toBe(true)
          if (Array.isArray(event.message_content)) {
            expect(event.message_content).toHaveLength(3)
            expect(event.message_content[0].type).toBe('thinking')
            expect(event.message_content[1].type).toBe('text')
            expect(event.message_content[2].type).toBe('tool_use')
          }
        }
      })
    })

    describe('post()', () => {
      it('sends POST request with JSON body', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({ id: 1 }),
        })

        await client.post('/some-endpoint', { name: 'test', value: 123 })

        expect(mockFetch).toHaveBeenCalledWith('/api/some-endpoint', {
          method: 'POST',
          body: '{"name":"test","value":123}',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
        })
      })
    })
  })
})
