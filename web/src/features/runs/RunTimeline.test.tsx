import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RunTimeline } from './RunTimeline'

describe('RunTimeline', () => {
  it('renders replayed events in sequence with observable summaries', () => {
    render(<RunTimeline events={[
      { contract_version: 1, run_id: 'run-1', sequence: 2, kind: 'data.profiled', phase: 'profile', summary: { row_count: 12 }, artifact_refs: [], created_at: '2026-08-23T00:00:01Z' },
      { contract_version: 1, run_id: 'run-1', sequence: 1, kind: 'run.started', phase: 'setup', summary: { snapshot_count: 1 }, artifact_refs: [], created_at: '2026-08-23T00:00:00Z' },
      { contract_version: 1, run_id: 'run-1', sequence: 3, kind: 'run.completed', phase: 'finish', summary: { status: 'completed' }, artifact_refs: [], created_at: '2026-08-23T00:00:02Z' },
    ]} />)

    const steps = screen.getAllByRole('listitem')
    expect(steps[0]).toHaveTextContent('开始分析')
    expect(steps[1]).toHaveTextContent('数据画像')
    expect(steps[2]).toHaveTextContent('分析完成')
    expect(screen.queryByText(/chain.of.thought/i)).not.toBeInTheDocument()
  })
})
