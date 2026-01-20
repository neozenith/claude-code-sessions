import { useSearchParams, useNavigate, useLocation } from 'react-router-dom'
import { useCallback, useMemo } from 'react'

export interface Filters {
  days: number | null
  project: string | null
}

const DEFAULT_DAYS = 30

// Time range options shared across all pages
export const TIME_RANGE_OPTIONS = [
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '14', label: 'Last 14 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 180 days' },
  { value: '0', label: 'All time' },
]

export function useFilters() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  // Parse current filters from URL
  const filters: Filters = useMemo(() => {
    const daysParam = searchParams.get('days')
    const projectParam = searchParams.get('project')

    return {
      days: daysParam !== null ? parseInt(daysParam, 10) : DEFAULT_DAYS,
      project: projectParam || null,
    }
  }, [searchParams])

  // Update filters in URL
  const setFilters = useCallback(
    (updates: Partial<Filters>) => {
      setSearchParams((prev) => {
        const newParams = new URLSearchParams(prev)

        if ('days' in updates) {
          if (updates.days === null || updates.days === DEFAULT_DAYS) {
            newParams.delete('days')
          } else {
            newParams.set('days', String(updates.days))
          }
        }

        if ('project' in updates) {
          if (!updates.project) {
            newParams.delete('project')
          } else {
            newParams.set('project', updates.project)
          }
        }

        return newParams
      })
    },
    [setSearchParams]
  )

  // Navigate to a different page while preserving filters
  const navigateWithFilters = useCallback(
    (path: string) => {
      const currentParams = new URLSearchParams(location.search)
      const paramString = currentParams.toString()
      navigate(paramString ? `${path}?${paramString}` : path)
    },
    [navigate, location.search]
  )

  // Get the current search string for use in links
  const filterSearchString = useMemo(() => {
    return location.search
  }, [location.search])

  // Build API query string from filters
  const buildApiQuery = useCallback(
    (additionalParams?: Record<string, string | number | null>) => {
      const params = new URLSearchParams()

      if (filters.days !== null && filters.days > 0) {
        params.set('days', String(filters.days))
      }

      if (filters.project) {
        params.set('project', filters.project)
      }

      if (additionalParams) {
        for (const [key, value] of Object.entries(additionalParams)) {
          if (value !== null && value !== undefined) {
            params.set(key, String(value))
          }
        }
      }

      const queryString = params.toString()
      return queryString ? `?${queryString}` : ''
    },
    [filters]
  )

  return {
    filters,
    setFilters,
    navigateWithFilters,
    filterSearchString,
    buildApiQuery,
  }
}
