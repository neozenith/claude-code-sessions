import { describe, it, expect } from 'vitest'

import { matchesKindFilter, MSG_KIND_OPTIONS } from './message-kinds'

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

describe('subagent scope composes with kind filter', () => {
  // A small mix of main-thread and subagent kinds.
  const kinds = ['human', 'tool_use', 'subagent-human', 'subagent-tool_use']

  it('msg=tool_use matches both main and subagent tool calls (prefix-agnostic)', () => {
    expect(kinds.filter((k) => matchesKindFilter(k, 'tool_use', 'all'))).toEqual([
      'tool_use',
      'subagent-tool_use',
    ])
  })

  it('scope=subagent narrows to subagent-prefixed kinds only', () => {
    expect(kinds.filter((k) => matchesKindFilter(k, '', 'subagent'))).toEqual([
      'subagent-human',
      'subagent-tool_use',
    ])
  })

  it('scope=main excludes subagent kinds', () => {
    expect(kinds.filter((k) => matchesKindFilter(k, '', 'main'))).toEqual(['human', 'tool_use'])
  })

  it('msg and scope compose (subagent tool calls only)', () => {
    expect(kinds.filter((k) => matchesKindFilter(k, 'tool_use', 'subagent'))).toEqual([
      'subagent-tool_use',
    ])
  })

  it('no filter (msg="" scope="all") matches everything', () => {
    expect(kinds.filter((k) => matchesKindFilter(k, '', 'all'))).toEqual(kinds)
  })
})
