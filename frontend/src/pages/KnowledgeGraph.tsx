/**
 * Knowledge Graph page — entity-resolved cytoscape view.
 *
 * Visual parity target: http://localhost:5282/sessions_demo/kg/er/
 *
 * URL state:
 *   ?topN=2          — number of seed nodes (default 2)
 *   ?seedMetric=...  — degree | node_betweenness | edge_betweenness (default edge_betweenness)
 *   ?maxDepth=1      — BFS depth from seeds, 0 = unlimited (default 1)
 *   ?minDegree=5     — prune nodes with degree below this (default 5)
 *   ?layout=fcose    — fcose | elk | grid (default fcose)
 *   ?sizeMode=...    — uniform | degree | betweenness (default degree)
 *
 * Defaults are *omitted* from the URL for clean deep links, matching the
 * project convention documented in CLAUDE.md.
 *
 * Click-to-inspect: clicking any node, edge, or community parent box
 * surfaces its full details in the right panel; clicking the canvas
 * background clears the selection.
 *
 * fcose layout config: the right panel exposes the fcose JSON config
 * for live editing — invalid JSON is reported in-place and the layout
 * is not re-run until the JSON parses cleanly.
 */

import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import elk from 'cytoscape-elk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import { useSearchParams } from 'react-router-dom'

import {
  type KGCommunity,
  type KGEdge,
  type KGNode,
  type KGPayload,
  type SeedMetric,
  fetchKG,
  KGFetchError,
} from '@/lib/kg-client'
import { useTheme } from '@/contexts/ThemeContext'
import { useFilters } from '@/hooks/useFilters'
import KnowledgeGraphControls, {
  type LayoutEngine,
  type Selection,
  type SizeMode,
  DEFAULT_FCOSE_CONFIG,
  DEFAULT_FCOSE_CONFIG_JSON,
  DEFAULT_TOP_N,
  DEFAULT_SEED_METRIC,
  DEFAULT_MAX_DEPTH,
  DEFAULT_MIN_DEGREE,
  DEFAULT_LAYOUT,
  DEFAULT_SIZE_MODE,
} from '@/components/KnowledgeGraphControls'

cytoscape.use(fcose as unknown as cytoscape.Ext)
cytoscape.use(elk as unknown as cytoscape.Ext)

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; payload: KGPayload }

const COMMUNITY_ID_PREFIX = 'community_'

const communityIdFromCytoscapeId = (id: string): number | null => {
  if (!id.startsWith(COMMUNITY_ID_PREFIX)) return null
  const n = Number(id.slice(COMMUNITY_ID_PREFIX.length))
  return Number.isFinite(n) ? n : null
}

/** Hash-based hue picker so the same entity-type or rel-type always gets the same color.
 *  Cytoscape's renderer rejects `hsl()` strings — must return `#rrggbb`. */
