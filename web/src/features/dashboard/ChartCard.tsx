import { useEffect, useRef, useState } from 'react'

import type { FlintChartSpec } from '../../contracts/dashboard'

interface ChartCardProps {
  title: string
  spec: FlintChartSpec
  data: Record<string, unknown>[]
}

const chartTypes = { line: 'Line Chart', bar: 'Bar Chart', point: 'Scatter Plot', area: 'Area Chart' } as const
const semanticTypes = { temporal: 'Date', quantitative: 'Quantity', nominal: 'Category', ordinal: 'Category' } as const

export async function compileFlintECharts(title: string, spec: FlintChartSpec, data: Record<string, unknown>[]) {
  const { assembleECharts } = await import('flint-chart')
  const semantics = Object.fromEntries(Object.values(spec.encoding).map((encoding) => [encoding.field, semanticTypes[encoding.type]]))
  const encodings = Object.fromEntries(Object.entries(spec.encoding).map(([channel, encoding]) => [channel, { field: encoding.field }]))
  return assembleECharts({
    data: { values: data },
    semantic_types: semantics,
    chart_spec: { chartType: chartTypes[spec.mark], title, encodings, baseSize: { width: 720, height: 320 }, canvasSize: { width: 1200, height: 520 } },
    options: { addTooltips: true },
  })
}

export function ChartCard({ title, spec, data }: ChartCardProps) {
  const host = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!host.current || navigator.userAgent.includes('jsdom')) return
    let disposed = false
    let cleanup = () => undefined
    Promise.all([compileFlintECharts(title, spec, data), import('./echarts-runtime')]).then(([option, echarts]) => {
      if (disposed || !host.current) return
      const chart = echarts.init(host.current, 'dark', { renderer: 'canvas' })
      chart.setOption({ ...option, backgroundColor: 'transparent' })
      const resize = () => chart.resize()
      window.addEventListener('resize', resize)
      cleanup = () => { window.removeEventListener('resize', resize); chart.dispose() }
    }).catch((reason) => {
      if (!disposed) setError(reason instanceof Error ? reason.message : '图表编译失败')
    })
    return () => { disposed = true; cleanup() }
  }, [data, spec, title])

  if (error) return <p role="alert">{error}</p>
  return <div className="chart-host" ref={host} role="img" aria-label={`${title}图表`} />
}
