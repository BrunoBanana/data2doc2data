import type { ArtifactDashboardBlock, ArtifactDashboardSpec } from '../../contracts/dashboard'

export function DiagnosticBlocks({ dashboard }: { dashboard: ArtifactDashboardSpec }) {
  if (dashboard.blocks.length === 0) return null
  return <section className="diagnostic-dashboard" aria-labelledby="diagnostic-title">
    <header><div><p className="eyebrow">LOCAL ANALYTICAL ARTIFACTS</p><h2 id="diagnostic-title">深度诊断产物</h2></div><span>{dashboard.blocks.length} 项本地产物</span></header>
    <div className="diagnostic-grid">{dashboard.blocks.map((block) => <DiagnosticBlock key={block.block_id} block={block} />)}</div>
  </section>
}

function DiagnosticBlock({ block }: { block: ArtifactDashboardBlock }) {
  const anomalies = Array.isArray(block.observations.anomalies) ? block.observations.anomalies : []
  const contributors = Array.isArray(block.observations.contributors) ? block.observations.contributors : []
  const topics = Array.isArray(block.observations.topics) ? block.observations.topics : []
  const clusters = Array.isArray(block.observations.clusters) ? block.observations.clusters : []
  const svg = safeSvg(block.observations.word_cloud_svg)
  return <article className="diagnostic-card" data-kind={block.kind}>
    <div className="diagnostic-card__heading"><div><span>{block.kind.replaceAll('_', ' ')}</span><h3>{block.title}</h3></div><b>{block.status === 'completed' ? '已完成' : '证据不足'}</b></div>
    <dl><div><dt>方法</dt><dd>{block.provenance.method}</dd></div><div><dt>范围</dt><dd>样本 {block.provenance.sample_size}</dd></div><div><dt>产物</dt><dd>{block.provenance.artifact_ref}</dd></div></dl>
    {anomalies.length > 0 && <div className="diagnostic-table-wrap"><table><caption>异常点明细</caption><thead><tr><th>日期</th><th>数值</th><th>稳健分数</th></tr></thead><tbody>{anomalies.map((item, index) => {
      const row = item as Record<string, unknown>
      return <tr key={`${String(row.date)}-${index}`}><td>{String(row.date ?? '—')}</td><td>{String(row.value ?? '—')}</td><td>{String(row.robust_score ?? '—')}</td></tr>
    })}</tbody></table></div>}
    {contributors.length > 0 && <div className="diagnostic-table-wrap"><table aria-label="贡献分解明细"><thead><tr><th>分组</th><th>基准</th><th>当前</th><th>变化</th><th>贡献</th></tr></thead><tbody>{contributors.map((item, index) => {
      const row = item as Record<string, unknown>
      return <tr key={`${String(row.member)}-${index}`}><td>{String(row.member ?? '—')}</td><td>{formatValue(row.baseline)}</td><td>{formatValue(row.current)}</td><td>{formatValue(row.delta)}</td><td>{formatPercent(row.contribution_percent)}</td></tr>
    })}</tbody></table></div>}
    {svg && <div className="diagnostic-word-cloud" dangerouslySetInnerHTML={{ __html: svg }} />}
    {topics.length > 0 && <ul className="diagnostic-topics">{topics.slice(0, 8).map((item, index) => {
      const topic = item as Record<string, unknown>
      return <li key={String(topic.topic_id ?? index)}><strong>{String(topic.label ?? `主题 ${index + 1}`)}</strong><span>{Array.isArray(topic.keywords) ? topic.keywords.slice(0, 6).join(' · ') : ''}</span></li>
    })}</ul>}
    {clusters.length > 0 && <ul className="diagnostic-clusters" aria-label="文本聚类">{clusters.slice(0, 8).map((item, index) => {
      const cluster = item as Record<string, unknown>
      const documents = Array.isArray(cluster.documents) ? cluster.documents : []
      return <li key={String(cluster.cluster_id ?? index)}><div><strong>{String(cluster.label ?? `聚类 ${index + 1}`)}</strong><span>{Array.isArray(cluster.keywords) ? cluster.keywords.slice(0, 6).join(' · ') : ''}</span></div><b>{documents.length} 份材料</b></li>
    })}</ul>}
    {block.provenance.limitations.length > 0 && <aside><strong>解释边界</strong><ul>{block.provenance.limitations.map((item) => <li key={item}>{item}</li>)}</ul></aside>}
  </article>
}

function formatValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value) : String(value ?? '—')
}

function formatPercent(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? `${formatValue(value)}%` : '—'
}

function safeSvg(value: unknown) {
  if (typeof value !== 'string') return ''
  const normalized = value.trim().toLowerCase()
  if (!normalized.startsWith('<svg') || normalized.includes('<script') || normalized.includes('http') || normalized.includes('javascript:')) return ''
  return value
}
