/**
 * Unit tests for formatters.ts
 */
import { describe, it, expect } from 'vitest'
import {
  formatNumber,
  formatProjectName,
  formatCurrency,
  formatWithCommas,
  formatTokensMillions,
  truncate,
  formatModelName,
  formatSessionId,
} from './formatters'

describe('formatNumber', () => {
  it('formats millions with M suffix', () => {
    expect(formatNumber(1_000_000)).toBe('1M')
    expect(formatNumber(1_234_567)).toBe('1.2M')
    expect(formatNumber(12_345_678)).toBe('12.3M')
  })

  it('removes trailing .0 from millions', () => {
    expect(formatNumber(2_000_000)).toBe('2M')
    expect(formatNumber(10_000_000)).toBe('10M')
  })

  it('formats thousands with k suffix', () => {
    expect(formatNumber(1_000)).toBe('1k')
    expect(formatNumber(12_345)).toBe('12k')
    expect(formatNumber(999_999)).toBe('1000k')
  })

  it('returns small numbers as-is', () => {
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(1)).toBe('1')
    expect(formatNumber(999)).toBe('999')
  })
})

describe('formatProjectName', () => {
  it('removes user path prefix and converts dashes to slashes', () => {
    expect(formatProjectName('-Users-joshpeak-code-myproject')).toBe('code/myproject')
    expect(formatProjectName('-Users-joshpeak-work-client-app')).toBe('work/client/app')
  })

  it('handles names without user prefix', () => {
    expect(formatProjectName('simple-project')).toBe('simple/project')
    expect(formatProjectName('my-app')).toBe('my/app')
  })

  it('handles single-word names', () => {
    expect(formatProjectName('project')).toBe('project')
  })
})

describe('formatCurrency', () => {
  it('formats as USD with 2 decimals by default', () => {
    expect(formatCurrency(123.456)).toBe('$123.46')
    expect(formatCurrency(0)).toBe('$0.00')
    expect(formatCurrency(1000.5)).toBe('$1000.50')
  })

  it('respects custom decimal places', () => {
    expect(formatCurrency(123.456, 0)).toBe('$123')
    expect(formatCurrency(123.456, 3)).toBe('$123.456')
    expect(formatCurrency(123.456, 1)).toBe('$123.5')
  })
})

describe('formatWithCommas', () => {
  it('adds thousand separators', () => {
    expect(formatWithCommas(1234567)).toBe('1,234,567')
    expect(formatWithCommas(1000)).toBe('1,000')
    expect(formatWithCommas(999)).toBe('999')
    expect(formatWithCommas(0)).toBe('0')
  })
})

describe('formatTokensMillions', () => {
  it('formats tokens as millions with 2 decimals', () => {
    expect(formatTokensMillions(1_000_000)).toBe('1.00M')
    expect(formatTokensMillions(1_234_567)).toBe('1.23M')
    expect(formatTokensMillions(500_000)).toBe('0.50M')
  })
})

describe('truncate', () => {
  it('truncates long strings with ellipsis', () => {
    expect(truncate('Hello World', 8)).toBe('Hello...')
    expect(truncate('This is a very long string', 10)).toBe('This is...')
  })

  it('returns short strings unchanged', () => {
    expect(truncate('Hi', 8)).toBe('Hi')
    expect(truncate('Exactly8', 8)).toBe('Exactly8')
  })

  it('handles edge cases', () => {
    expect(truncate('', 5)).toBe('')
    expect(truncate('abc', 3)).toBe('abc')
  })
})

describe('formatModelName', () => {
  it('removes claude- prefix', () => {
    expect(formatModelName('claude-sonnet-4-5-20250929')).toBe('sonnet-4-5-20250929')
    expect(formatModelName('claude-opus-4-20250515')).toBe('opus-4-20250515')
    expect(formatModelName('claude-haiku-3')).toBe('haiku-3')
  })

  it('returns unchanged if no claude- prefix', () => {
    expect(formatModelName('gpt-4')).toBe('gpt-4')
    expect(formatModelName('some-model')).toBe('some-model')
  })
})

describe('formatSessionId', () => {
  it('truncates long session IDs', () => {
    // Default maxLength is 16, so we keep 16 chars + "..."
    expect(formatSessionId('abc123def456ghi789jkl')).toBe('abc123def456ghi7...')
    expect(formatSessionId('verylongsessionid12345')).toBe('verylongsessioni...')
  })

  it('returns short session IDs unchanged', () => {
    expect(formatSessionId('short')).toBe('short')
    expect(formatSessionId('exactly16chars!!')).toBe('exactly16chars!!')
  })

  it('respects custom maxLength', () => {
    expect(formatSessionId('abcdefghij', 5)).toBe('abcde...')
    expect(formatSessionId('abc', 5)).toBe('abc')
  })
})
