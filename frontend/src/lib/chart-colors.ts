/**
 * Chart color constants for consistent styling across all Plotly charts
 *
 * These colors are designed to work well together and provide
 * good contrast in both light and dark modes.
 */

/** Primary color for cost-related charts (green) */
export const COST_COLOR = '#10B981'

/** Color for input tokens (purple) */
export const INPUT_TOKEN_COLOR = '#8B5CF6'

/** Color for output tokens (amber/orange) */
export const OUTPUT_TOKEN_COLOR = '#F59E0B'

/** Color for rolling average lines (red) */
export const AVERAGE_LINE_COLOR = '#DC2626'

/** Standard color palette for categorical data (models, projects, etc.) */
export const CHART_COLORS = [
  '#3B82F6', // Blue
  '#EF4444', // Red
  '#10B981', // Emerald/Green
  '#F59E0B', // Amber
  '#8B5CF6', // Violet
  '#EC4899', // Pink
] as const

/** Extended color palette for more categories */
export const EXTENDED_CHART_COLORS = [
  '#3B82F6', // Blue
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#EF4444', // Red
  '#8B5CF6', // Violet
  '#EC4899', // Pink
  '#06B6D4', // Cyan
  '#84CC16', // Lime
  '#F97316', // Orange
  '#6366F1', // Indigo
  '#14B8A6', // Teal
  '#A855F7', // Purple
  '#22C55E', // Green
  '#0EA5E9', // Sky
  '#E11D48', // Rose
  '#FACC15', // Yellow
] as const

/** Colors specifically for input tokens by model (darker/saturated) */
export const MODEL_INPUT_COLORS = [
  '#3B82F6', // Blue
  '#EF4444', // Red
  '#10B981', // Green
  '#F59E0B', // Amber
  '#8B5CF6', // Violet
  '#EC4899', // Pink
] as const

/** Colors specifically for output tokens by model (lighter/complementary) */
export const MODEL_OUTPUT_COLORS = [
  '#06B6D4', // Cyan
  '#F97316', // Orange
  '#84CC16', // Lime
  '#A78BFA', // Light Violet
  '#FB923C', // Light Orange
  '#4ADE80', // Light Green
] as const

/**
 * Get a color from the standard palette by index (cycles through if > palette length)
 *
 * @param index - The index of the item
 * @returns A color string from CHART_COLORS
 */
export function getChartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

/**
 * Get a color from the extended palette by index
 *
 * @param index - The index of the item
 * @returns A color string from EXTENDED_CHART_COLORS
 */
export function getExtendedChartColor(index: number): string {
  return EXTENDED_CHART_COLORS[index % EXTENDED_CHART_COLORS.length]
}

/**
 * Generate HSL colors evenly distributed around the color wheel
 *
 * @param count - Number of colors to generate
 * @param saturation - Saturation percentage (default: 70)
 * @param lightness - Lightness percentage (default: 50)
 * @returns Array of HSL color strings
 */
export function generateHslColors(
  count: number,
  saturation: number = 70,
  lightness: number = 50
): string[] {
  return Array.from({ length: count }, (_, i) =>
    `hsl(${(i * 360) / count}, ${saturation}%, ${lightness}%)`
  )
}

/** Event type styling for timeline charts */
export const EVENT_TYPE_STYLES: Record<string, { symbol: string; color: string; name: string }> = {
  user: { symbol: 'square', color: '#3B82F6', name: 'User' },
  assistant: { symbol: 'circle', color: '#10B981', name: 'Assistant' },
  tool_use: { symbol: 'diamond', color: '#F59E0B', name: 'Tool Use' },
  tool_result: { symbol: 'star', color: '#8B5CF6', name: 'Tool Result' },
  system: { symbol: 'hexagon', color: '#EF4444', name: 'System' },
} as const

/** Default styling for unknown event types */
export const DEFAULT_EVENT_STYLE = { symbol: 'circle', color: '#6B7280', name: 'Other' } as const

/**
 * Get the style for an event type, with fallback to default
 *
 * @param eventType - The event type string
 * @returns Style object with symbol, color, and display name
 */
export function getEventTypeStyle(eventType: string): { symbol: string; color: string; name: string } {
  return EVENT_TYPE_STYLES[eventType] || DEFAULT_EVENT_STYLE
}
