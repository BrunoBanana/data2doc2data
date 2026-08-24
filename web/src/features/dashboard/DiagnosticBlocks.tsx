import type { ArtifactDashboardBlock, ArtifactDashboardSpec } from '../../contracts/dashboard'

const methodLabels: Record<string, string> = {
  detect_anomalies: '稳健异常检测', detect_change_points: '结构变化点检测', compare_periods: '前后周期比较',
  segment_rank: '分组差异排名', decompose_change: '变化贡献分解', correlate_metrics: '指标时滞关联',
  compare_groups: '组间效应比较', tfidf_nmf_kmeans: '文本主题与聚类', tfidf_fallback: '小样本文本主题',
  local_embeddings: '本地语义聚类', topic_metric_alignment: '文本—指标对齐', text_metric_lag: '文本领先指标检验',
  explanatory_segments: '解释分组候选',
}
const findingLabels: Record<string, string> = {
  baseline: '基准值', current: '当前值', absolute_change: '绝对变化', change_percent: '变化率',
  change_date: '变化日期', before_mean: '变化前均值', after_mean: '变化后均值', effect_size: '效应量',
  best_lag: '最佳滞后', correlation: '相关系数', overlap: '重叠周期', difference: '组间差异',
  first_mean: '第一组均值', second_mean: '第二组均值', total_delta: '总变化', anomaly_count: '异常点数',
}

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
  const findings = Object.entries(findingLabels).flatMap(([key, label]) => {
    const value = block.observations[key]
    return typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value)) ? [{ key, label, value }] : []
  }).slice(0, 8)
  const statusLabel = ({ completed: '已完成', unavailable: '不可用', insufficient: '证据不足', failed: '失败' } as Record<string, string>)[block.status] ?? block.status
  const limitations = block.provenance.limitations.length > 0
    ? block.provenance.limitations
    : block.status === 'completed'
      ? []
      : ['当前输入不足以完成该方法；产物已保留，可补充材料后安全重试。']
  return <article className="diagnostic-card" data-kind={block.kind}>
    <div className="diagnostic-card__heading"><div><span>{block.kind.replaceAll('_', ' ')}</span><h3>{block.title}</h3></div><b data-status={block.status}>{statusLabel}</b></div>
    <dl><div><dt>方法</dt><dd><strong>{methodLabels[block.provenance.method] ?? '本地诊断'}</strong><code>{block.provenance.method}</code></dd></div><div><dt>范围</dt><dd>样本 {block.provenance.sample_size}</dd></div><div><dt>产物</dt><dd>{block.provenance.artifact_ref}</dd></div></dl>
    {findings.length > 0 && <div className="diagnostic-facts" aria-label="关键计算结果">{findings.map((finding) => <span key={finding.key}><small>{finding.label}</small><strong>{finding.key === 'change_percent' ? formatPercent(finding.value) : formatValue(finding.value)}</strong></span>)}</div>}
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
    {limitations.length > 0 && <aside><strong>{block.status === 'completed' ? '解释边界' : '为何未完成'}</strong><ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul></aside>}
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
