import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search as SearchIcon, Filter } from 'lucide-react'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName } from '@/lib/formatters'
import { MSG_KIND_OPTIONS } from '@/lib/message-kinds'
import type { MessageKind, SearchResultRow } from '@/lib/api-client'

const QUERY_DEBOUNCE_MS = 300

/** Short label for the session_id badge shown on each result card. We
 * only show the first 8 hex chars — enough to identify a session at a
 * glance, short enough to sit next to the timestamp without wrapping. */
const SESSION_ID_DISPLAY_LEN = 8

export default function SearchPage() {
  const { buildApiQuery, filterSearchString } = useFilters()
  const [searchParams, setSearchParams] = useSearchParams()

  // The input is a controlled component, so we keep a local copy that
  // updates on every keystroke. The debounce effect below is responsible
  // for pushing this value into `?q=` — which in turn triggers the API
  // fetch. This keeps typing snappy without flooding the backend.
  const urlQuery = searchParams.get('q') ?? ''
  const [inputValue, setInputValue] = useState(urlQuery)

  // Message-kind filter lives on `?msg=` — same URL convention as
  // SessionDetail, so a deep link from one view carries the filter into
  // the other. Empty string means "no filter".
  const msgKindFilter = (searchParams.get('msg') ?? '') as MessageKind | ''

  // Debounce local input → URL. We intentionally do NOT strip whitespace
  // here so that pasting a query with a leading space still feels
  // responsive; the backend handles whitespace-only queries by returning
  // an empty list.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (inputValue.trim() === '') {
          next.delete('q')
        } else {
          next.set('q', inputValue)
        }
        return next
      })
    }, QUERY_DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
    // We deliberately depend only on `inputValue` — if the URL changes
    // from some other source (e.g. back button), the urlQuery → input
    // sync effect below handles it without scheduling another write.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputValue])

  // If the URL changes externally (back/forward, shared link, filter
  // clear), reflect that back into the input.
  useEffect(() => {
    setInputValue(urlQuery)
  }, [urlQuery])

  // Write the msg-kind dropdown selection to `?msg=` (or clear it).
  const setMsgKindFilter = (kind: MessageKind | '') => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (kind) {
        next.set('msg', kind)
      } else {
        next.delete('msg')
      }
      return next
    })
  }

  // Skip fetching on empty queries — `useApi(null)` is the idiomatic
  // way to conditionally fetch. Saves a round-trip on initial mount.
  const apiEndpoint = useMemo(() => {
    const trimmed = urlQuery.trim()
    if (!trimmed) return null
    // Put `q` and (optionally) `msg_kind` into the existing filter query
    // string so days/project stack on top of them. The backend applies
    // `msg_kind` before the LIMIT so selecting "human prompts" yields
    // the top-N human prompts, not a post-filter of the overall top-N.
    const extra: Record<string, string | number | null> = { q: trimmed, limit: 50 }
    if (msgKindFilter) extra.msg_kind = msgKindFilter
    return `/search${buildApiQuery(extra)}`
  }, [urlQuery, msgKindFilter, buildApiQuery])

  const { data: results, loading, error } = useApi<SearchResultRow[]>(apiEndpoint)

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Search</h1>

      {/* Search input card — full-width input on the top row, the kind
          filter on the row below so it doesn't compress the input width
          on narrow viewports. */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Search event messages…"
              className="w-full pl-10 pr-3 py-2 border rounded-lg bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              autoFocus
              data-testid="search-input"
            />
          </div>

          {/* Kind filter row — mirrors the dropdown on SessionDetail and
              uses the same `?msg=` param so filters are portable between
              the two views. */}
          <div className="flex items-center gap-2 mt-3">
            <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <label className="text-sm text-muted-foreground">Message kind:</label>
            <select
              value={msgKindFilter}
              onChange={(e) => setMsgKindFilter(e.target.value as MessageKind | '')}
              className="text-sm border rounded px-2 py-1 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              data-testid="msg-kind-filter"
              title={
                MSG_KIND_OPTIONS.find((o) => o.value === msgKindFilter)
                  ?.description
              }
            >
              {MSG_KIND_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} title={opt.description}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <p className="text-xs text-muted-foreground mt-2">
            Full-text search over event content via SQLite FTS5. Scoped by the
            global time range, project, and message-kind filters.
          </p>
        </CardContent>
      </Card>

      {/* Results section. Three states: no query (instructions),
          loading, or the ranked list. */}
      {urlQuery.trim() === '' ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground" data-testid="search-empty">
              Type a query above to search across event messages.
            </p>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="text-center py-8" data-testid="search-loading">
          Searching…
        </div>
      ) : error ? (
        <div className="text-center py-8 text-red-500">Error: {error}</div>
      ) : !results || results.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground" data-testid="search-no-results">
              No matches for "{urlQuery.trim()}" under current filters.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="search-results">
          <p className="text-sm text-muted-foreground">
            {results.length} {results.length === 1 ? 'match' : 'matches'} (ranked by relevance)
          </p>
          {results.map((row, idx) => {
            // Link target: deep-link into session detail (with the event
            // UUID when available, so the session page opens already
            // scoped to that event's subtree). Fall back to the project
            // sessions listing when the row lacks a session_id. We also
            // forward the msg-kind filter so the destination page
            // preserves it.
            let href: string
            if (row.session_id) {
              const params = new URLSearchParams(filterSearchString.replace(/^\?/, ''))
              if (row.uuid) params.set('event_uuid', row.uuid)
              if (msgKindFilter) params.set('msg', msgKindFilter)
              const qs = params.toString()
              href = `/sessions/${encodeURIComponent(row.project_id)}/${encodeURIComponent(row.session_id)}${qs ? `?${qs}` : ''}`
            } else {
              href = `/sessions/${encodeURIComponent(row.project_id)}${filterSearchString}`
            }

            // Session id display: first 8 hex chars, or "—" for the rare
            // row without one. Full id lives in a title attribute for
            // copy-on-hover.
            const sessionShort = row.session_id
              ? row.session_id.slice(0, SESSION_ID_DISPLAY_LEN)
              : '—'

            return (
              <Link
                key={`${row.uuid ?? 'norow'}-${idx}`}
                to={href}
                className="block group"
                data-testid="search-result-row"
              >
                <Card className="transition-colors hover:border-primary/50 hover:bg-muted/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-sm font-normal gap-2">
                      <span className="truncate text-muted-foreground group-hover:text-primary transition-colors">
                        {formatProjectName(row.project_id)}
                      </span>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span
                          className="text-xs text-muted-foreground font-mono px-1.5 py-0.5 bg-muted rounded"
                          title={row.session_id ?? ''}
                          data-testid="search-result-session-id"
                        >
                          {sessionShort}
                        </span>
                        {row.timestamp_local && (
                          <span className="text-xs text-muted-foreground font-mono">
                            {new Date(row.timestamp_local).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {/* Snippet renders <mark> tags emitted by FTS5. The
                        surrounding text is HTML-escaped by the snippet()
                        function, so this is safe. */}
                    <p
                      className="text-sm leading-relaxed [&_mark]:bg-yellow-200 [&_mark]:text-foreground dark:[&_mark]:bg-yellow-900 [&_mark]:rounded [&_mark]:px-1"
                      dangerouslySetInnerHTML={{ __html: row.snippet }}
                    />
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-2 font-mono">
                      {row.message_kind && <span>{row.message_kind}</span>}
                      {row.model_id && <span>· {row.model_id}</span>}
                      <span>· rank {row.rank.toFixed(2)}</span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
