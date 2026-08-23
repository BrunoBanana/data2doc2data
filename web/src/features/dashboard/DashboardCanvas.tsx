import { useMemo, useState } from 'react'

import type { DashboardBlock, DashboardSpec } from '../../contracts/dashboard'
import { ChartCard } from './ChartCard'
import { DataProfilePanel } from './DataProfilePanel'

const allowedMarks = new Set(['line', 'bar', 'point', 'area'])
const allowedTransforms = new Set(['aggregate', 'filter', 'bin', 'sort', 'top_n'])
const allowedChannels = new Set(['x', 'y', 'color', 'size', 'shape', 'tooltip'])
const allowedTypes = new Set(['temporal', 'quantitative', 'nominal', 'ordinal'])
const safeField = /^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{0,127}$/

export function DashboardCanvas({ dashboard }: { dashboard: DashboardSpec }) {
  const [provenance, setProvenance] = useState<DashboardBlock | null>(null)
  const validationError = useMemo(() => validateDashboard(dashboard), [dashboard])
  if (validationError) return <p className="form-notice" role="alert">Dashboard 包含不受支持的内容：{validationError}</p>
  const kpis = dashboard.blocks.filter((block) => block.kind === 'kpi')
  const details = dashboard.blocks.filter((block) => block.kind !== 'kpi')

  return (
    <section className="dashboard-canvas" aria-labelledby="dashboard-title">
      <div className="dashboard-heading"><div><p className="eyebrow">DETERMINISTIC DASHBOARD</p><h2 id="dashboard-title">{dashboard.title}</h2></div><span>本地计算 · 快照已锁定</span></div>
      <DataProfilePanel blocks={kpis} onProvenance={setProvenance} />
      <div className="dashboard-grid">{details.map((block) => <article className={`dashboard-card dashboard-card--${block.kind}`} key={block.block_id}><header><h3>{block.title}</h3><button type="button" onClick={() => setProvenance(block)}>查看依据</button></header>{block.kind === 'chart' && block.chart ? <ChartCard title={block.title} spec={block.chart} data={block.data} /> : <SafeTable rows={block.data} />}</article>)}</div>
      {provenance && <div className="provenance-backdrop" role="presentation" onMouseDown={() => setProvenance(null)}><section className="provenance-dialog" role="dialog" aria-modal="true" aria-label="计算依据" onMouseDown={(event) => event.stopPropagation()}><button className="button button--quiet provenance-close" type="button" aria-label="关闭计算依据" onClick={() => setProvenance(null)}>关闭</button><p className="eyebrow">PROVENANCE</p><h3>{provenance.title}</h3><dl><dt>计算</dt><dd>{provenance.provenance.expression}</dd><dt>字段</dt><dd>{provenance.provenance.fields.join('、')}</dd><dt>快照</dt><dd><code>{provenance.provenance.snapshot_id}</code></dd><dt>结果行数</dt><dd>{provenance.provenance.result_row_count}</dd></dl></section></div>}
    </section>
  )
}

function SafeTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="muted-copy">没有可展示的记录。</p>
  const fields = Object.keys(rows[0]).slice(0, 20)
  return <div className="table-scroll"><table><thead><tr>{fields.map((field) => <th key={field}>{field}</th>)}</tr></thead><tbody>{rows.slice(0, 100).map((row, index) => <tr key={index}>{fields.map((field) => <td key={field}>{String(row[field] ?? '')}</td>)}</tr>)}</tbody></table></div>
}

function validateDashboard(dashboard: DashboardSpec): string {
  if (dashboard.contract_version !== 1 || !Array.isArray(dashboard.blocks)) return 'Dashboard 契约版本无效'
  for (const block of dashboard.blocks) {
    if (!block || !['kpi', 'chart', 'table'].includes(block.kind) || !Array.isArray(block.data) || block.data.length > 1000) return `区块 ${block?.block_id ?? ''} 无效`
    if (block.kind === 'chart') {
      if (!block.chart || !allowedMarks.has(block.chart.mark)) return `图表 ${block.block_id} 类型不受支持`
      for (const [channel, encoding] of Object.entries(block.chart.encoding)) {
        if (!allowedChannels.has(channel) || !safeField.test(encoding.field) || !allowedTypes.has(encoding.type)) return `图表 ${block.block_id} 编码不受支持`
      }
      if (block.chart.transforms.some((transform) => !allowedTransforms.has(String(transform.type)))) return `图表 ${block.block_id} 变换不受支持`
    }
  }
  return ''
}
