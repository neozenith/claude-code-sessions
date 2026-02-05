/**
 * Unit tests for chart-colors.ts
 */
import { describe, it, expect } from 'vitest'
import {
  CHART_COLORS,
  EXTENDED_CHART_COLORS,
  getChartColor,
  getExtendedChartColor,
  generateHslColors,
  getEventTypeStyle,
  EVENT_TYPE_STYLES,
  DEFAULT_EVENT_STYLE,
} from './chart-colors'

describe('CHART_COLORS', () => {
  it('has 6 colors', () => {
    expect(CHART_COLORS).toHaveLength(6)
  })

  it('contains valid hex colors', () => {
    CHART_COLORS.forEach((color) => {
      expect(color).toMatch(/^#[0-9A-F]{6}$/i)
    })
  })
})

describe('EXTENDED_CHART_COLORS', () => {
  it('has 16 colors', () => {
    expect(EXTENDED_CHART_COLORS).toHaveLength(16)
  })

  it('contains valid hex colors', () => {
    EXTENDED_CHART_COLORS.forEach((color) => {
      expect(color).toMatch(/^#[0-9A-F]{6}$/i)
    })
  })
})

describe('getChartColor', () => {
  it('returns colors from CHART_COLORS by index', () => {
    expect(getChartColor(0)).toBe(CHART_COLORS[0])
    expect(getChartColor(1)).toBe(CHART_COLORS[1])
    expect(getChartColor(5)).toBe(CHART_COLORS[5])
  })

  it('cycles through colors for indices beyond array length', () => {
    expect(getChartColor(6)).toBe(CHART_COLORS[0])
    expect(getChartColor(7)).toBe(CHART_COLORS[1])
    expect(getChartColor(12)).toBe(CHART_COLORS[0])
  })
})

describe('getExtendedChartColor', () => {
  it('returns colors from EXTENDED_CHART_COLORS by index', () => {
    expect(getExtendedChartColor(0)).toBe(EXTENDED_CHART_COLORS[0])
    expect(getExtendedChartColor(15)).toBe(EXTENDED_CHART_COLORS[15])
  })

  it('cycles through colors for indices beyond array length', () => {
    expect(getExtendedChartColor(16)).toBe(EXTENDED_CHART_COLORS[0])
    expect(getExtendedChartColor(17)).toBe(EXTENDED_CHART_COLORS[1])
  })
})

describe('generateHslColors', () => {
  it('generates the requested number of colors', () => {
    expect(generateHslColors(3)).toHaveLength(3)
    expect(generateHslColors(10)).toHaveLength(10)
    expect(generateHslColors(1)).toHaveLength(1)
  })

  it('generates valid HSL color strings', () => {
    const colors = generateHslColors(5)
    colors.forEach((color) => {
      expect(color).toMatch(/^hsl\(\d+, \d+%, \d+%\)$/)
    })
  })

  it('distributes hues evenly around the color wheel', () => {
    const colors = generateHslColors(4)
    expect(colors[0]).toBe('hsl(0, 70%, 50%)')
    expect(colors[1]).toBe('hsl(90, 70%, 50%)')
    expect(colors[2]).toBe('hsl(180, 70%, 50%)')
    expect(colors[3]).toBe('hsl(270, 70%, 50%)')
  })

  it('uses custom saturation and lightness', () => {
    const colors = generateHslColors(2, 50, 60)
    expect(colors[0]).toBe('hsl(0, 50%, 60%)')
    expect(colors[1]).toBe('hsl(180, 50%, 60%)')
  })
})

describe('EVENT_TYPE_STYLES', () => {
  it('has styles for common event types', () => {
    expect(EVENT_TYPE_STYLES).toHaveProperty('user')
    expect(EVENT_TYPE_STYLES).toHaveProperty('assistant')
    expect(EVENT_TYPE_STYLES).toHaveProperty('tool_use')
    expect(EVENT_TYPE_STYLES).toHaveProperty('tool_result')
    expect(EVENT_TYPE_STYLES).toHaveProperty('system')
  })

  it('each style has required properties', () => {
    Object.values(EVENT_TYPE_STYLES).forEach((style) => {
      expect(style).toHaveProperty('symbol')
      expect(style).toHaveProperty('color')
      expect(style).toHaveProperty('name')
      expect(style.color).toMatch(/^#[0-9A-F]{6}$/i)
    })
  })
})

describe('getEventTypeStyle', () => {
  it('returns the correct style for known event types', () => {
    expect(getEventTypeStyle('user')).toBe(EVENT_TYPE_STYLES.user)
    expect(getEventTypeStyle('assistant')).toBe(EVENT_TYPE_STYLES.assistant)
    expect(getEventTypeStyle('tool_use')).toBe(EVENT_TYPE_STYLES.tool_use)
  })

  it('returns DEFAULT_EVENT_STYLE for unknown event types', () => {
    expect(getEventTypeStyle('unknown')).toBe(DEFAULT_EVENT_STYLE)
    expect(getEventTypeStyle('')).toBe(DEFAULT_EVENT_STYLE)
    expect(getEventTypeStyle('some_new_type')).toBe(DEFAULT_EVENT_STYLE)
  })
})
