import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'

import type { FlowLane, FlowNodeStatus } from './flow-projection'

export interface FlowNodeData extends Record<string, unknown> {
  label: string
  kind: string
  lane: FlowLane
  status: FlowNodeStatus
  active: boolean
  addedAt: number
}

export type AgentFlowNode = Node<FlowNodeData, 'agentFlow'>

const statusLabels: Record<FlowNodeStatus, string> = {
  pending: '待核验',
  verified: '已验证',
  supported: '支持',
  contradicted: '冲突',
  insufficient: '证据不足',
}

const kindLabels: Record<string, string> = {
  data_source: 'DATA', document_source: 'DOC', document_excerpt: 'QUOTE', compute_plan: 'PLAN',
  data_signal: 'SIGNAL', claim: 'CLAIM', hypothesis: 'HYPOTHESIS', validation: 'CHECK',
  conclusion: 'CONCLUSION', action: 'ACTION', report: 'REPORT',
}

export function FlowNode({ data, selected }: NodeProps<AgentFlowNode>) {
  return <article className={`agent-flow-node agent-flow-node--${data.status}${data.active ? ' agent-flow-node--active' : ''}${selected ? ' agent-flow-node--selected' : ''}`}>
    <Handle type="target" position={Position.Left} className="agent-flow-handle" />
    <div className="agent-flow-node__meta"><b>{String(data.addedAt).padStart(2, '0')}</b><span>{kindLabels[data.kind] ?? data.kind.toUpperCase().slice(0, 16)}</span></div>
    <strong>{data.label}</strong>
    <footer><span>{statusLabels[data.status]}</span><small>{data.lane}</small></footer>
    <Handle type="source" position={Position.Right} className="agent-flow-handle" />
  </article>
}
