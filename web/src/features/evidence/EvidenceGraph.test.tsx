import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EvidenceGraph } from './EvidenceGraph'
import type { EvidenceGraphSpec } from '../../contracts/run-events'

const graph: EvidenceGraphSpec = { contract_version: 1, graph_id: 'graph-1', nodes: [
  { node_id: 'signal-1', kind: 'data_signal', label: '收入下降 8%', status: 'verified', artifact_ref: 'dashboard-1' },
  { node_id: 'claim-1', kind: 'claim', label: '收入目标增长', status: 'contradicted', artifact_ref: 'claim-source' },
], edges: [{ edge_id: 'edge-1', source: 'signal-1', target: 'claim-1', relationship: 'contradicts' }] }

describe('EvidenceGraph', () => {
  it('filters and expands evidence nodes without exposing private reasoning', () => {
    render(<EvidenceGraph graph={graph} />)

    fireEvent.click(screen.getByRole('button', { name: '矛盾' }))
    expect(screen.getAllByText('收入目标增长').length).toBeGreaterThan(0)
    expect(screen.queryByText('收入下降 8%')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByText('收入目标增长')[0])
    expect(screen.getByRole('dialog')).toHaveTextContent('claim-source')
  })
})
