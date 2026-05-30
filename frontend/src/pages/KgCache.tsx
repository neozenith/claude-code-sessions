import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Clock,
  Database,
  Loader2,
  Play,
  RefreshCw,
} from 'lucide-react'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatWithCommas } from '@/lib/formatters'
import type { IndexerPhase, KGCacheStats, PipelineStage } from '@/lib/api-client'

/**
 * KG Cache — pipeline backlog diagnostics.
 *
 * Shows how far the cache → knowledge-graph pipeline has progressed at
 * each stage (ingest → chunk → embed → NER/RE → entity-embed → resolve →
 * communities → naming) so you can see where processing is backing up as
 * the indexer's waves iterate. The indexer's live status is shown at the
 * top — if a wave crashed, its error appears here verbatim.
 *
 * State note (URL-as-state rule): this page has no user-visible page
 * state to encode in the URL. The only local state is an ephemeral
 * refresh counter used to re-trigger the fetch, which is not shareable
 * state, so `useState` is correct here.
 */
export default function KgCache() {
  const [tick, setTick] = useState(0)
  // Appending a cache-busting param re-keys useApi's effect so it refetches.
  // FastAPI ignores undeclared query params, so `?t=` is harmless.
  const { data, loading, error } = useApi<KGCacheStats>(
    `/kg/cache-stats${tick ? `?t=${tick}` : ''}`
  )

  const phase = data?.indexer?.phase

  // Auto-refresh while the indexer is actively running so the backlog
  // numbers tick down live. Stop polling once it settles (idle/completed/
  // failed/cancelled) to avoid pointless requests.
  useEffect(() => {
    if (phase !== 'running') return
    const id = window.setInterval(() => setTick((t) => t + 1), 5000)
    return () => window.clearInterval(id)
  }, [phase])

  // The bottleneck is the first stage (in pipeline order) that still has a
  // backlog — that's where work is backing up.
  const bottleneckKey = data?.stages.find((s) => s.eligible > 0 && s.pending > 0)?.key ?? null

  const running = phase === 'running'
  const stagesComplete = data ? data.stages.filter((s) => s.pending === 0).length : 0
  const totalPending = data ? data.stages.reduce((sum, s) => sum + s.pending, 0) : 0

  // Trigger a background indexer pass. Idempotent server-side, so a
  // double-click can't spawn overlapping runs. After kicking it, bump the
  // refresh tick so the next poll shows phase=running, which in turn starts
  // the 5s auto-refresh loop above.
  const [triggering, setTriggering] = useState(false)
  const handleReindex = async () => {
    setTriggering(true)
    try {
      await fetch('/api/kg/reindex', { method: 'POST' })
      setTick((t) => t + 1)
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="space-y-6" data-testid="kg-cache-page">
      <header className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Database className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold">Knowledge Graph — Cache Pipeline</h1>
            <p className="text-sm text-muted-foreground">
              Per-stage processing backlog. Global across all projects (not affected by the
              time-range / project filters).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReindex}
            disabled={running || triggering}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            title={running ? 'Indexer already running' : 'Run an indexer pass now to drain the backlog'}
          >
            <Play className="h-4 w-4" />
            {running ? 'Indexing…' : triggering ? 'Starting…' : 'Run indexer'}
          </button>
          <button
            onClick={() => setTick((t) => t + 1)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm border rounded-lg hover:bg-accent transition-colors"
            title="Refresh stats now"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-300">
          Failed to load cache stats: {error}
        </div>
      )}

      {!data && loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading pipeline stats…
        </div>
      )}

      {data && (
        <>
          <IndexerBanner indexer={data.indexer} />

          {/* Coverage is distinct from indexer phase: the phase tells you
              the last run's lifecycle, this tells you how much of the
              pipeline is actually drained. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span>
              Pipeline coverage:{' '}
              <strong>
                {stagesComplete}/{data.stages.length}
              </strong>{' '}
              stages complete
            </span>
            {totalPending > 0 && (
              <span className="text-amber-600 dark:text-amber-400">
                {formatWithCommas(totalPending)} items pending
              </span>
            )}
            {running && (
              <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> updating live
              </span>
            )}
          </div>

          <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Metric label="Source files" value={data.source_files} sub={`${data.files_on_disk} on disk`} />
            <Metric label="Events" value={data.events_total} />
            <Metric label="Chunks" value={data.chunks_total} />
            <Metric label="Entities" value={data.entities_total} sub={`${data.unique_entities} unique`} />
            <Metric label="Relations" value={data.relations_total} />
            <Metric label="Graph nodes" value={data.nodes_total} />
            <Metric label="Graph edges" value={data.edges_total} />
            <Metric
              label="Communities"
              value={data.communities_total}
              sub={data.display_resolution !== null ? `at resolution ${data.display_resolution}` : undefined}
            />
          </section>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pipeline stages</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {data.stages.map((stage) => (
                <StageRow
                  key={stage.key}
                  stage={stage}
                  isBottleneck={stage.key === bottleneckKey}
                />
              ))}
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            Updated {new Date(data.generated_at).toLocaleString()}
            {phase === 'running' && ' · auto-refreshing every 5s while the indexer runs'}
          </p>
        </>
      )}
    </div>
  )
}

function Metric({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{formatWithCommas(value)}</p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  )
}

const PHASE_STYLES: Record<
  IndexerPhase,
  { box: string; icon: typeof CheckCircle2; iconClass: string; label: string }
> = {
  idle: { box: 'border-border bg-muted/40', icon: Clock, iconClass: 'text-muted-foreground', label: 'Idle' },
  running: { box: 'border-blue-500/40 bg-blue-500/10', icon: Loader2, iconClass: 'text-blue-600 dark:text-blue-400 animate-spin', label: 'Running' },
  completed: { box: 'border-green-500/40 bg-green-500/10', icon: CheckCircle2, iconClass: 'text-green-600 dark:text-green-400', label: 'Completed' },
  cancelled: { box: 'border-amber-500/40 bg-amber-500/10', icon: CircleSlash, iconClass: 'text-amber-600 dark:text-amber-400', label: 'Cancelled' },
  failed: { box: 'border-red-500/50 bg-red-500/10', icon: AlertTriangle, iconClass: 'text-red-600 dark:text-red-400', label: 'Failed' },
}

function IndexerBanner({ indexer }: { indexer: KGCacheStats['indexer'] }) {
  const style = PHASE_STYLES[indexer.phase] ?? PHASE_STYLES.idle
  const Icon = style.icon
  return (
    <div
      className={`rounded-lg border p-4 ${style.box}`}
      data-testid="kg-cache-indexer"
      data-phase={indexer.phase}
    >
      <div className="flex items-center gap-2">
        <Icon className={`h-5 w-5 ${style.iconClass}`} />
        <span className="font-semibold">Indexer: {style.label}</span>
        {indexer.started_at && (
          <span className="text-xs text-muted-foreground">
            started {new Date(indexer.started_at).toLocaleString()}
          </span>
        )}
        {indexer.finished_at && (
          <span className="text-xs text-muted-foreground">
            · finished {new Date(indexer.finished_at).toLocaleString()}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        This is the last indexer run's lifecycle — not overall coverage. A run can finish
        "Completed" with stages still pending; use <span className="font-medium">Run indexer</span> to
        drain them.
      </p>
      {indexer.error && (
        <pre className="mt-3 overflow-x-auto rounded bg-red-950/80 p-3 text-xs text-red-100 whitespace-pre-wrap">
          {indexer.error}
        </pre>
      )}
    </div>
  )
}

function barColor(stage: PipelineStage): string {
  if (stage.eligible === 0) return 'bg-muted-foreground/30'
  if (stage.pending === 0) return 'bg-green-500'
  if (stage.done === 0) return 'bg-amber-500'
  return 'bg-blue-500'
}

function StageRow({ stage, isBottleneck }: { stage: PipelineStage; isBottleneck: boolean }) {
  return (
    <div data-testid={`kg-cache-stage-${stage.key}`}>
      <div className="flex items-center justify-between mb-1 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-medium">{stage.label}</span>
          {isBottleneck && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-700 dark:text-amber-300 font-medium">
              backing up here
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-muted-foreground tabular-nums">
          <span>
            {formatWithCommas(stage.done)} / {formatWithCommas(stage.eligible)}
          </span>
          {stage.pending > 0 && (
            <span className="text-amber-600 dark:text-amber-400 font-medium">
              {formatWithCommas(stage.pending)} pending
            </span>
          )}
          <span className="w-12 text-right">{stage.percent}%</span>
        </div>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor(stage)}`}
          style={{ width: `${Math.min(100, Math.max(stage.eligible === 0 ? 0 : 2, stage.percent))}%` }}
        />
      </div>
      {stage.note && <p className="mt-1 text-xs text-muted-foreground">{stage.note}</p>}
    </div>
  )
}
