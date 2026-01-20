import { useMemo } from 'react'
import { useTheme } from '@/contexts/ThemeContext'
import type { Layout } from 'plotly.js'

/**
 * Theme-aware Plotly layout configuration.
 * Provides colors that adapt to light/dark mode.
 */
export interface PlotlyThemeColors {
  /** Text color for labels, titles, etc. */
  text: string
  /** Secondary/muted text color */
  textMuted: string
  /** Grid line color */
  gridColor: string
  /** Background color for plot area */
  plotBg: string
  /** Background color for paper (outside plot area) */
  paperBg: string
  /** Border/line color */
  borderColor: string
}

/**
 * Hook that provides theme-aware colors and layout config for Plotly charts.
 *
 * Usage:
 * ```tsx
 * const { colors, themedLayout } = usePlotlyTheme()
 *
 * <Plot
 *   data={...}
 *   layout={{
 *     ...themedLayout,
 *     xaxis: { ...themedLayout.xaxis, title: 'Date' },
 *   }}
 * />
 * ```
 */
export function usePlotlyTheme() {
  const { resolvedTheme } = useTheme()

  const colors: PlotlyThemeColors = useMemo(() => {
    if (resolvedTheme === 'dark') {
      return {
        text: '#e5e7eb', // gray-200
        textMuted: '#9ca3af', // gray-400
        gridColor: 'rgba(75, 85, 99, 0.5)', // gray-600 with opacity
        plotBg: 'transparent',
        paperBg: 'transparent',
        borderColor: 'rgba(75, 85, 99, 0.5)',
      }
    }
    return {
      text: '#1f2937', // gray-800
      textMuted: '#6b7280', // gray-500
      gridColor: 'rgba(156, 163, 175, 0.3)', // gray-400 with opacity
      plotBg: 'transparent',
      paperBg: 'transparent',
      borderColor: 'rgba(156, 163, 175, 0.3)',
    }
  }, [resolvedTheme])

  /**
   * Base themed layout that can be spread into Plotly layout prop.
   * Includes common axis styling that adapts to theme.
   */
  const themedLayout: Partial<Layout> = useMemo(
    () => ({
      paper_bgcolor: colors.paperBg,
      plot_bgcolor: colors.plotBg,
      font: {
        color: colors.text,
      },
      xaxis: {
        color: colors.text,
        gridcolor: colors.gridColor,
        linecolor: colors.borderColor,
        zerolinecolor: colors.borderColor,
      },
      yaxis: {
        color: colors.text,
        gridcolor: colors.gridColor,
        linecolor: colors.borderColor,
        zerolinecolor: colors.borderColor,
      },
      legend: {
        font: { color: colors.text },
      },
      coloraxis: {
        colorbar: {
          tickfont: { color: colors.text },
          titlefont: { color: colors.text },
        },
      },
    }),
    [colors]
  )

  /**
   * Create a deep merged layout that preserves nested axis properties.
   * Use this when you need to add additional axis configuration.
   */
  const mergeLayout = useMemo(
    () =>
      (customLayout: Partial<Layout>): Partial<Layout> => {
        return {
          ...themedLayout,
          ...customLayout,
          xaxis: {
            ...themedLayout.xaxis,
            ...(customLayout.xaxis as Record<string, unknown>),
          },
          yaxis: {
            ...themedLayout.yaxis,
            ...(customLayout.yaxis as Record<string, unknown>),
          },
          legend: {
            ...themedLayout.legend,
            ...(customLayout.legend as Record<string, unknown>),
          },
        }
      },
    [themedLayout]
  )

  return {
    colors,
    themedLayout,
    mergeLayout,
    isDark: resolvedTheme === 'dark',
  }
}
