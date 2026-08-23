import { describe, expect, it } from 'vitest'

import { compileFlintECharts } from './ChartCard'

describe('Flint chart compilation', () => {
  it('compiles the bounded dashboard grammar into ECharts options', async () => {
    const option = await compileFlintECharts('指标趋势', {
      mark: 'line',
      encoding: { x: { field: 'date', type: 'temporal' }, y: { field: 'value', type: 'quantitative' }, color: { field: 'metric', type: 'nominal' } },
      transforms: [],
    }, [
      { date: '2026-01-01', metric: '收入', value: 10 },
      { date: '2026-02-01', metric: '收入', value: 12 },
    ]) as { series?: unknown[] }

    expect(option.series?.length).toBeGreaterThan(0)
  })
})
