import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { EvidenceEdge, EvidenceNode } from '../../contracts/run-events'

const relationColors = { derived_from: '#7399df', supports: '#55d6a2', contradicts: '#ff7785', tests: '#d8b36b', insufficient_for: '#8f9bb2' }

export default function EvidenceFlowCanvas({ visible, edges: rawEdges, activeArtifactRefs, onSelect }: { visible: EvidenceNode[]; edges: EvidenceEdge[]; activeArtifactRefs: string[]; onSelect: (nodeId: string) => void }) {
  const visibleIds = new Set(visible.map((node) => node.node_id))
  const active = new Set(activeArtifactRefs)
  const nodes: Node[] = visible.map((node, index) => ({ id: node.node_id, position: positionNode(node.kind, index), data: { label: node.label }, className: `evidence-node evidence-node--${node.status}${node.artifact_ref && active.has(node.artifact_ref) ? ' evidence-node--active' : ''}`, draggable: false }))
  const edges: Edge[] = rawEdges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)).map((edge) => ({ id: edge.edge_id, source: edge.source, target: edge.target, label: relationLabel(edge.relationship), animated: false, style: { stroke: relationColors[edge.relationship], strokeWidth: 2 } }))
  return <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} fitView nodesConnectable={false} nodesDraggable={false} onNodeClick={(_, node) => onSelect(node.id)}><Background color="#26324a" gap={24} /><Controls showInteractive={false} /></ReactFlow></div>
}

function positionNode(kind: string, index: number) {
  const columns: Record<string, number> = { data_source: 0, data_signal: 1, document_source: 1, document_excerpt: 2, claim: 2, hypothesis: 3, validation: 4, conclusion: 5, action: 6 }
  return { x: (columns[kind] ?? 2) * 240, y: (index % 5) * 120 }
}

function relationLabel(relationship: string) {
  return ({ derived_from: '派生自', supports: '支持', contradicts: '矛盾', tests: '检验', insufficient_for: '证据不足' } as Record<string, string>)[relationship] ?? relationship
}
