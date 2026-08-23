export interface QueryProvenance {
  snapshot_id: string
  sha256: string
  expression: string
  fields: string[]
  result_row_count: number
}

export interface ChartEncoding {
  field: string
  type: 'temporal' | 'quantitative' | 'nominal' | 'ordinal'
}

export interface FlintChartSpec {
  mark: 'line' | 'bar' | 'point' | 'area'
  encoding: Record<string, ChartEncoding>
  transforms: Record<string, unknown>[]
}

export interface DashboardBlock {
  block_id: string
  kind: 'kpi' | 'chart' | 'table'
  title: string
  provenance: QueryProvenance
  value: unknown
  chart?: FlintChartSpec
  data: Record<string, unknown>[]
}

export interface DashboardSpec {
  contract_version: 1
  dashboard_id: string
  title: string
  blocks: DashboardBlock[]
}

export interface TextCitation {
  document: string
  sha256: string
  start_line: number
  end_line: number
  excerpt: string
}

export interface TextClaim {
  claim_id: string
  text: string
  status: 'pending' | 'supported' | 'contradicted'
  citation: TextCitation
  conflicts_with: string[]
}

export interface TextDashboardSpec {
  corpus_id: string
  document_count: number
  failure_count: number
  duplicate_count: number
  topics: string[]
  entities: string[]
  claims: TextClaim[]
}

export interface CombinedDashboard {
  dashboard: DashboardSpec | null
  text_dashboard: TextDashboardSpec | null
}
