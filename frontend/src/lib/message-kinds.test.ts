import { describe, it, expect } from 'vitest'

import { matchesKind, MSG_KIND_OPTIONS } from './message-kinds'

describe('MSG_KIND_OPTIONS', () => {
  const BASE = [
    'human',
    'task_notification',
    'tool_result',
    'user_text',
    'meta',
    'assistant_text',
    'thinking',
    'tool_use',
    'other',
  ]

  it('has 19 entries including subagent kinds', () => {
    expect(MSG_KIND_OPTIONS).toHaveLength(19)
    expect(MSG_KIND_OPTIONS[0].value).toBe('')

    const nonEmpty = MSG_KIND_OPTIONS.slice(1).map((o) => o.value)
    const expected = [...BASE, ...BASE.map((b) => `subagent-${b}`)]
    expect(new Set(nonEmpty)).toEqual(new Set(expected))
    expect(nonEmpty).toContain('subagent-thinking')
    expect(nonEmpty).toContain('subagent-human')
  })
})

describe('matchesKind (exact full-kind value, no scope composition)', () => {
  const kinds = ['human', 'tool_use', 'subagent-human', 'subagent-tool_use']

  it('matches only the exact kind, never the base-equivalent subagent kind', () => {
    expect(kinds.filter((k) => matchesKind(k, 'tool_use'))).toEqual(['tool_use'])
  })

  it('matches the full subagent kind exactly', () => {
    expect(kinds.filter((k) => matchesKind(k, 'subagent-tool_use'))).toEqual(['subagent-tool_use'])
  })

  it('an empty filter matches everything', () => {
    expect(kinds.filter((k) => matchesKind(k, ''))).toEqual(kinds)
  })
})
