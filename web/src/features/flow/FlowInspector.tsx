import type { FlowNodeProjection, FlowProjection } from './flow-projection'

export function FlowInspector({ projection, selected }: { projection: FlowProjection; selected: FlowNodeProjection | null }) {
  return <aside className="flow-inspector" aria-label="Flow 节点检查器">
    <div className="flow-inspector__heading"><p className="eyebrow">LIVE INSPECTOR</p><h3>{selected ? '节点详情' : '运行状态'}</h3></div>
    {selected ? <dl>
      <dt>节点</dt><dd><code>{selected.id}</code></dd>
      <dt>类型</dt><dd>{selected.kind}</dd>
      <dt>状态</dt><dd>{statusLabel(selected.status)}</dd>
      <dt>阶段</dt><dd>{laneLabel(selected.lane)}</dd>
      <dt>制品</dt><dd>{selected.artifactRef ?? '无独立制品'}</dd>
      <dt>出现于</dt><dd>事件 #{selected.addedAt}</dd>
    </dl> : <div className="flow-inspector__empty"><strong>选择画布节点</strong><p>检查可审计状态、制品引用和事件位置。</p></div>}
    <section className="flow-inspector__runtime" aria-label="当前运行">
      <span>当前阶段</span><strong>{projection.phase}</strong>
      {projection.activeTool && <p><b>{toolStateLabel(projection.activeTool.state)}</b>{projection.activeTool.name || projection.activeTool.stepId}{projection.activeTool.progress === null ? '' : ` · ${Math.round(projection.activeTool.progress * 100)}%`}</p>}
    </section>
    {projection.communication && <section className="flow-inspector__protocol" aria-label="协议交接">
      <span>PROTOCOL HANDOFF</span>
      <strong>{projection.communication.sender} → {projection.communication.receiver}</strong>
      <small>TRACE {projection.communication.traceId}</small>
      <small>ATTEMPT {projection.communication.attempt} · ID {projection.communication.idempotencyKey.slice(0, 18)}…</small>
    </section>}
    <div className="flow-inspector__counts" aria-label="Flow 图统计">
      <span><b>{projection.nodes.length}</b>节点</span>
      <span><b>{projection.edges.length}</b>关系</span>
      <span><b>{projection.conflictCount}</b>冲突</span>
      <span><b>{projection.planRevisionCount}</b>修订</span>
    </div>
    {projection.report && <section className="flow-inspector__report"><span>REPORT READY</span><strong>{projection.report.filename}</strong><small>SHA-256 {projection.report.sha256.slice(0, 12)}…</small></section>}
  </aside>
}

function statusLabel(status: FlowNodeProjection['status']) {
  return ({ pending: '待核验', verified: '已验证', supported: '支持', contradicted: '存在冲突', insufficient: '证据不足' })[status]
}

function laneLabel(lane: FlowNodeProjection['lane']) {
  return ({ inputs: '输入材料', compute: '本地计算', reasoning: '交叉推理', verification: '证据核验', delivery: '结论交付' })[lane]
}

function toolStateLabel(state: 'running' | 'completed' | 'failed') {
  return ({ running: '执行中 · ', completed: '已完成 · ', failed: '失败 · ' })[state]
}
