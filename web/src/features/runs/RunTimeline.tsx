import type { RunEvent } from '../../contracts/run-events'

const labels: Record<string, string> = {
  'run.started': '开始分析',
  'data.profiled': '数据画像',
  'chart.spec.created': '生成 Dashboard',
  'document.indexed': '索引文本材料',
  'claim.extracted': '抽取待核验主张',
  'hypothesis.created': '登记分析假设',
  'validation.completed': '完成假设核验',
  'evidence.linked': '构建证据链',
  'run.completed': '分析完成',
  'run.failed': '分析失败',
}

export function RunTimeline({ events }: { events: RunEvent[] }) {
  const ordered = [...events].sort((left, right) => left.sequence - right.sequence)
  return <section className="run-timeline" aria-labelledby="run-timeline-title"><div className="dashboard-heading"><div><p className="eyebrow">OBSERVABLE RUN</p><h2 id="run-timeline-title">分析过程</h2></div><span>{ordered.length} 个可观察事件</span></div><ol>{ordered.map((event) => <li key={`${event.run_id}-${event.sequence}`} className={`run-step run-step--${event.kind.endsWith('failed') ? 'failed' : event.kind.endsWith('completed') ? 'completed' : 'active'}`}><span className="run-step__index">{event.sequence}</span><div><strong>{labels[event.kind] ?? event.kind}</strong><small>{event.phase} · {new Date(event.created_at).toLocaleTimeString()}</small><div className="event-summary">{Object.entries(event.summary).map(([key, value]) => <span key={key}><b>{key}</b> {formatValue(value)}</span>)}</div></div></li>)}</ol></section>
}

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.map(String).join('、')
  if (value && typeof value === 'object') return '结构化结果'
  return String(value)
}
