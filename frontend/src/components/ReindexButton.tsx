import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { apiClient, isApiSuccess } from '@/lib/api-client'
import type { ReindexStatus } from '@/lib/api-client'

/**
 * ReindexButton (CR5) — kick off an extractive reindex of the current scope
 * slice, then poll status until it settles.
 *
 * POSTs `/api/claims/reindex?path=&grain=&model=` and polls
 * `/api/claims/reindex/status` every ~1.5s while `state === 'running'`,
 * surfacing `state`, `sessions_done/sessions_total`, and `failures`. The
 * button is disabled while running so a second click can't double-dispatch
 * (the backend is single-flight anyway, but the UI shouldn't invite it).
 */

const POLL_INTERVAL_MS = 1500

interface ReindexButtonProps {
  path: string
  grain: string
  model: string
}

export default function ReindexButton({ path, grain, model }: ReindexButtonProps) {
  const [status, setStatus] = useState<ReindexStatus | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const poll = useCallback(async () => {
    const result = await apiClient.getClaimsReindexStatus()
    if (isApiSuccess(result)) {
      setStatus(result.data)
      if (result.data.state === 'running') {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }
  }, [])

  // Tear down the poll loop on unmount.
  useEffect(() => clearTimer, [clearTimer])

  const running = status?.state === 'running'

  const onClick = useCallback(async () => {
    if (running) return
    clearTimer()
    const result = await apiClient.startClaimsReindex({ path, grain, model })
    if (isApiSuccess(result)) {
      // Seed an optimistic running state so the button disables immediately,
      // then start polling for the authoritative status.
      setStatus((prev) => ({
        state: 'running',
        scope_path: path,
        grain,
        model,
        sessions_total: prev?.sessions_total ?? 0,
        sessions_done: 0,
        failures: 0,
        rollups_written: 0,
        message: result.data.message ?? 'Reindex started',
        error: null,
      }))
      void poll()
    }
  }, [running, clearTimer, path, grain, model, poll])

  return (
    <div className="flex flex-col items-end gap-1 text-sm">
      <Button
        data-testid="reindex-button"
        type="button"
        variant="outline"
        size="sm"
        onClick={onClick}
        disabled={running}
      >
        {running ? 'Reindexing…' : 'Reindex this slice'}
      </Button>
      {status ? (
        <span data-testid="reindex-status" className="text-xs text-muted-foreground">
          {status.state} · {status.sessions_done}/{status.sessions_total} sessions
          {status.failures > 0 ? ` · ${status.failures} failures` : ''}
          {status.state === 'error' && status.error ? ` · ${status.error}` : ''}
        </span>
      ) : null}
    </div>
  )
}
