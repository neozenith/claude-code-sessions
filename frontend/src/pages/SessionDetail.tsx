import { useMemo, useState, useEffect, useCallback } from 'react'
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName } from '@/lib/formatters'
import type { SessionEvent, MessageContentItem, MessageKind } from '@/lib/api-client'
import { MSG_KIND_OPTIONS } from '@/lib/message-kinds'
import {
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  User,
  Bot,
  Settings,
  GitBranch,
  Clock,
  ArrowRight,
  MessageSquare,
  FileText,
  Code,
  Brain,
  Wrench,
  X,
  Filter,
  Activity,
  BellRing,
} from 'lucide-react'

// Message kind filter options — "All messages" + the 9 fine-grained kinds
// Message kind styling — one unique color + icon per derived kind
const MESSAGE_KIND_CONFIG: Record<MessageKind, { icon: typeof User; label: string; color: string; bgColor: string; badgeBg: string }> = {
  human: {
    icon: User,
    label: 'Human prompt',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    badgeBg: 'bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-300',
  },
  task_notification: {
    icon: BellRing,
    label: 'Task notification',
    color: 'text-teal-600 dark:text-teal-400',
    bgColor: 'bg-teal-50 dark:bg-teal-900/20 border-teal-200 dark:border-teal-800',
    badgeBg: 'bg-teal-100 text-teal-800 dark:bg-teal-900/60 dark:text-teal-300',
  },
  assistant_text: {
    icon: Bot,
    label: 'Assistant text',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800',
    badgeBg: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300',
  },
  thinking: {
    icon: Brain,
    label: 'Thinking',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800',
    badgeBg: 'bg-purple-100 text-purple-800 dark:bg-purple-900/60 dark:text-purple-300',
  },
  tool_use: {
    icon: Wrench,
    label: 'Tool call',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',
    badgeBg: 'bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300',
  },
  tool_result: {
    icon: Code,
    label: 'Tool result',
    color: 'text-cyan-600 dark:text-cyan-400',
    bgColor: 'bg-cyan-50 dark:bg-cyan-900/20 border-cyan-200 dark:border-cyan-800',
    badgeBg: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/60 dark:text-cyan-300',
  },
  user_text: {
    icon: MessageSquare,
    label: 'User text',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-800',
    badgeBg: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/60 dark:text-indigo-300',
  },
  meta: {
    icon: Settings,
    label: 'Meta / injected',
    color: 'text-slate-600 dark:text-slate-400',
    bgColor: 'bg-slate-100 dark:bg-slate-800/30 border-slate-300 dark:border-slate-700',
    badgeBg: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  },
  other: {
    icon: Activity,
    label: 'System / progress',
    color: 'text-rose-600 dark:text-rose-400',
    bgColor: 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800',
    badgeBg: 'bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-300',
  },
}

function getMessageKindConfig(kind: MessageKind) {
  return MESSAGE_KIND_CONFIG[kind] ?? MESSAGE_KIND_CONFIG.other
}

// Parse message content - handles nested content types
// Content can be: string, JSON string, or already-parsed array of content items
function parseMessageContent(content: string | MessageContentItem[] | null): MessageContentItem[] {
  if (!content) return []

  // If already an array, return as-is
  if (Array.isArray(content)) {
    return content
  }

  // Try to parse string as JSON array
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) {
        return parsed as MessageContentItem[]
      }
      // If it's an object with a type, wrap it
      if (parsed && typeof parsed === 'object' && 'type' in parsed) {
        return [parsed as MessageContentItem]
      }
    } catch {
      // Not JSON, treat as plain text
    }
    // Return as plain text item
    return [{ type: 'text', text: content }]
  }

  return []
}

// Content type icon
function getContentTypeIcon(type: string) {
  switch (type) {
    case 'thinking':
      return Brain
    case 'tool_use':
      return Wrench
    case 'tool_result':
      return Code
    default:
      return MessageSquare
  }
}

