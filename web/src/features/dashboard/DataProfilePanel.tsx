import type { DashboardBlock } from '../../contracts/dashboard'

interface DataProfilePanelProps {
  blocks: DashboardBlock[]
  onProvenance: (block: DashboardBlock) => void
}

export function DataProfilePanel({ blocks, onProvenance }: DataProfilePanelProps) {
  return <div className="kpi-grid">{blocks.map((block) => <article className="kpi-card" key={block.block_id}><span>{block.title}</span><strong>{String(block.value)}</strong><button type="button" onClick={() => onProvenance(block)}>查看依据</button></article>)}</div>
}
