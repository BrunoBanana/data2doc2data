import { useEffect, useMemo, useRef, useState } from 'react'

import type { FlintChartSpec } from '../../contracts/dashboard'

interface ChartCardProps {
  title: string
  spec: FlintChartSpec
  data: Record<string, unknown>[]
}

const chartTypes = { line: 'Line Chart', bar: 'Bar Chart', point: 'Scatter Plot', area: 'Area Chart' } as const
const semanticTypes = { temporal: 'Date', quantitative: 'Quantity', nominal: 'Category', ordinal: 'Category' } as const
const metricLabels: Record<string, string> = {
  gmv: 'GMV', orders: '订单量', conversion_rate: '转化率', aov: '客单价', gross_margin_rate: '毛利率',
  refund_rate: '退款率', return_rate: '退货率', late_delivery_rate: '延迟交付率', stockout_rate: '缺货率',
  repeat_purchase_rate: '复购率', mrr: 'MRR', trial_signups: '试用注册量', activation_rate: '激活率',
  retention_8w: '8 周留存率', churn_rate: '流失率', expansion_revenue: '扩展收入', cac: '获客成本',
  support_backlog: '支持工单积压',
}
const preferredMetrics = ['gmv', 'mrr', 'orders', 'trial_signups', 'gross_margin_rate', 'retention_8w']

export function metricLabel(metric: string): string {
  return metricLabels[metric] ?? metric.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function metricKind(metric: string): 'rate' | 'currency' | 'number' {
  if (/(?:rate|ratio|retention|conversion|churn|margin|refund|return|stockout|repeat|activation)/i.test(metric)) return 'rate'
  if (/(?:gmv|mrr|revenue|aov|cac|price|cost|amount|sales)/i.test(metric)) return 'currency'
  return 'number'
}

function compactNumber(value: number): string {
  const absolute = Math.abs(value)
  if (absolute >= 100_000_000) return `${trimNumber(value / 100_000_000)}亿`
  if (absolute >= 10_000) return `${trimNumber(value / 10_000)}万`
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: absolute < 10 ? 2 : 1 }).format(value)
}

function trimNumber(value: number): string {
  return value.toFixed(Math.abs(value) >= 100 ? 0 : 1).replace(/\.0$/, '')
}

export function formatMetricValue(metric: string, value: number): string {
  if (!Number.isFinite(value)) return '—'
  const kind = metricKind(metric)
  if (kind === 'rate') return `${(value * 100).toFixed(1)}%`
  if (kind === 'currency') return `¥${compactNumber(value)}`
  return compactNumber(value)
}

function metricUnit(metric: string) {
  return metricKind(metric) === 'rate' ? '%' : metricKind(metric) === 'currency' ? '元' : '数量'
}

function shortDate(value: unknown) {
  const text = String(value)
  const match = /\d{4}-(\d{2})-(\d{2})/.exec(text)
  return match ? `${Number(match[1])}月${Number(match[2])}日` : text
}

