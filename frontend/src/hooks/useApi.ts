import { useState, useEffect } from 'react'

export function useApi<T>(endpoint: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(endpoint !== null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Skip fetch if endpoint is null (conditional fetching)
    if (endpoint === null) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }

    const fetchData = async () => {
      try {
        setLoading(true)
        const response = await fetch(`/api${endpoint}`)
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const result = await response.json()
        setData(result)
        setError(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'An error occurred')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [endpoint])

  return { data, loading, error }
}
