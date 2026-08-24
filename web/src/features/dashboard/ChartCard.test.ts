import { describe, expect, it } from 'vitest'

import { buildFocusedTrendOption, formatMetricValue, metricLabel } from './ChartCard'

describe('focused metric trend', () => {
  it('builds one honest series instead of mixing metrics with incompatible scales', () => {
    const option = buildFocusedTrendOption('指标趋势', {
      mark: 'line',
      encoding: { x: { field: 'date', type: 'temporal' }, y: { field: 'value', type: 'quantitative' }, color: { field: 'metric', type: 'nominal' } },
      transforms: [],
    }, [
      { date: '2026-01-01', metric: 'gmv', value: 4_000_000 },
      { date: '2026-02-01', metric: 'gmv', value: 4_200_000 },
      { date: '2026-01-01', metric: 'gross_margin_rate', value: .36 },
      { date: '2026-02-01', metric: 'gross_margin_rate', value: .31 },
    ], 'gmv') as { legend?: unknown; series?: Array<{ name?: string; data?: unknown[] }>; xAxis?: { axisLabel?: { rotate?: number } }; yAxis?: { name?: string } }

    expect(option.legend).toBeUndefined()
    expect(option.series).toHaveLength(1)
    expect(option.series?.[0]).toMatchObject({ name: 'GMV', data: [4_000_000, 4_200_000] })
    expect(option.yAxis?.name).toBe('GMV · 元')
    expect(option.xAxis?.axisLabel?.rotate).toBe(0)
  })

  it('localizes and formats known business metrics', () => {
    expect(metricLabel('gross_margin_rate')).toBe('毛利率')
    expect(formatMetricValue('gross_margin_rate', .315)).toBe('31.5%')
    expect(formatMetricValue('gmv', 4_200_000)).toBe('¥420万')
  })
})
