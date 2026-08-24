import type { SnapshotRef } from './workbench'

export type RunEventKind =
  | 'run.started' | 'run.completed' | 'run.failed' | 'run.interrupted'
  | 'step.started' | 'step.completed' | 'step.failed' | 'step.added'
  | 'data.profiled' | 'compute.plan.created' | 'compute.result.created'
  | 'chart.spec.created' | 'chart.rendered' | 'dashboard.updated'
  | 'document.indexed' | 'retrieval.result.created' | 'claim.extracted'
  | 'hypothesis.created' | 'validation.completed' | 'evidence.linked'
  | 'conclusion.created' | 'approval.requested' | 'approval.decided'
  | 'plan.created' | 'plan.revised'
  | 'tool.started' | 'tool.progress' | 'tool.result' | 'tool.failed'
  | 'node.added' | 'node.updated' | 'edge.added' | 'edge.activated'
  | 'conflict.detected'
  | 'knowledge.candidate' | 'knowledge.verified' | 'knowledge.superseded'
  | 'report.generated'

export interface RunEvent {
  contract_version: 1
  run_id: string
  sequence: number
  kind: RunEventKind
  phase: string
  summary: Record<string, unknown>
  artifact_refs: string[]
  created_at: string
}

export interface AnalysisRun {
  contract_version: 1
  run_id: string
  task_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted'
  snapshot_refs: SnapshotRef[]
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface EvidenceNode {
  node_id: string
  kind: string
  label: string
  status: 'pending' | 'verified' | 'supported' | 'contradicted' | 'insufficient'
  artifact_ref: string | null
}

export interface EvidenceEdge {
  edge_id: string
  source: string
  target: string
  relationship: 'derived_from' | 'supports' | 'contradicts' | 'tests' | 'insufficient_for'
}

export interface EvidenceGraphSpec {
  contract_version: 1
  graph_id: string
  nodes: EvidenceNode[]
  edges: EvidenceEdge[]
}

export interface AnalysisRunResult {
  run: AnalysisRun
  events: RunEvent[]
  evidence_graph: EvidenceGraphSpec
}

export interface AnalysisRunStart {
  accepted: true
  run: AnalysisRun
  stream_url: string
}

export interface RunHistoryItem extends AnalysisRun {
  stale: boolean
  event_count: number
  failure_type: string | null
}