// Render a single content item
function ContentItem({ item, depth = 0 }: { item: MessageContentItem; depth?: number }) {
  const [expanded, setExpanded] = useState(true)
  const Icon = getContentTypeIcon(item.type)

  const contentTypeColors: Record<string, string> = {
    text: 'border-l-gray-400',
    thinking: 'border-l-purple-400 bg-purple-50/50 dark:bg-purple-900/10',
    tool_use: 'border-l-orange-400 bg-orange-50/50 dark:bg-orange-900/10',
    tool_result: 'border-l-cyan-400 bg-cyan-50/50 dark:bg-cyan-900/10',
  }

  const borderColor = contentTypeColors[item.type] || 'border-l-gray-300'

  return (
    <div className={`border-l-2 pl-3 py-1 ${borderColor}`} style={{ marginLeft: depth * 16 }}>
      <div
        className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer hover:text-foreground"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <Icon className="h-3 w-3" />
        <span className="font-medium">{item.type}</span>
        {item.name && <span className="text-blue-600 dark:text-blue-400">({item.name})</span>}
        {item.id && <span className="font-mono text-xs opacity-60">id: {item.id}</span>}
      </div>
      {expanded && (
        <div className="mt-1">
          {/* Text content */}
          {item.text && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-foreground/90 max-h-96 overflow-y-auto">
              {item.text}
            </pre>
          )}
          {/* Thinking content */}
          {item.thinking && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-foreground/90 max-h-96 overflow-y-auto italic">
              {item.thinking}
            </pre>
          )}
          {/* Tool input */}
          {item.input && (
            <pre className="whitespace-pre-wrap font-mono text-xs bg-muted/50 p-2 rounded max-h-64 overflow-y-auto">
              {typeof item.input === 'string' ? item.input : JSON.stringify(item.input, null, 2)}
            </pre>
          )}
          {/* Tool result content */}
          {item.content && typeof item.content === 'string' && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-foreground/90 max-h-96 overflow-y-auto">
              {item.content}
            </pre>
          )}
          {/* Nested content array */}
          {item.content && Array.isArray(item.content) && (
            <div className="space-y-1 mt-1">
              {item.content.map((subItem, i) => (
                <ContentItem key={i} item={subItem} depth={depth + 1} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Single event card component - flat rendering for timeline view
function EventCard({
  event,
  eventMap,
  projectId,
  sessionId,
  onUuidClick,
  onFilterClick,
  isHighlighted,
}: {
  event: SessionEvent
  eventMap: Map<string, SessionEvent>
  projectId: string
  sessionId: string
  onUuidClick: (uuid: string) => void
  onFilterClick: (uuid: string) => void
  isHighlighted?: boolean
}) {
  const [showJson, setShowJson] = useState(false)
  // Raw JSON is fetched on demand — not stored in the cache any more
  const [rawJson, setRawJson] = useState<string | null>(null)
  const [rawJsonLoading, setRawJsonLoading] = useState(false)
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)

  const handleToggleJson = async () => {
    const willShow = !showJson
    setShowJson(willShow)

    // Fetch on first open, only if we have a uuid to look up
    if (willShow && rawJson === null && !rawJsonLoading && event.uuid) {
      setRawJsonLoading(true)
      setRawJsonError(null)
      try {
        const url =
          `/api/sessions/${encodeURIComponent(projectId)}` +
          `/${encodeURIComponent(sessionId)}` +
          `/events/${encodeURIComponent(event.uuid)}/raw`
        const res = await fetch(url)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const body = (await res.json()) as { raw_json: string | null; found: boolean }
        if (!body.found || body.raw_json === null) {
          setRawJsonError('Event not found in source JSONL file')
        } else {
          // Pretty-print — the API returns the line as-is
          try {
            const parsed = JSON.parse(body.raw_json)
            setRawJson(JSON.stringify(parsed, null, 2))
          } catch {
            setRawJson(body.raw_json)
          }
        }
      } catch (err) {
        setRawJsonError(err instanceof Error ? err.message : 'Fetch failed')
      } finally {
        setRawJsonLoading(false)
      }
    }
  }

  const config = getMessageKindConfig(event.message_kind)
  const Icon = config.icon
  const parentEvent = event.parent_uuid ? eventMap.get(event.parent_uuid) : null
  const contentItems = parseMessageContent(event.message_content)

  // Clickable UUID component
  const ClickableUuid = ({ uuid, label }: { uuid: string; label: string }) => (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground">{label}:</span>
      <button
        onClick={() => onUuidClick(uuid)}
        className="break-all select-all text-blue-600 dark:text-blue-400 hover:underline cursor-pointer"
        title={`Scroll to ${uuid}`}
      >
        {uuid}
      </button>
      <button
        onClick={() => onFilterClick(uuid)}
        className="p-0.5 hover:bg-muted rounded transition-colors"
        title={`Filter to this event and its children`}
      >
        <Filter className="h-3 w-3 text-muted-foreground hover:text-foreground" />
      </button>
    </div>
  )

  return (
    <div
      id={event.uuid || undefined}
      className={`relative p-4 rounded-lg border ${config.bgColor} ${
        isHighlighted ? 'ring-2 ring-blue-500 ring-offset-2' : ''
      }`}
    >
      {/* Subagent indicator */}
      {event.is_subagent_file && (
        <div className="absolute -left-3 top-4 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
          <GitBranch className="h-3 w-3 text-white" />
        </div>
      )}

      {/* Message kind badge */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${config.badgeBg}`}>
          <Icon className="h-3.5 w-3.5" />
          {config.label}
        </span>
        {event.is_subagent_file && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
            <GitBranch className="h-3 w-3" />
            {event.agent_slug || 'subagent'}
          </span>
        )}
      </div>

      {/* Event header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-full bg-background">
            <Icon className={`h-4 w-4 ${config.color}`} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`font-medium ${config.color}`}>{event.event_type}</span>
              {event.model_id && (
                <span className="text-xs text-muted-foreground">
                  {event.model_id.replace('claude-', '').replace(/-\d+$/, '')}
                </span>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {event.timestamp_local
                ? new Date(event.timestamp_local).toLocaleString()
                : 'No timestamp'}
            </div>
          </div>
        </div>

        <div className="text-right text-xs text-muted-foreground flex-shrink-0">
          {event.input_tokens > 0 && <div>In: {event.input_tokens.toLocaleString()}</div>}
          {event.output_tokens > 0 && <div>Out: {event.output_tokens.toLocaleString()}</div>}
        </div>
      </div>

      {/* Parent reference - clickable */}
      {parentEvent && (
        <div className="mt-2 text-xs text-muted-foreground flex items-center gap-1">
          <ArrowRight className="h-3 w-3" />
          Reply to:{' '}
          <button
            onClick={() => event.parent_uuid && onUuidClick(event.parent_uuid)}
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            {parentEvent.event_type} at {new Date(parentEvent.timestamp_local || '').toLocaleTimeString()}
          </button>
        </div>
      )}

      {/* File location */}
      <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <FileText className="h-3 w-3" />
        <span className="font-mono break-all">{event.filepath}</span>
        {event.line_number && (
          <span className="text-blue-600 dark:text-blue-400">:{event.line_number}</span>
        )}
      </div>

      {/* Message content - parsed by type */}
      {contentItems.length > 0 && (
        <div className="mt-3 space-y-2">
          {contentItems.map((item, i) => (
            <ContentItem key={i} item={item} />
          ))}
        </div>
      )}

      {/* UUID info - clickable */}
      <div className="mt-3 space-y-1 text-xs font-mono text-muted-foreground/70">
        {event.uuid && <ClickableUuid uuid={event.uuid} label="uuid" />}
        {event.parent_uuid && <ClickableUuid uuid={event.parent_uuid} label="parent" />}
      </div>

      {/* Collapsible raw JSON — fetched on demand from source JSONL */}
      <div className="mt-3 border-t pt-2">
        <button
          onClick={handleToggleJson}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          disabled={!event.uuid}
          title={event.uuid ? undefined : 'This event has no UUID and cannot be looked up'}
        >
          {showJson ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <Code className="h-3 w-3" />
          {showJson ? 'Hide' : 'Show'} raw JSON
        </button>
        {showJson && (
          <pre className="mt-2 p-3 bg-muted/50 rounded text-xs font-mono overflow-x-auto max-h-96 overflow-y-auto">
            {rawJsonLoading
              ? 'Loading raw JSON from source file…'
              : rawJsonError
                ? `Error: ${rawJsonError}`
                : rawJson ?? '(no data)'}
          </pre>
        )}
      </div>
    </div>
  )
}

export default function SessionDetail() {
  const { projectId, sessionId } = useParams<{ projectId: string; sessionId: string }>()
  const { filterSearchString } = useFilters()
  const location = useLocation()
  const navigate = useNavigate()

  // Filter state — useState for immediate reactivity, synced with URL.
  // React Router's navigate/setSearchParams doesn't reliably trigger
  // re-renders when useFilters (Layout) also uses useSearchParams.
  const [msgKindFilter, setMsgKindState] = useState<MessageKind | ''>(() => {
    const params = new URLSearchParams(location.search)
    return (params.get('msg') ?? '') as MessageKind | ''
  })
  const [eventUuidFilter, setEventUuidState] = useState<string | null>(() => {
    const params = new URLSearchParams(location.search)
    return params.get('event_uuid')
  })

  // Sync state from URL on navigation (back/forward, external URL changes)
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    setMsgKindState((params.get('msg') ?? '') as MessageKind | '')
    setEventUuidState(params.get('event_uuid'))
  }, [location.search])

  // Helper: update both React state (immediate) and URL (for deep linking)
  const updateSearchParams = useCallback(
    (updater: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(location.search)
      updater(params)
      // Sync local state immediately from the updated params
      setMsgKindState((params.get('msg') ?? '') as MessageKind | '')
      setEventUuidState(params.get('event_uuid'))
      // Update URL for deep linking
      const qs = params.toString()
      navigate(`${location.pathname}${qs ? `?${qs}` : ''}${location.hash}`, { replace: true })
    },
    [navigate, location.pathname, location.search, location.hash]
  )

  const [highlightedUuid, setHighlightedUuid] = useState<string | null>(null)

  // Build API URL with optional event_uuid filter (filtering happens server-side)
  const apiUrl = useMemo(() => {
    if (!projectId || !sessionId) return null
    const base = `/sessions/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}`
    if (eventUuidFilter) {
      return `${base}?event_uuid=${encodeURIComponent(eventUuidFilter)}`
    }
    return base
  }, [projectId, sessionId, eventUuidFilter])

  const { data: events, loading, error } = useApi<SessionEvent[]>(apiUrl)

  // Client-side message kind filter (applied on top of the server-side event_uuid filter)
  const visibleEvents = useMemo(() => {
    if (!events) return []
    if (!msgKindFilter) return events
    return events.filter((e) => e.message_kind === msgKindFilter)
  }, [events, msgKindFilter])

  // Build event lookup map for parent references (always from full event set)
  const eventMap = useMemo(() => {
    if (!events) return new Map<string, SessionEvent>()

    const map = new Map<string, SessionEvent>()
    events.forEach((event) => {
      if (event.uuid) {
        map.set(event.uuid, event)
      }
    })
    return map
  }, [events])

  // Scroll to element by UUID
  const scrollToUuid = useCallback((uuid: string) => {
    const element = document.getElementById(uuid)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlightedUuid(uuid)
      // Remove highlight after a delay
      setTimeout(() => setHighlightedUuid(null), 2000)
    }
  }, [])

  // Handle UUID click - updates URL fragment and scrolls
  const handleUuidClick = useCallback(
    (uuid: string) => {
      // Update URL with fragment
      navigate(`${location.pathname}${location.search}#${uuid}`, { replace: true })
      scrollToUuid(uuid)
    },
    [navigate, location.pathname, location.search, scrollToUuid]
  )

  // Handle filter click - sets event_uuid query parameter
  const handleFilterClick = useCallback(
    (uuid: string) => {
      updateSearchParams((params) => params.set('event_uuid', uuid))
    },
    [updateSearchParams]
  )

  // Clear the event_uuid filter
  const clearEventFilter = useCallback(() => {
    updateSearchParams((params) => params.delete('event_uuid'))
  }, [updateSearchParams])

  // Set/clear the message kind filter
  const setMsgKindFilter = useCallback(
    (kind: MessageKind | '') => {
      updateSearchParams((params) => {
        if (kind) {
          params.set('msg', kind)
        } else {
          params.delete('msg')
        }
      })
    },
    [updateSearchParams]
  )

  // Scroll to fragment on load/change
  useEffect(() => {
    if (events && location.hash) {
      const uuid = location.hash.slice(1) // Remove the '#'
      // Small delay to ensure DOM is ready
      setTimeout(() => scrollToUuid(uuid), 100)
    }
  }, [events, location.hash, scrollToUuid])

  // Calculate summary stats
  const summaryStats = useMemo(() => {
    if (!events) return null

    const uniqueAgents = new Set(events.filter((e) => e.agent_slug).map((e) => e.agent_slug))
    const mainAgentEvents = events.filter((e) => !e.is_sidechain).length
    const subagentEvents = events.filter((e) => e.is_sidechain).length

    return {
      totalEvents: events.length,
      mainAgentEvents,
      subagentEvents,
      uniqueAgents: uniqueAgents.size,
      totalInputTokens: events.reduce((acc, e) => acc + (e.input_tokens || 0), 0),
      totalOutputTokens: events.reduce((acc, e) => acc + (e.output_tokens || 0), 0),
    }
  }, [events])

  if (!projectId || !sessionId) {
    return <div className="text-center py-8 text-red-500">Missing project or session ID</div>
  }

  if (loading) return <div className="text-center py-8">Loading session events...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-6">
      {/* Header with breadcrumb */}
      <div className="flex items-center gap-4">
        <Link
          to={`/sessions/${encodeURIComponent(projectId)}${filterSearchString}`}
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to {formatProjectName(projectId)}
        </Link>
      </div>

      <div>
        <h1 className="text-3xl font-bold">Session Detail</h1>
        <p className="text-muted-foreground mt-1">
          <span className="font-medium">{formatProjectName(projectId)}</span>
          <span className="mx-2">·</span>
          <span className="font-mono text-sm">{sessionId}</span>
        </p>
      </div>

      {/* Summary Stats */}
      {summaryStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Total Events</p>
              <p className="text-2xl font-bold">{summaryStats.totalEvents}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Main Agent</p>
              <p className="text-2xl font-bold">{summaryStats.mainAgentEvents}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Subagent Events</p>
              <p className="text-2xl font-bold">{summaryStats.subagentEvents}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Unique Agents</p>
              <p className="text-2xl font-bold">{summaryStats.uniqueAgents}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Input Tokens</p>
              <p className="text-2xl font-bold">{summaryStats.totalInputTokens.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Output Tokens</p>
              <p className="text-2xl font-bold">{summaryStats.totalOutputTokens.toLocaleString()}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Events Timeline - Flat chronological list */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Event Timeline
              {events && (
                <span className="text-sm font-normal text-muted-foreground ml-2">
                  ({visibleEvents.length}{visibleEvents.length !== events.length && ` of ${events.length}`} events
                  {(eventUuidFilter || msgKindFilter) && ' filtered'})
                </span>
              )}
            </CardTitle>
            {/* Message kind dropdown */}
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <select
                value={msgKindFilter}
                onChange={(e) => setMsgKindFilter(e.target.value as MessageKind | '')}
                className="text-sm border rounded px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                data-testid="msg-kind-filter"
                title={MSG_KIND_OPTIONS.find(o => o.value === msgKindFilter)?.description}
              >
                {MSG_KIND_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} title={opt.description}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {/* Event UUID filter indicator */}
          {eventUuidFilter && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-sm text-muted-foreground">Filtered to:</span>
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-mono bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                <Filter className="h-3 w-3" />
                {eventUuidFilter.slice(0, 8)}...
              </span>
              <button
                onClick={clearEventFilter}
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs bg-muted hover:bg-muted/80 transition-colors"
                title="Clear filter"
              >
                <X className="h-3 w-3" />
                Clear
              </button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {visibleEvents.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground">
                {msgKindFilter || eventUuidFilter ? 'No events match the active filters' : 'No events found'}
              </p>
              {msgKindFilter && (
                <button
                  onClick={() => setMsgKindFilter('')}
                  className="mt-2 text-blue-600 dark:text-blue-400 hover:underline text-sm"
                >
                  Show all message types
                </button>
              )}
              {eventUuidFilter && (
                <button
                  onClick={clearEventFilter}
                  className="mt-2 ml-2 text-blue-600 dark:text-blue-400 hover:underline text-sm"
                >
                  Clear UUID filter
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {visibleEvents.map((event, index) => (
                <EventCard
                  key={event.uuid ? `${event.uuid}-${index}` : `event-${index}`}
                  event={event}
                  eventMap={eventMap}
                  projectId={projectId ?? ''}
                  sessionId={sessionId ?? ''}
                  onUuidClick={handleUuidClick}
                  onFilterClick={handleFilterClick}
                  isHighlighted={event.uuid === highlightedUuid}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
