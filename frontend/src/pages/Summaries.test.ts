import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { createElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import { SummariesView } from './Summaries'
import type { SummaryResponse, SummaryVariant } from '../lib/api-client'

afterEach(cleanup)

function LocationProbe() {
  const loc = useLocation()
  return createElement('div', { 'data-testid': 'loc' }, loc.search)
}

const currentParam = (key: string): string | null =>
  new URLSearchParams(screen.getByTestId('loc').textContent ?? '').get(key)

const summarised = (task: string, pat: string, dec: string): SummaryResponse => ({
  status: 'summarised',
  lenses: { task_summary: task, patterns: pat, decisions_values: dec },
})

const VARIANTS: SummaryVariant[] = [
  { strategy: 'strict', model: 'model-a' },
  { strategy: 'reground', model: 'model-b' },
]

function renderView(
  props: Partial<Parameters<typeof SummariesView>[0]>,
  entries: string[] = ['/summaries'],
) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: entries },
      createElement(SummariesView, {
        summary: null,
        childScopes: [],
        variants: [],
        loading: false,
        ...props,
      }),
      createElement(LocationProbe),
    ),
  )
}

describe('SummariesView — not_summarised empty state (T8.6)', () => {
  it('renders the empty state and no lens cards when not summarised', () => {
    renderView({ summary: { status: 'not_summarised' } })
    expect(screen.getByTestId('summary-empty')).toBeTruthy()
    expect(screen.queryByTestId('lens-task')).toBeNull()
    expect(screen.queryByTestId('lens-patterns')).toBeNull()
    expect(screen.queryByTestId('lens-decisions')).toBeNull()
  })

  it('renders the three lens cards (and no empty state) when summarised', () => {
    renderView({ summary: summarised('T1', 'P1', 'D1') })
    expect(screen.getByTestId('lens-task').textContent).toBe('T1')
    expect(screen.getByTestId('lens-patterns').textContent).toBe('P1')
    expect(screen.getByTestId('lens-decisions').textContent).toBe('D1')
    expect(screen.queryByTestId('summary-empty')).toBeNull()
  })
})

describe('SummariesView — strategy/model variant selection (T8.5)', () => {
  it('shows the given variant prose and the selectors write ?strategy/?model', () => {
    renderView(
      { summary: summarised('ALPHA_task', 'ap', 'ad'), variants: VARIANTS },
      ['/summaries?strategy=strict&model=model-a'],
    )
    expect(screen.getByTestId('lens-task').textContent).toBe('ALPHA_task')

    fireEvent.change(screen.getByTestId('model-select'), { target: { value: 'model-b' } })
    expect(currentParam('model')).toBe('model-b')

    fireEvent.change(screen.getByTestId('strategy-select'), { target: { value: 'reground' } })
    expect(currentParam('strategy')).toBe('reground')
  })

  it('swaps the displayed prose to whichever variant summary it is given', () => {
    renderView({ summary: summarised('BETA_task', 'bp', 'bd'), variants: VARIANTS })
    expect(screen.getByTestId('lens-task').textContent).toBe('BETA_task')
  })
})
