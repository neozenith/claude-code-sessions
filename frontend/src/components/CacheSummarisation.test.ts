import { render, screen, cleanup, fireEvent, within } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import CacheSummarisation from './CacheSummarisation'
import type { Coverage, CoverageProject } from '../lib/api-client'

afterEach(cleanup)

const proj = (over: Partial<CoverageProject>): CoverageProject => ({
  project_id: 'pid',
  scope_path: 'play/pid',
  domain: 'play',
  total: 10,
  summarised: 5,
  failed: 0,
  pending: 5,
  pct_complete: 50,
  ...over,
})

const coverage = (projects: CoverageProject[]): Coverage => ({
  model: 'M',
  overall: { total: 0, summarised: 0, failed: 0, pending: 0, pct_complete: 0 },
  projects,
})

const renderC = (cov: Coverage | null) =>
  render(createElement(CacheSummarisation, { coverage: cov }))

const projectCol = (): string[] =>
  Array.from(
    within(screen.getByTestId('coverage-project-table')).getAllByRole('row')
  )
    .slice(1) // drop header
    .map((r) => r.querySelectorAll('td')[1]?.textContent ?? '')

describe('CacheSummarisation', () => {
  it('renders a Domain column and the domain value per row', () => {
    renderC(coverage([proj({ project_id: 'a', domain: 'work' })]))
    expect(screen.getByTestId('sort-col-domain')).toBeTruthy()
    const firstRow = within(screen.getByTestId('coverage-project-table')).getAllByRole('row')[1]
    expect(firstRow.querySelectorAll('td')[0]?.textContent).toBe('work')
  })

  it('renders exactly the rows it is given (scoping is done upstream by the page filter)', () => {
    renderC(
      coverage([
        proj({ project_id: 'play1', domain: 'play' }),
        proj({ project_id: 'work1', domain: 'work' }),
      ])
    )
    expect([...projectCol()].sort()).toEqual(['play1', 'work1'])
  })

  it('sorts by a column and toggles direction on re-click', () => {
    renderC(
      coverage([
        proj({ project_id: 'low', pending: 1 }),
        proj({ project_id: 'high', pending: 9 }),
      ])
    )
    // default sort is pending desc → high first
    expect(projectCol()).toEqual(['high', 'low'])
    fireEvent.click(screen.getByTestId('sort-col-pending')) // toggle to asc
    expect(projectCol()).toEqual(['low', 'high'])
  })

  it('returns null when coverage is absent', () => {
    const { container } = renderC(null)
    expect(container.querySelector('[data-testid="cache-summarisation"]')).toBeNull()
  })
})