export function buildFocusedTrendOption(title: string, spec: FlintChartSpec, data: Record<string, unknown>[], metric: string) {
  const xField = spec.encoding.x?.field ?? 'date'
  const yField = spec.encoding.y?.field ?? 'value'
  const metricField = spec.encoding.color?.field
  const points = data
    .filter((row) => !metricField || String(row[metricField]) === metric)
    .map((row) => ({ date: String(row[xField] ?? ''), value: Number(row[yField]) }))
    .filter((point) => point.date && Number.isFinite(point.value))
    .sort((left, right) => left.date.localeCompare(right.date))
  const label = metricLabel(metric)
  const values = points.map((point) => point.value)

  return {
    animationDuration: 420,
    color: ['#00a955'],
    textStyle: { color: '#151511', fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' },
    grid: { left: 76, right: 28, top: 42, bottom: 54 },
    tooltip: {
      trigger: 'axis', backgroundColor: '#050505', borderWidth: 0, textStyle: { color: '#fffdf7' },
      formatter: (raw: unknown) => {
        const item = Array.isArray(raw) ? raw[0] as { axisValue?: unknown; value?: unknown; marker?: string } : raw as { axisValue?: unknown; value?: unknown; marker?: string }
        return `${shortDate(item?.axisValue)}<br/>${item?.marker ?? ''}${label}　<strong>${formatMetricValue(metric, Number(item?.value))}</strong>`
      },
    },
    xAxis: {
      type: 'category', boundaryGap: false, data: points.map((point) => point.date),
      axisLine: { lineStyle: { color: '#151511' } }, axisTick: { show: false },
      axisLabel: { color: '#6f6b60', rotate: 0, hideOverlap: true, formatter: shortDate, margin: 16 },
    },
    yAxis: {
      type: 'value', name: `${label} · ${metricUnit(metric)}`, nameLocation: 'end', nameGap: 18,
      nameTextStyle: { color: '#6f6b60', align: 'left', fontSize: 11 }, scale: true, splitNumber: 4,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#6f6b60', formatter: (value: number) => formatMetricValue(metric, value) },
      splitLine: { lineStyle: { color: '#ded8cc', type: 'dashed' } },
    },
    series: [{
      name: label, type: spec.mark === 'area' ? 'line' : spec.mark, data: values, smooth: false,
      symbol: 'circle', showSymbol: values.length <= 32, symbolSize: 5,
      lineStyle: { width: 3, color: '#00a955' }, itemStyle: { color: '#fffdf7', borderColor: '#00a955', borderWidth: 2 },
      areaStyle: spec.mark === 'area' ? { color: 'rgba(0, 169, 85, .12)' } : undefined,
      markPoint: values.length > 2 ? {
        symbol: 'circle', symbolSize: 9, label: { show: false }, itemStyle: { color: '#f0b43f', borderColor: '#050505', borderWidth: 1 },
        data: [{ type: 'max', name: '区间高点' }, { type: 'min', name: '区间低点' }],
      } : undefined,
    }],
    aria: { enabled: true, description: `${title}：${label}，共 ${values.length} 个时间点。` },
  }
}

export async function compileFlintECharts(title: string, spec: FlintChartSpec, data: Record<string, unknown>[]) {
  const { assembleECharts } = await import('flint-chart')
  const semantics = Object.fromEntries(Object.values(spec.encoding).map((encoding) => [encoding.field, semanticTypes[encoding.type]]))
  const encodings = Object.fromEntries(Object.entries(spec.encoding).map(([channel, encoding]) => [channel, { field: encoding.field }]))
  return assembleECharts({
    data: { values: data }, semantic_types: semantics,
    chart_spec: { chartType: chartTypes[spec.mark], title, encodings, baseSize: { width: 720, height: 320 }, canvasSize: { width: 1200, height: 520 } },
    options: { addTooltips: true },
  })
}

export function ChartCard({ title, spec, data }: ChartCardProps) {
  const host = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const metricField = spec.encoding.color?.field
  const metrics = useMemo(() => {
    if (!metricField) return []
    const unique = [...new Set(data.map((row) => String(row[metricField] ?? '')).filter(Boolean))]
    return unique.sort((left, right) => {
      const leftRank = preferredMetrics.indexOf(left)
      const rightRank = preferredMetrics.indexOf(right)
      return (leftRank < 0 ? 999 : leftRank) - (rightRank < 0 ? 999 : rightRank) || metricLabel(left).localeCompare(metricLabel(right), 'zh-CN')
    })
  }, [data, metricField])
  const [selectedMetric, setSelectedMetric] = useState('')
  const activeMetric = metrics.includes(selectedMetric) ? selectedMetric : metrics[0] ?? ''
  const points = useMemo(() => activeMetric && metricField
    ? data.filter((row) => String(row[metricField]) === activeMetric).map((row) => Number(row[spec.encoding.y?.field ?? 'value'])).filter(Number.isFinite)
    : [], [activeMetric, data, metricField, spec.encoding.y?.field])
  const currentValue = points.at(-1)
  const previousValue = points.at(-2)
  const change = currentValue !== undefined && previousValue !== undefined && previousValue !== 0 ? (currentValue - previousValue) / Math.abs(previousValue) : null

  useEffect(() => {
    if (!host.current || navigator.userAgent.includes('jsdom')) return
    let disposed = false
    let cleanup = () => undefined
    const optionPromise = activeMetric ? Promise.resolve(buildFocusedTrendOption(title, spec, data, activeMetric)) : compileFlintECharts(title, spec, data)
    Promise.all([optionPromise, import('./echarts-runtime')]).then(([option, echarts]) => {
      if (disposed || !host.current) return
      const chart = echarts.init(host.current, undefined, { renderer: 'canvas' })
      chart.setOption({ ...option, backgroundColor: 'transparent' })
      const resize = () => chart.resize()
      window.addEventListener('resize', resize)
      cleanup = () => { window.removeEventListener('resize', resize); chart.dispose() }
    }).catch((reason) => {
      if (!disposed) setError(reason instanceof Error ? reason.message : '图表编译失败')
    })
    return () => { disposed = true; cleanup() }
  }, [activeMetric, data, spec, title])

  if (error) return <p role="alert">{error}</p>
  return <div className="metric-trend">
    {metrics.length > 1 && <div className="metric-switch" role="group" aria-label="选择趋势指标">{metrics.map((metric) => <button type="button" key={metric} aria-pressed={activeMetric === metric} onClick={() => setSelectedMetric(metric)}>{metricLabel(metric)}</button>)}</div>}
    {activeMetric && currentValue !== undefined && <div className="metric-trend__summary" aria-live="polite">
      <span><small>当前值</small><strong>{formatMetricValue(activeMetric, currentValue)}</strong></span>
      <span><small>较上期</small><strong data-direction={change === null ? 'flat' : change >= 0 ? 'up' : 'down'}>{change === null ? '—' : `${change >= 0 ? '+' : ''}${(change * 100).toFixed(1)}%`}</strong></span>
      <span><small>时间点</small><strong>{points.length}</strong></span>
    </div>}
    <div className="chart-host" ref={host} role="img" aria-label={`${activeMetric ? metricLabel(activeMetric) : title}趋势图`} />
  </div>
}
