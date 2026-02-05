import { useMemo, useState, useEffect, useCallback } from 'react'
import { useParams, Link, useSearchParams, useLocation, useNavigate } from 'react-router-dom'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName } from '@/lib/formatters'
import type { SessionEvent, MessageContentItem } from '@/lib/api-client'
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
} from 'lucide-react'

// Event type styling
const EVENT_TYPE_CONFIG: Record<string, { icon: typeof User; color: string; bgColor: string }> = {
  user: {
    icon: User,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
  },
  assistant: {
    icon: Bot,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
  },
  system: {
    icon: Settings,
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-50 dark:bg-gray-800/30 border-gray-200 dark:border-gray-700',
  },
}

function getEventConfig(eventType: string) {
  return (
    EVENT_TYPE_CONFIG[eventType] || {
      icon: MessageSquare,
      color: 'text-purple-600 dark:text-purple-400',
      bgColor: 'bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800',
    }
  )
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
  onUuidClick,
  onFilterClick,
  isHighlighted,
}: {
  event: SessionEvent
  eventMap: Map<string, SessionEvent>
  onUuidClick: (uuid: string) => void
  onFilterClick: (uuid: string) => void
  isHighlighted?: boolean
}) {
  const [showJson, setShowJson] = useState(false)

  const config = getEventConfig(event.event_type)
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

      {/* Event header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full bg-background`}>
            <Icon className={`h-4 w-4 ${config.color}`} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`font-medium ${config.color}`}>{event.event_type}</span>
              {event.is_subagent_file && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                  <GitBranch className="h-3 w-3" />
                  {event.agent_slug || 'subagent'}
                </span>
              )}
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

      {/* Collapsible raw JSON */}
      <div className="mt-3 border-t pt-2">
        <button
          onClick={() => setShowJson(!showJson)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {showJson ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <Code className="h-3 w-3" />
          {showJson ? 'Hide' : 'Show'} raw JSON
        </button>
        {showJson && (
          <pre className="mt-2 p-3 bg-muted/50 rounded text-xs font-mono overflow-x-auto max-h-96 overflow-y-auto">
            {JSON.stringify(event.message_json, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

export default function SessionDetail() {
  const { projectId, sessionId } = useParams<{ projectId: string; sessionId: string }>()
  const { filterSearchString } = useFilters()
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()

  // Get event_uuid filter from query params
  const eventUuidFilter = searchParams.get('event_uuid')
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

  // Build event lookup map for parent references
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
      const newParams = new URLSearchParams(searchParams)
      newParams.set('event_uuid', uuid)
      setSearchParams(newParams)
    },
    [searchParams, setSearchParams]
  )

  // Clear the event_uuid filter
  const clearEventFilter = useCallback(() => {
    const newParams = new URLSearchParams(searchParams)
    newParams.delete('event_uuid')
    setSearchParams(newParams)
  }, [searchParams, setSearchParams])

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
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Event Timeline
            {events && (
              <span className="text-sm font-normal text-muted-foreground ml-2">
                ({events.length} events{eventUuidFilter && ' filtered'})
              </span>
            )}
          </CardTitle>
          {/* Filter indicator */}
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
          {!events || events.length === 0 ? (
            eventUuidFilter ? (
              <div className="text-center py-8">
                <p className="text-muted-foreground">No events match the filter</p>
                <button
                  onClick={clearEventFilter}
                  className="mt-2 text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Clear filter
                </button>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">No events found</p>
            )
          ) : (
            <div className="space-y-3">
              {events.map((event, index) => (
                <EventCard
                  key={event.uuid || `event-${index}`}
                  event={event}
                  eventMap={eventMap}
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
