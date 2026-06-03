import { describe, expect, it } from 'vitest'

import { buildHeatmapMatrices, sortClaims } from './claims'
import type { Claim, CoveragePivot } from './api-client'

const claim = (text: string, count: number): Claim => ({ claim: text, count, sessions: [] })

describe('sortClaims', () => {
  const claims = [claim('banana', 1), claim('apple', 9), claim('cherry', 4)]

  it('sorts by count descending', () => {
    const out = sortClaims(claims, { field: 'count', dir: 'desc' }).map((c) => c.count)
    expect(out).toEqual([9, 4, 1])
  })

  it('sorts by count ascending', () => {
    const out = sortClaims(claims, { field: 'count', dir: 'asc' }).map((c) => c.count)
    expect(out).toEqual([1, 4, 9])
  })

  it('sorts by claim text ascending/descending', () => {
    expect(sortClaims(claims, { field: 'claim', dir: 'asc' }).map((c) => c.claim)).toEqual([
      'apple',
      'banana',
      'cherry',
    ])
    expect(sortClaims(claims, { field: 'claim', dir: 'desc' }).map((c) => c.claim)).toEqual([
      'cherry',
      'banana',
      'apple',
    ])
  })

  it('does not mutate the input array', () => {
    const original = [...claims]
    sortClaims(claims, { field: 'count', dir: 'asc' })
    expect(claims).toEqual(original)
  })
})

describe('buildHeatmapMatrices', () => {
  const pivot: CoveragePivot = {
    model: 'qwen3',
    grain: 'month',
    scopes: ['clients/acme', 'clients/beta'],
    buckets: ['2026-04', '2026-05'],
    cells: [
      { scope_path: 'clients/acme', bucket: '2026-05', sessions: 4, claims: 12, failures: 0, status: 'done' },
      { scope_path: 'clients/beta', bucket: '2026-04', sessions: 2, claims: 0, failures: 1, status: 'failed' },
    ],
  }

  it('densifies sparse cells into a row-major z matrix (pending=null, status code otherwise)', () => {
    const { z } = buildHeatmapMatrices(pivot)
    // rows = scopes, cols = buckets. done=2, failed=1, absent=null.
    expect(z).toEqual([
      [null, 2], // acme: 2026-04 absent, 2026-05 done
      [1, null], // beta: 2026-04 failed, 2026-05 absent
    ])
  })

  it('builds hovertext only for present cells', () => {
    const { text } = buildHeatmapMatrices(pivot)
    expect(text[0]![0]).toBe('')
    expect(text[0]![1]).toContain('clients/acme')
    expect(text[0]![1]).toContain('4 sessions · 12 claims · 0 failures')
    expect(text[1]![0]).toContain('status: failed')
  })

  it('ignores cells whose scope/bucket is not in the axis arrays', () => {
    const { z } = buildHeatmapMatrices({
      ...pivot,
      cells: [
        { scope_path: 'unknown/scope', bucket: '2026-05', sessions: 1, claims: 1, failures: 0, status: 'done' },
      ],
    })
    expect(z).toEqual([
      [null, null],
      [null, null],
    ])
  })
})
