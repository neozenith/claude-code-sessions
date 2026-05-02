/**
 * Typed wrappers for the /api/kg/er endpoint.
 *
 * Field names match the reference contract at
 * /Users/joshpeak/play/sqlite-vector-graph/viz/server/kg.py exactly so the
 * cytoscape page can be ported with minimal adaptation.
 */

export interface KGNode {
  id: string
  label: string
  entity_type: string | null
  community_id: number | null
  mention_count: number | null
  /** Betweenness centrality over the FULL graph, not the filtered subset. */
  node_betweenness: number | null
}

export interface KGEdge {
  source: string
  target: string
  rel_type: string | null
  weight: number | null
  /** Betweenness centrality over the FULL graph, not the filtered subset. */
  edge_betweenness: number | null
}

export interface KGCommunity {
  id: number
  label: string | null
  member_count: number
  node_ids: string[]
}

export type SeedMetric = 'degree' | 'node_betweenness' | 'edge_betweenness'

export interface KGPayload {
  table_id: string
  resolution: number
  seed_metric: SeedMetric
  max_depth: number
  min_degree: number
  node_count: number
  edge_count: number
  community_count: number
  total_node_count: number
  total_edge_count: number
  nodes: KGNode[]
  edges: KGEdge[]
  communities: KGCommunity[]
  filtered_days: number | null
  filtered_project: string | null
  filtered_node_count: number | null
}

export class KGFetchError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(`KG fetch failed (${status}): ${body}`)
    this.name = 'KGFetchError'
    this.status = status
    this.body = body
  }
}

export interface FetchKGOptions {
  resolution?: number
  topN?: number
  seedMetric?: SeedMetric
  maxDepth?: number
  minDegree?: number
  /** Restrict KG to chunks within the last N days (matches global filter). */
  days?: number | null
  /** Restrict KG to chunks belonging to a single project (matches global filter). */
  project?: string | null
}

export async function fetchKG(opts: FetchKGOptions = {}): Promise<KGPayload> {
  const params = new URLSearchParams()
  if (opts.resolution !== undefined) params.set('resolution', String(opts.resolution))
  if (opts.topN !== undefined) params.set('top_n', String(opts.topN))
  if (opts.seedMetric !== undefined) params.set('seed_metric', opts.seedMetric)
  if (opts.maxDepth !== undefined) params.set('max_depth', String(opts.maxDepth))
  if (opts.minDegree !== undefined) params.set('min_degree', String(opts.minDegree))
  if (opts.days !== undefined && opts.days !== null && opts.days > 0) {
    params.set('days', String(opts.days))
  }
  if (opts.project) params.set('project', opts.project)
  const qs = params.toString()
  const url = qs ? `/api/kg/er?${qs}` : '/api/kg/er'
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new KGFetchError(response.status, body)
  }
  return (await response.json()) as KGPayload
}
