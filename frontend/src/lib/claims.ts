import type { Claim, ClusterNode, CoverageCell, CoveragePivot } from '@/lib/api-client'

/**
 * Pure data helpers for the Claims Explorer (CR5).
 *
 * Lives outside the page/component modules so the page files stay
 * component-only (react-refresh/only-export-components) while these
 * Plotly-free, DOM-free functions remain independently unit-testable.
 */

/** A lens-local sort spec: which field, which direction. Default is count desc. */
export type SortField = 'count' | 'claim'
export type SortDir = 'asc' | 'desc'
export interface SortSpec {
  field: SortField
  dir: SortDir
}
export const DEFAULT_SORT: SortSpec = { field: 'count', dir: 'desc' }

/** Pure client-side sort of the already-fetched claims (count or claim text). */
export const sortClaims = (claims: Claim[], sort: SortSpec): Claim[] => {
  const sign = sort.dir === 'asc' ? 1 : -1
  return [...claims].sort((a, b) => {
    if (sort.field === 'count') return sign * (a.count - b.count)
    return sign * a.claim.localeCompare(b.claim)
  })
}

/** Sort a lens's top-level cluster nodes (count = salience, or by cluster name).
 * The `claim` field sorts nodes by their `name` (the cluster's common-thread label). */
export const sortNodes = (nodes: ClusterNode[], sort: SortSpec): ClusterNode[] => {
  const sign = sort.dir === 'asc' ? 1 : -1
  return [...nodes].sort((a, b) => {
    if (sort.field === 'count') return sign * (a.count - b.count)
    return sign * a.name.localeCompare(b.name)
  })
}

/** Numeric encoding of the tri-state status for the z (color) axis. */
const STATUS_Z: Record<CoverageCell['status'], number> = {
  pending: 0,
  failed: 1,
  done: 2,
}

export interface HeatmapMatrices {
  /** z[scopeIdx][bucketIdx] — status code, null for an absent cell. */
  z: (number | null)[][]
  /** hovertext[scopeIdx][bucketIdx] — human-readable cell tooltip. */
  text: string[][]
}

/** Densify the sparse pivot cells into row-major z + hovertext matrices.
 *
 * Rows follow `pivot.scopes` (y), columns follow `pivot.buckets` (x). An
 * absent (scope, bucket) pair is `null` in z (rendered transparent) with an
 * empty hovertext. Pure — no Plotly, no DOM. */
export const buildHeatmapMatrices = (pivot: CoveragePivot): HeatmapMatrices => {
  const bucketIndex = new Map(pivot.buckets.map((b, i) => [b, i]))
  const scopeIndex = new Map(pivot.scopes.map((s, i) => [s, i]))

  const z: (number | null)[][] = pivot.scopes.map(() => pivot.buckets.map(() => null))
  const text: string[][] = pivot.scopes.map(() => pivot.buckets.map(() => ''))

  pivot.cells.forEach((cell) => {
    const si = scopeIndex.get(cell.scope_path)
    const bi = bucketIndex.get(cell.bucket)
    if (si === undefined || bi === undefined) return
    z[si]![bi] = STATUS_Z[cell.status]
    text[si]![bi] =
      `${cell.scope_path || '(root)'} · ${cell.bucket}<br>` +
      `status: ${cell.status}<br>` +
      `${cell.sessions} sessions · ${cell.claims} claims · ${cell.failures} failures`
  })

  return { z, text }
}
