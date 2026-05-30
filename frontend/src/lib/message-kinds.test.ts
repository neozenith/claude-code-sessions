import { describe, it, expect } from 'vitest'

import { matchesKindFilter } from './message-kinds'

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
