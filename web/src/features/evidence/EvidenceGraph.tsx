import { lazy, Suspense, useMemo, useState } from 'react'

import type { EvidenceGraphSpec, EvidenceNode } from '../../contracts/run-events'
import { HypothesisTree } from './HypothesisTree'

const filters = [{ id: 'all', label: '全部' }, { id: 'verified', label: '已验证' }, { id: 'supported', label: '支持' }, { id: 'contradicted', label: '存在冲突' }, { id: 'insufficient', label: '证据不足' }] as const
const statusLabels: Record<string, string> = { verified: '已验证', supported: '支持', contradicted: '存在冲突', insufficient: '证据不足', pending: '待验证' }
const EvidenceFlowCanvas = lazy(() => import('./EvidenceFlowCanvas'))

export function EvidenceGraph({ graph, activeArtifactRefs = [], question }: { graph: EvidenceGraphSpec; activeArtifactRefs?: string[]; question?: string }) {
  const [filter, setFilter] = useState<(typeof filters)[number]['id']>('all')
  const [selected, setSelected] = useState<EvidenceNode | null>(null)
  const visible = useMemo(() => graph.nodes.filter((node) => filter === 'all' || node.status === filter), [filter, graph.nodes])

  const active = new Set(activeArtifactRefs)
  return <>{question && <HypothesisTree graph={graph} question={question} />}<section className="evidence-graph" aria-labelledby="evidence-title"><div className="dashboard-heading"><div><p className="eyebrow">EVIDENCE BLUEPRINT</p><h2 id="evidence-title">证据链与假设图</h2></div><span>{graph.nodes.length} 个节点 · {graph.edges.length} 条关系</span></div><div className="graph-filters" aria-label="证据状态筛选">{filters.map((item) => <button type="button" key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}</div><div className="graph-accessible">{visible.map((node, index) => <button type="button" key={node.node_id} data-active={node.artifact_ref && active.has(node.artifact_ref) || undefined} onClick={() => setSelected(node)}><b>{String(index + 1).padStart(2, '0')}</b><span>{statusLabels[node.status] ?? node.status}</span>{node.label}</button>)}</div>{!navigator.userAgent.includes('jsdom') && <Suspense fallback={<div className="graph-canvas graph-canvas--loading">正在加载证据图…</div>}><EvidenceFlowCanvas visible={visible} edges={graph.edges} activeArtifactRefs={activeArtifactRefs} onSelect={(nodeId) => setSelected(graph.nodes.find((item) => item.node_id === nodeId) ?? null)} /></Suspense>}{selected && <div className="provenance-backdrop" role="presentation" onMouseDown={() => setSelected(null)}><section className="provenance-dialog" role="dialog" aria-modal="true" aria-label="证据节点详情" onMouseDown={(event) => event.stopPropagation()}><button className="button button--quiet provenance-close" type="button" aria-label="关闭证据节点" onClick={() => setSelected(null)}>关闭</button><p className="eyebrow">{selected.kind}</p><h3>{selected.label}</h3><dl><dt>状态</dt><dd>{statusLabels[selected.status] ?? selected.status}</dd><dt>节点</dt><dd><code>{selected.node_id}</code></dd><dt>来源</dt><dd>{selected.artifact_ref ?? '无独立制品'}</dd></dl></section></div>}</section></>
}
