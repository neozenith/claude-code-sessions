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
