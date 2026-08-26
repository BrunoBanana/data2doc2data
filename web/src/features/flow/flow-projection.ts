import type { EvidenceNode, RunEvent } from '../../contracts/run-events'

const analysisMethodLabels: Record<string, string> = {
  detect_anomalies: '稳健异常检测', detect_change_points: '结构变化点检测', compare_periods: '前后周期比较',
  segment_rank: '分组差异排名', decompose_change: '变化贡献分解', correlate_metrics: '指标时滞关联',
  compare_groups: '组间效应比较', analyze_text: '文本主题与聚类', tfidf_nmf_kmeans: '文本主题与聚类',
  topic_metric_alignment: '文本—指标对齐', text_metric_lag: '文本领先指标检验', explanatory_segments: '解释分组候选',
}

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

export interface CommunicationProjection {
  traceId: string
  messageId: string
  sender: string
  receiver: string
  attempt: number
  idempotencyKey: string
  deadlineAt: string | null
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
  communication: CommunicationProjection | null
}

export function emptyFlowProjection(): FlowProjection {
  return {
    nodes: [], edges: [], activeNodeIds: [], activeEdgeIds: [], activeTool: null,
    planRevisionCount: 0, conflictCount: 0, converged: false, report: null,
    lastSequence: 0, phase: 'setup',
    communication: null,
  }
}

export function projectFlowEvents(events: RunEvent[]): FlowProjection {
  return [...events]
    .sort((left, right) => left.sequence - right.sequence)
    .reduce(projectFlowEvent, emptyFlowProjection())
}

