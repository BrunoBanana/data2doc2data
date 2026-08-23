export interface ProviderConnection {
  provider_id: string
  kind: string
  state: string
  capabilities: string[]
  detail: string | null
  reconnect_hint: string | null
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
