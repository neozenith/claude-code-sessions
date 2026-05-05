/**
 * Constants and types for the Knowledge Graph controls panel.
 *
 * Split out from ``KnowledgeGraphControls.tsx`` so that file exports
 * only React components — required by Vite Fast Refresh's
 * ``react-refresh/only-export-components`` rule. Mixing constants and
 * components in one module breaks HMR for every consumer of the
 * constants.
 */

import type { KGCommunity, KGEdge, KGNode, SeedMetric } from '@/lib/kg-client'

export type LayoutEngine = 'fcose' | 'elk' | 'grid'
export type SizeMode = 'uniform' | 'degree' | 'betweenness'

export type Selection =
  | { kind: 'node'; node: KGNode }
  | { kind: 'edge'; edge: KGEdge }
  | { kind: 'community'; community: KGCommunity }

export const DEFAULT_TOP_N = 2
export const DEFAULT_SEED_METRIC: SeedMetric = 'edge_betweenness'
export const DEFAULT_MAX_DEPTH = 1
export const DEFAULT_MIN_DEGREE = 5
export const DEFAULT_LAYOUT: LayoutEngine = 'fcose'
export const DEFAULT_SIZE_MODE: SizeMode = 'degree'

export const DEFAULT_FCOSE_CONFIG = {
  quality: 'default',
  randomize: true,
  animate: false,
  fit: true,
  padding: 30,
  nodeRepulsion: 4500,
  idealEdgeLength: 50,
  edgeElasticity: 0.45,
  nestingFactor: 0.1,
  gravity: 0.25,
  gravityRangeCompound: 1.5,
  gravityCompound: 1.0,
  gravityRange: 3.8,
  initialEnergyOnIncremental: 0.3,
  tile: true,
  numIter: 2500,
}

export const DEFAULT_FCOSE_CONFIG_JSON = JSON.stringify(DEFAULT_FCOSE_CONFIG, null, 2)