export function projectFlowEvent(current: FlowProjection, event: RunEvent): FlowProjection {
  if (event.sequence <= current.lastSequence) return current
  let next: FlowProjection = {
    ...current,
    lastSequence: event.sequence,
    phase: event.phase,
    communication: communicationFromEvent(event) ?? current.communication,
  }
  const summary = event.summary

  if (event.kind === 'step.added') {
    const id = text(summary.step_id)
    if (!id || current.nodes.some((node) => node.id === id)) return next
    const tool = text(summary.tool)
    const node: FlowNodeProjection = {
      id,
      kind: 'tool_step',
      label: boundedText(summary.purpose, tool || '本地工具步骤'),
      status: 'pending',
      lane: laneForTool(tool),
      artifactRef: null,
      addedAt: event.sequence,
      updatedAt: event.sequence,
    }
    const dependencies = Array.isArray(summary.dependencies)
      ? summary.dependencies.map(text).filter(Boolean)
      : []
    const dependencyEdges: FlowEdgeProjection[] = dependencies.map((dependency) => ({
      id: `step:${dependency}->${id}`,
      source: dependency,
      target: id,
      relationship: 'derived_from',
      addedAt: event.sequence,
      activeAt: null,
      conflicted: false,
    }))
    return {
      ...next,
      nodes: [...current.nodes, node],
      edges: [...current.edges, ...dependencyEdges],
      activeNodeIds: [id],
      activeEdgeIds: dependencyEdges.map((edge) => edge.id),
    }
  }

  if (event.kind === 'round.planned') {
    const roundNumber = finiteNumber(summary.round_number)
    if (roundNumber === null) return next
    const id = `round-${roundNumber}`
    if (current.nodes.some((node) => node.id === id)) return next
    const priorRefs = Array.isArray(summary.prior_artifact_refs) ? summary.prior_artifact_refs.map(text).filter(Boolean) : []
    const plannerPrefix = text(summary.planner) === 'connected_agent' ? 'Agent 规划 · ' : ''
    const node: FlowNodeProjection = {
      id, kind: 'analysis_round', label: `${plannerPrefix}第 ${roundNumber} 轮 · ${boundedText(summary.rationale_summary, analysisMethodLabels[text(summary.tool)] || text(summary.tool) || '继续诊断')}`,
      status: 'pending', lane: 'reasoning', artifactRef: null, addedAt: event.sequence, updatedAt: event.sequence,
    }
    const edges = priorRefs.map((source) => ({
      id: `cycle:${source}->${id}`, source, target: id, relationship: 'derived_from', addedAt: event.sequence, activeAt: event.sequence, conflicted: false,
    }))
    return { ...next, nodes: [...current.nodes, node], edges: [...current.edges, ...edges], activeNodeIds: [id], activeEdgeIds: edges.map((edge) => edge.id) }
  }

  if (event.kind === 'round.started' || event.kind === 'round.completed') {
    const roundNumber = finiteNumber(summary.round_number)
    if (roundNumber === null) return next
    const id = `round-${roundNumber}`
    return { ...next, nodes: current.nodes.map((node) => node.id === id ? { ...node, status: event.kind === 'round.completed' ? 'verified' : 'pending', updatedAt: event.sequence } : node), activeNodeIds: [id] }
  }

  if (event.kind === 'artifact.created') {
    const id = text(summary.artifact_ref) || event.artifact_refs[0]
    const roundNumber = finiteNumber(summary.round_number)
    if (!id || roundNumber === null || current.nodes.some((node) => node.id === id)) return next
    const roundId = `round-${roundNumber}`
    const node: FlowNodeProjection = {
      id, kind: text(summary.kind) === 'text_ml' ? 'text_theme' : 'analytical_artifact',
      label: analysisMethodLabels[text(summary.method)] || boundedText(summary.method, '本地分析产物'), status: 'verified',
      lane: text(summary.kind) === 'text_ml' ? 'reasoning' : 'compute', artifactRef: id,
      addedAt: event.sequence, updatedAt: event.sequence,
    }
    const edge = { id: `cycle:${roundId}->${id}`, source: roundId, target: id, relationship: 'derived_from', addedAt: event.sequence, activeAt: event.sequence, conflicted: false }
    return { ...next, nodes: [...current.nodes, node], edges: [...current.edges, edge], activeNodeIds: [id], activeEdgeIds: [edge.id] }
  }

  if (event.kind === 'step.started' || event.kind === 'step.completed' || event.kind === 'step.failed') {
    const id = text(summary.step_id)
    if (!id) return next
    const status: FlowNodeStatus = event.kind === 'step.completed'
      ? 'verified'
      : event.kind === 'step.failed'
        ? 'contradicted'
        : 'pending'
    return {
      ...next,
      nodes: current.nodes.map((node) => node.id === id ? { ...node, status, updatedAt: event.sequence } : node),
      activeNodeIds: current.nodes.some((node) => node.id === id) ? [id] : [],
    }
  }

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
  if (kind === 'compute_plan' || kind === 'data_signal' || kind === 'analytical_artifact') return 'compute'
  if (kind === 'analysis_round' || kind === 'text_theme') return 'reasoning'
  if (kind === 'claim' || kind === 'hypothesis') return 'reasoning'
  if (kind === 'validation') return 'verification'
  if (kind === 'conclusion' || kind === 'action' || kind === 'report') return 'delivery'
  return 'reasoning'
}

function laneForTool(tool: string): FlowLane {
  if (tool === 'inspect_sources') return 'inputs'
  if (tool === 'profile_data' || tool === 'query_data') return 'compute'
  if (tool === 'extract_claims' || tool === 'align_evidence') return 'reasoning'
  if (tool === 'test_hypothesis') return 'verification'
  return 'compute'
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
    conclusion: '分析结论', action: '建议行动', report: '分析报告', tool_step: '本地工具步骤',
    analysis_round: '分析轮次', analytical_artifact: '分析产物', text_theme: '文本主题',
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

function communicationFromEvent(event: RunEvent): CommunicationProjection | null {
  const value = event.communication
  if (!value) return null
  const traceId = text(value.trace_id)
  const messageId = text(value.message_id)
  const sender = text(value.sender)
  const receiver = text(value.receiver)
  const idempotencyKey = text(value.idempotency_key)
  const attempt = finiteNumber(value.attempt)
  if (!traceId || !messageId || !sender || !receiver || !idempotencyKey || attempt === null || attempt < 1) return null
  return {
    traceId,
    messageId,
    sender,
    receiver,
    attempt,
    idempotencyKey,
    deadlineAt: typeof value.deadline_at === 'string' ? value.deadline_at : null,
  }
}
