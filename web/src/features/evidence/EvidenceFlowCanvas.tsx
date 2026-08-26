import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { EvidenceEdge, EvidenceNode } from '../../contracts/run-events'

const relationColors = { derived_from: '#6f6b60', supports: '#00a955', contradicts: '#c43d3d', tests: '#b87621', insufficient_for: '#8a8477' }

export default function EvidenceFlowCanvas({ visible, edges: rawEdges, activeArtifactRefs, onSelect }: { visible: EvidenceNode[]; edges: EvidenceEdge[]; activeArtifactRefs: string[]; onSelect: (nodeId: string) => void }) {
  const visibleIds = new Set(visible.map((node) => node.node_id))
  const active = new Set(activeArtifactRefs)
  const rows = new Map<number, number>()
  const nodes: Node[] = visible.map((node) => {
    const column = nodeColumn(node.kind)
    const row = rows.get(column) ?? 0
    rows.set(column, row + 1)
    return { id: node.node_id, position: { x: column * 215, y: row * 118 }, data: { label: node.label }, className: `evidence-node evidence-node--${node.status}${node.artifact_ref && active.has(node.artifact_ref) ? ' evidence-node--active' : ''}`, draggable: false }
  })
  const edges: Edge[] = rawEdges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)).map((edge) => ({ id: edge.edge_id, source: edge.source, target: edge.target, label: relationLabel(edge.relationship), animated: false, style: { stroke: relationColors[edge.relationship], strokeWidth: 2 } }))
  return <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: .12 }} minZoom={.45} maxZoom={1.5} nodesConnectable={false} nodesDraggable={false} onNodeClick={(_, node) => onSelect(node.id)}><Background color="#ded8ca" gap={32} /><Controls showInteractive={false} /></ReactFlow></div>
}

function nodeColumn(kind: string) {
  const columns: Record<string, number> = { data_source: 0, document_source: 0, compute_plan: 1, data_signal: 1, document_excerpt: 1, claim: 2, hypothesis: 2, validation: 3, conclusion: 4, action: 4 }
  return columns[kind] ?? 2
}

function relationLabel(relationship: string) {
  return ({ derived_from: '派生自', supports: '支持', contradicts: '矛盾', tests: '检验', insufficient_for: '证据不足' } as Record<string, string>)[relationship] ?? relationship
}
