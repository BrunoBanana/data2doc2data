export interface ProviderConnection {
  provider_id: string
  kind: string
  state: string
  capabilities: string[]
  detail: string | null
  reconnect_hint: string | null
}

export interface AgentProviderStatus {
  name: string
  available: boolean
  connected: boolean
  version: string | null
  authenticated: boolean
  compatible: boolean
  detail: string | null
}

export interface AgentSession {
  id: string
  provider: string
  workspace: string
  permission_mode: 'read_only' | 'collaborative' | 'trusted_session'
  resumed: boolean
}

export interface AgentEvent {
  kind: string
  payload: Record<string, unknown>
}

export interface AgentApproval {
  request_id: string
  operation: string
  command?: string
  working_directory?: string
  target_paths?: string[]
  diff?: string
  expires_at?: string
}

export interface SnapshotRef {
  kind: 'dataset' | 'document'
  snapshot_id: string
  sha256: string
}

export interface AnalysisTask {
  task_id: string
  title: string
  goal: string
  status: string
  snapshot_refs: SnapshotRef[]
}

export interface FlagshipCaseSummary {
  id: string
  title: string
  summary: string
  business_question: string
  learning_objective: string
  metric_count: number
  record_count: number
  document_count: number
  synthetic: true
  time_range: { start: string; end: string; grain: 'week' }
}

export interface SourcePreview {
  preview: {
    format: string
    fields: string[]
    row_count: number | null
    sample_rows: Record<string, string>[]
  }
  suggestion: Record<string, string> | null
}

export interface PreparedSource extends SourcePreview {
  source_path: string
}