const hueToHex = (hue: number, saturation = 0.6, lightness = 0.55): string => {
  const c = (1 - Math.abs(2 * lightness - 1)) * saturation
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1))
  const m = lightness - c / 2
  let r = 0
  let g = 0
  let b = 0
  if (hue < 60) [r, g, b] = [c, x, 0]
  else if (hue < 120) [r, g, b] = [x, c, 0]
  else if (hue < 180) [r, g, b] = [0, c, x]
  else if (hue < 240) [r, g, b] = [0, x, c]
  else if (hue < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  const toHex = (v: number) =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

const colorForKey = (key: string): string => {
  let h = 5381
  for (let i = 0; i < key.length; i++) h = (h * 33) ^ key.charCodeAt(i)
  const hue = Math.abs(h) % 360
  return hueToHex(hue)
}

const buildElements = (payload: KGPayload): cytoscape.ElementDefinition[] => {
  const parentIdFor = (cid: number) => `${COMMUNITY_ID_PREFIX}${cid}`

  const parents: cytoscape.ElementDefinition[] = payload.communities.map((c) => ({
    group: 'nodes',
    data: {
      id: parentIdFor(c.id),
      label: c.label ?? `community #${c.id}`,
      isCommunity: true,
      memberCount: c.member_count,
    },
  }))

  const children: cytoscape.ElementDefinition[] = payload.nodes.map((n) => ({
    group: 'nodes',
    data: {
      id: n.id,
      label: n.label,
      entityType: n.entity_type ?? '',
      mentionCount: n.mention_count ?? 0,
      nodeBetweenness: n.node_betweenness ?? 0,
      parent: n.community_id !== null ? parentIdFor(n.community_id) : undefined,
    },
  }))

  const nodeIdSet = new Set(children.map((c) => c.data.id as string))
  const edges: cytoscape.ElementDefinition[] = payload.edges
    .filter((e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target))
    .map((e, i) => ({
      group: 'edges',
      data: {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        relType: e.rel_type ?? '',
        weight: e.weight ?? 1,
        edgeBetweenness: e.edge_betweenness ?? 0,
      },
    }))

  return [...parents, ...children, ...edges]
}

const buildStylesheet = (
  payload: KGPayload,
  theme: 'light' | 'dark',
  sizeMode: SizeMode,
): cytoscape.StylesheetStyle[] => {
  const isDark = theme === 'dark'
  const base = {
    label: 'data(label)',
    'font-size': '8px',
    color: isDark ? '#e6e6e6' : '#222',
    'text-wrap': 'ellipsis',
    'text-max-width': '80px',
    'text-valign': 'center',
    'text-halign': 'center',
  } as const

  let sizeFn: (ele: cytoscape.NodeSingular) => number
  if (sizeMode === 'uniform') {
    sizeFn = () => 14
  } else if (sizeMode === 'degree') {
    const adj = new Map<string, number>()
    for (const e of payload.edges) {
      adj.set(e.source, (adj.get(e.source) ?? 0) + 1)
      adj.set(e.target, (adj.get(e.target) ?? 0) + 1)
    }
    const maxDeg = Math.max(1, ...Array.from(adj.values()))
    sizeFn = (ele) => {
      const id = ele.id()
      const d = adj.get(id) ?? 0
      return 6 + Math.sqrt(d / maxDeg) * 26
    }
  } else {
    const bcs = payload.nodes.map((n) => n.node_betweenness ?? 0)
    const maxBc = Math.max(0.001, ...bcs)
    const map = new Map(payload.nodes.map((n) => [n.id, n.node_betweenness ?? 0]))
    sizeFn = (ele) => {
      const v = map.get(ele.id()) ?? 0
      return 6 + Math.sqrt(v / maxBc) * 26
    }
  }

  const entityTypes = Array.from(
    new Set(payload.nodes.map((n) => n.entity_type ?? 'unknown')),
  )
  const nodeColorByType = new Map(entityTypes.map((t) => [t, colorForKey(t)]))

  const relTypes = Array.from(new Set(payload.edges.map((e) => e.rel_type ?? 'rel')))
  const edgeColorByType = new Map(relTypes.map((t) => [t, colorForKey(t)]))

  return [
    {
      selector: 'node',
      style: {
        ...base,
        'background-color': (ele: cytoscape.NodeSingular) => {
          const t = (ele.data('entityType') as string) || 'unknown'
          return nodeColorByType.get(t) ?? (isDark ? '#7AB3FF' : '#4F86C6')
        },
        width: sizeFn,
        height: sizeFn,
      } as cytoscape.Css.Node,
    },
    {
      selector: 'node[?isCommunity]',
      style: {
        'background-color': isDark ? '#3a341a' : '#F4E3A1',
        'background-opacity': 0.25,
        'border-color': isDark ? '#E0C765' : '#C19A00',
        'border-width': 1,
        label: 'data(label)',
        'font-size': '14px',
        'font-weight': 'bold',
        color: isDark ? '#F5DC78' : '#5A4300',
        'text-valign': 'top',
        'text-halign': 'center',
        'text-margin-y': -6,
        'text-wrap': 'ellipsis',
        'text-max-width': '200px',
        shape: 'round-rectangle',
        padding: '16px',
      } as unknown as cytoscape.Css.Node,
    },
    {
      selector: 'edge',
      style: {
        width: 1,
        'line-color': (ele: cytoscape.EdgeSingular) => {
          const t = (ele.data('relType') as string) || 'rel'
          return edgeColorByType.get(t) ?? (isDark ? '#5a6375' : '#999')
        },
        'target-arrow-color': (ele: cytoscape.EdgeSingular) => {
          const t = (ele.data('relType') as string) || 'rel'
          return edgeColorByType.get(t) ?? (isDark ? '#5a6375' : '#999')
        },
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        opacity: isDark ? 0.7 : 0.6,
      } as cytoscape.Css.Edge,
    },
    {
      selector: 'node:selected',
      style: { 'border-color': isDark ? '#ffbb33' : '#ff8800', 'border-width': 3 },
    },
    {
      selector: 'edge:selected',
      style: {
        'line-color': isDark ? '#ffbb33' : '#ff8800',
        'target-arrow-color': isDark ? '#ffbb33' : '#ff8800',
        width: 3,
        opacity: 1,
      },
    },
  ]
}

const ELK_CONFIG = {
  name: 'elk',
  fit: true,
  padding: 30,
  elk: {
    algorithm: 'layered',
    'elk.direction': 'DOWN',
    'elk.spacing.nodeNode': 40,
    'elk.layered.spacing.nodeNodeBetweenLayers': 60,
  },
}

const layoutFor = (engine: LayoutEngine, fcoseConfig: object): cytoscape.LayoutOptions => {
  if (engine === 'grid') return { name: 'grid', animate: false } as cytoscape.LayoutOptions
  if (engine === 'elk') return ELK_CONFIG as unknown as cytoscape.LayoutOptions
  return { name: 'fcose', ...fcoseConfig } as unknown as cytoscape.LayoutOptions
}

export default function KnowledgeGraph(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams()
  const { theme } = useTheme()
  const { filters } = useFilters()
  const cyRef = useRef<cytoscape.Core | null>(null)
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [selection, setSelection] = useState<Selection | null>(null)
  const [fcoseConfigText, setFcoseConfigText] = useState<string>(DEFAULT_FCOSE_CONFIG_JSON)
  const [fcoseConfigError, setFcoseConfigError] = useState<string | null>(null)
  const [appliedFcoseConfig, setAppliedFcoseConfig] = useState<object>(DEFAULT_FCOSE_CONFIG)

  const topN = Number(searchParams.get('topN') ?? DEFAULT_TOP_N)
  const seedMetric = (searchParams.get('seedMetric') ?? DEFAULT_SEED_METRIC) as SeedMetric
  const maxDepth = Number(searchParams.get('maxDepth') ?? DEFAULT_MAX_DEPTH)
  const minDegree = Number(searchParams.get('minDegree') ?? DEFAULT_MIN_DEGREE)
  const layoutEngine = (searchParams.get('layout') ?? DEFAULT_LAYOUT) as LayoutEngine
  const sizeMode = (searchParams.get('sizeMode') ?? DEFAULT_SIZE_MODE) as SizeMode
  const filterDays = filters.days
  const filterProject = filters.project

  const updateParam = useCallback(
    (key: string, value: string | null, defaultValue: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === null || value === defaultValue) {
          next.delete(key)
        } else {
          next.set(key, value)
        }
        return next
      })
    },
    [setSearchParams],
  )

  // Validate fcose JSON whenever the textarea changes.
  useEffect(() => {
    try {
      const parsed = JSON.parse(fcoseConfigText) as object
      setFcoseConfigError(null)
      setAppliedFcoseConfig(parsed)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setFcoseConfigError(message)
    }
  }, [fcoseConfigText])

  // Fetch KG payload whenever query params *or* global filters change.
  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    setSelection(null)
    fetchKG({
      topN,
      seedMetric,
      maxDepth,
      minDegree,
      days: filterDays,
      project: filterProject,
    })
      .then((payload) => {
        if (!cancelled) setState({ status: 'ready', payload })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message =
          err instanceof KGFetchError
            ? `${err.status}: ${err.body || err.message}`
            : err instanceof Error
              ? err.message
              : String(err)
        setState({ status: 'error', message })
      })
    return () => {
      cancelled = true
    }
  }, [topN, seedMetric, maxDepth, minDegree, filterDays, filterProject])

  // Indexes used by click handlers to resolve cytoscape ids back to KG payload rows.
  const indexes = useMemo(() => {
    if (state.status !== 'ready') {
      return {
        nodeById: new Map<string, KGNode>(),
        edgesByPair: new Map<string, KGEdge[]>(),
        communityById: new Map<number, KGCommunity>(),
      }
    }
    const nodeById = new Map(state.payload.nodes.map((n) => [n.id, n]))
    const edgesByPair = new Map<string, KGEdge[]>()
    for (const e of state.payload.edges) {
      const key = `${e.source}\x1f${e.target}`
      const arr = edgesByPair.get(key)
      if (arr) arr.push(e)
      else edgesByPair.set(key, [e])
    }
    const communityById = new Map(state.payload.communities.map((c) => [c.id, c]))
    return { nodeById, edgesByPair, communityById }
  }, [state])

  const elements = useMemo(
    () => (state.status === 'ready' ? buildElements(state.payload) : []),
    [state],
  )
  const stylesheet = useMemo(
    () =>
      state.status === 'ready'
        ? buildStylesheet(state.payload, theme === 'dark' ? 'dark' : 'light', sizeMode)
        : [],
    [state, theme, sizeMode],
  )

  const runLayout = useCallback(() => {
    const cy = cyRef.current
    if (!cy) return
    try {
      cy.layout(layoutFor(layoutEngine, appliedFcoseConfig)).run()
    } catch (err) {
      console.error('cytoscape layout error', err)
    }
  }, [layoutEngine, appliedFcoseConfig])

  // Run layout whenever payload, layout engine, or applied config changes.
  useEffect(() => {
    if (state.status !== 'ready') return
    let raf = 0
    let cancelled = false
    const expectedNodeCount = elements.filter((e) => e.group === 'nodes').length
    const tryLayout = (): void => {
      if (cancelled) return
      const cy = cyRef.current
      if (!cy || cy.nodes().length < expectedNodeCount) {
        raf = requestAnimationFrame(tryLayout)
        return
      }
      runLayout()
    }
    raf = requestAnimationFrame(tryLayout)
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
    }
  }, [state, elements, runLayout])

  // The cy mount callback (passed to <CytoscapeComponent>) runs as soon
  // as cytoscape initializes, which is *after* useEffect has fired the
  // first time on a fresh render. We stash the latest indexes in a ref
  // so the click handlers can read fresh data without re-binding.
  const indexesRef = useRef(indexes)
  useEffect(() => {
    indexesRef.current = indexes
  }, [indexes])

  const handleCyMount = useCallback((cy: cytoscape.Core) => {
    cyRef.current = cy
    ;(window as unknown as { cy: cytoscape.Core }).cy = cy

    cy.on('tap', 'node', (evt) => {
      const ele = evt.target
      const id = ele.id()
      const idx = indexesRef.current
      if (ele.data('isCommunity')) {
        const cid = communityIdFromCytoscapeId(id)
        if (cid !== null) {
          const community = idx.communityById.get(cid)
          if (community) setSelection({ kind: 'community', community })
        }
        return
      }
      const node = idx.nodeById.get(id)
      if (node) setSelection({ kind: 'node', node })
    })

    cy.on('tap', 'edge', (evt) => {
      const ele = evt.target
      const src = String(ele.data('source'))
      const dst = String(ele.data('target'))
      const rt = String(ele.data('relType') ?? '')
      const idx = indexesRef.current
      const candidates = idx.edgesByPair.get(`${src}\x1f${dst}`) ?? []
      const match =
        candidates.find((e) => (e.rel_type ?? '') === rt) ?? candidates[0] ?? null
      if (match) setSelection({ kind: 'edge', edge: match })
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) setSelection(null)
    })
  }, [])

  return (
    <main
      className="flex h-full w-full flex-col"
      data-testid="kg-page"
      data-table-id="er"
    >
      <header className="border-b border-border p-4">
        <h1 className="text-2xl font-bold">
          Knowledge Graph <span className="font-mono text-sm text-muted-foreground">/ er</span>
        </h1>
        {state.status === 'ready' && (
          <p className="mt-1 text-sm text-muted-foreground">
            <span data-testid="kg-stats">
              {state.payload.node_count.toLocaleString()} nodes
              {state.payload.filtered_node_count !== null
                ? ` (filter: ${state.payload.filtered_node_count.toLocaleString()} / total: ${state.payload.total_node_count.toLocaleString()})`
                : state.payload.total_node_count > state.payload.node_count
                  ? ` (of ${state.payload.total_node_count.toLocaleString()})`
                  : ''}{' · '}
              {state.payload.edge_count.toLocaleString()} edges{' · '}
              {state.payload.community_count.toLocaleString()} communities{' · '}
              seeds by <span className="font-mono">{state.payload.seed_metric}</span>, depth=
              {state.payload.max_depth}, min-deg={state.payload.min_degree}
              {(state.payload.filtered_days || state.payload.filtered_project) && (
                <span className="ml-2 rounded bg-foreground/10 px-2 py-0.5 font-mono text-[10px]">
                  filter:
                  {state.payload.filtered_days
                    ? ` days=${state.payload.filtered_days}`
                    : ''}
                  {state.payload.filtered_project
                    ? ` project=${state.payload.filtered_project}`
                    : ''}
                </span>
              )}
            </span>
          </p>
        )}
      </header>

      <section className="flex min-h-0 flex-1">
        <div className="relative flex-1">
          {state.status === 'loading' && (
            <div data-testid="kg-loading" className="p-8">
              Loading knowledge graph…
            </div>
          )}
          {state.status === 'error' && (
            <div
              data-testid="kg-error"
              className="m-8 rounded border border-destructive/40 bg-destructive/10 p-4"
            >
              <p className="font-semibold text-destructive">Failed to load knowledge graph</p>
              <pre className="mt-2 whitespace-pre-wrap text-sm text-destructive/80">
                {state.message}
              </pre>
              <p className="mt-3 text-sm text-muted-foreground">
                The KG pipeline runs incrementally on every server start. If this is your first
                run, NER/RE on the full session corpus may still be in progress — watch the
                backend logs for phase-7 progress messages, then refresh.
              </p>
            </div>
          )}
          {state.status === 'ready' && (
            <div className="absolute inset-0">
              <CytoscapeComponent
                elements={elements}
                stylesheet={stylesheet}
                cy={handleCyMount}
                style={{ width: '100%', height: '100%' }}
                wheelSensitivity={0.2}
              />
              <div
                data-testid="kg-canvas-ready"
                data-node-count={state.payload.node_count}
                data-edge-count={state.payload.edge_count}
                data-community-count={state.payload.community_count}
                className="hidden"
              />
            </div>
          )}
        </div>

        <KnowledgeGraphControls
          topN={topN}
          seedMetric={seedMetric}
          maxDepth={maxDepth}
          minDegree={minDegree}
          layoutEngine={layoutEngine}
          sizeMode={sizeMode}
          fcoseConfig={fcoseConfigText}
          fcoseConfigError={fcoseConfigError}
          onTopNChange={(v) => updateParam('topN', String(v), String(DEFAULT_TOP_N))}
          onSeedMetricChange={(v) => updateParam('seedMetric', v, DEFAULT_SEED_METRIC)}
          onMaxDepthChange={(v) => updateParam('maxDepth', String(v), String(DEFAULT_MAX_DEPTH))}
          onMinDegreeChange={(v) =>
            updateParam('minDegree', String(v), String(DEFAULT_MIN_DEGREE))
          }
          onLayoutChange={(v) => updateParam('layout', v, DEFAULT_LAYOUT)}
          onSizeModeChange={(v) => updateParam('sizeMode', v, DEFAULT_SIZE_MODE)}
          onFcoseConfigChange={setFcoseConfigText}
          onFcoseConfigReset={() => setFcoseConfigText(DEFAULT_FCOSE_CONFIG_JSON)}
          onApplyLayout={runLayout}
          payload={state.status === 'ready' ? state.payload : null}
          selection={selection}
          onClearSelection={() => setSelection(null)}
        />
      </section>
    </main>
  )
}

export type { KGNode, KGEdge }
