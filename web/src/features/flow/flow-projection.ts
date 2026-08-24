import type { EvidenceNode, RunEvent } from '../../contracts/run-events'

export type FlowLane = 'inputs' | 'compute' | 'reasoning' | 'verification' | 'delivery'
export type FlowNodeStatus = EvidenceNode['status']

export interface FlowNodeProjection {
  id: string
  kind: string
  label: string
  status: FlowNodeStatus
  lane: FlowLane
  artifactRef: string | null
  addedAt: number
  updatedAt: number
}

export interface FlowEdgeProjection {
  id: string
  source: string
  target: string
  relationship: string
  addedAt: number
  activeAt: number | null
  conflicted: boolean
}

export interface ActiveToolProjection {
  stepId: string
  name: string
  state: 'running' | 'completed' | 'failed'
  progress: number | null
  sequence: number
}

export interface ReportProjection {
  filename: string
  sha256: string
  byteCount: number | null
}

export interface FlowProjection {
  nodes: FlowNodeProjection[]
  edges: FlowEdgeProjection[]
  activeNodeIds: string[]
  activeEdgeIds: string[]
  activeTool: ActiveToolProjection | null
  planRevisionCount: number
  conflictCount: number
  converged: boolean
  report: ReportProjection | null
  lastSequence: number
  phase: string
}

export function emptyFlowProjection(): FlowProjection {
  return {
    nodes: [], edges: [], activeNodeIds: [], activeEdgeIds: [], activeTool: null,
    planRevisionCount: 0, conflictCount: 0, converged: false, report: null,
    lastSequence: 0, phase: 'setup',
  }
}

export function projectFlowEvents(events: RunEvent[]): FlowProjection {
  return [...events]
    .sort((left, right) => left.sequence - right.sequence)
    .reduce(projectFlowEvent, emptyFlowProjection())
}

export function projectFlowEvent(current: FlowProjection, event: RunEvent): FlowProjection {
  if (event.sequence <= current.lastSequence) return current
  let next: FlowProjection = { ...current, lastSequence: event.sequence, phase: event.phase }
  const summary = event.summary

  if (event.kind === 'node.added') {
    const id = text(summary.node_id)
    if (!id || current.nodes.some((node) => node.id === id)) return next
    const kind = text(summary.node_kind) || 'evidence'
    const artifactRef = event.artifact_refs.find((reference) => reference !== id) ?? null
    const node: FlowNodeProjection = {
      id,
      kind,
      label: boundedText(summary.label, kindLabel(kind)),
      status: evidenceStatus(summary.status),
      lane: laneForKind(kind),
      artifactRef,
      addedAt: event.sequence,
      updatedAt: event.sequence,
    }
    return { ...next, nodes: [...current.nodes, node], activeNodeIds: [id] }
  }

  if (event.kind === 'node.updated') {
    const id = text(summary.node_id)
    if (!id) return next
    return {
      ...next,
      nodes: current.nodes.map((node) => node.id === id ? {
        ...node,
        label: summary.label === undefined ? node.label : boundedText(summary.label, node.label),
        status: summary.status === undefined ? node.status : evidenceStatus(summary.status),
        updatedAt: event.sequence,
      } : node),
      activeNodeIds: current.nodes.some((node) => node.id === id) ? [id] : [],
    }
  }

  if (event.kind === 'edge.added') {
    const edge = edgeFromEvent(event)
    if (!edge || current.edges.some((item) => item.id === edge.id)) return next
    return { ...next, edges: [...current.edges, edge], activeEdgeIds: [edge.id] }
  }

  if (event.kind === 'edge.activated') {
    const id = text(summary.edge_id)
    if (!id) return next
    return {
      ...next,
      edges: current.edges.map((edge) => edge.id === id ? { ...edge, activeAt: event.sequence } : edge),
      activeEdgeIds: current.edges.some((edge) => edge.id === id) ? [id] : [],
    }
  }

  if (event.kind === 'tool.started' || event.kind === 'tool.progress' || event.kind === 'tool.result' || event.kind === 'tool.failed') {
    const stepId = text(summary.step_id)
    const name = text(summary.tool)
    const state = event.kind === 'tool.failed' ? 'failed' : event.kind === 'tool.result' ? 'completed' : 'running'
    const progress = finiteNumber(summary.progress)
    return {
      ...next,
      activeTool: { stepId, name, state, progress, sequence: event.sequence },
      activeNodeIds: current.nodes.some((node) => node.id === stepId) ? [stepId] : current.activeNodeIds,
    }
  }

  if (event.kind === 'plan.revised') {
    return { ...next, planRevisionCount: current.planRevisionCount + 1 }
  }

  if (event.kind === 'conflict.detected') {
    const referencedEdge = event.artifact_refs.find((reference) => current.edges.some((edge) => edge.id === reference))
    return {
      ...next,
      conflictCount: current.conflictCount + 1,
      edges: current.edges.map((edge) => edge.id === referencedEdge ? { ...edge, conflicted: true, activeAt: event.sequence } : edge),
      activeEdgeIds: referencedEdge ? [referencedEdge] : current.activeEdgeIds,
    }
  }

  if (event.kind === 'report.generated') {
    return {
      ...next,
      converged: true,
      report: {
        filename: boundedText(summary.filename, 'analysis-report.html'),
        sha256: boundedText(summary.sha256, ''),
        byteCount: finiteNumber(summary.byte_count),
      },
    }
  }

  return next
}

export function laneForKind(kind: string): FlowLane {
  if (kind === 'data_source' || kind === 'document_source' || kind === 'document_excerpt') return 'inputs'
  if (kind === 'compute_plan' || kind === 'data_signal') return 'compute'
  if (kind === 'claim' || kind === 'hypothesis') return 'reasoning'
  if (kind === 'validation') return 'verification'
  if (kind === 'conclusion' || kind === 'action' || kind === 'report') return 'delivery'
  return 'reasoning'
}

function edgeFromEvent(event: RunEvent): FlowEdgeProjection | null {
  const id = text(event.summary.edge_id)
  const source = text(event.summary.source)
  const target = text(event.summary.target)
  if (!id || !source || !target) return null
  return {
    id,
    source,
    target,
    relationship: text(event.summary.relationship) || 'derived_from',
    addedAt: event.sequence,
    activeAt: null,
    conflicted: false,
  }
}

function evidenceStatus(value: unknown): FlowNodeStatus {
  return value === 'verified' || value === 'supported' || value === 'contradicted' || value === 'insufficient'
    ? value
    : 'pending'
}

function kindLabel(kind: string) {
  return ({
    data_source: '数据来源', document_source: '文本来源', document_excerpt: '引用片段', compute_plan: '计算计划',
    data_signal: '数据信号', claim: '文本主张', hypothesis: '业务假设', validation: '交叉核验',
    conclusion: '分析结论', action: '建议行动', report: '分析报告',
  } as Record<string, string>)[kind] ?? '证据节点'
}

function boundedText(value: unknown, fallback: string) {
  const result = text(value).trim()
  return (result || fallback).slice(0, 500)
}

function text(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
