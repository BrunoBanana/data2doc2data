import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AnalysisRunResult, RunHistoryItem } from '../../contracts/run-events'
import { RunHistory } from './RunHistory'

const history: RunHistoryItem[] = [
  { run_id: 'run-2', task_id: 'task-1', status: 'failed', created_at: '2026-08-23T02:00:00Z', started_at: '2026-08-23T02:00:00Z', completed_at: '2026-08-23T02:00:01Z', snapshot_refs: [], contract_version: 1, stale: true, event_count: 3, failure_type: 'DataProfileError' },
  { run_id: 'run-1', task_id: 'task-1', status: 'completed', created_at: '2026-08-23T01:00:00Z', started_at: '2026-08-23T01:00:00Z', completed_at: '2026-08-23T01:00:01Z', snapshot_refs: [], contract_version: 1, stale: false, event_count: 9, failure_type: null },
]
const replay: AnalysisRunResult = { run: history[1], events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] } }

describe('RunHistory', () => {
  it('shows immutable status, failure diagnosis, stale warning, replay and retry', async () => {
    const loadRun = vi.fn(async () => replay)
    const retryRun = vi.fn(async () => replay)
    const onReplay = vi.fn()
    render(<RunHistory runs={history} loadRun={loadRun} retryRun={retryRun} onReplay={onReplay} />)

    expect(screen.getByText('DataProfileError')).toBeInTheDocument()
    expect(screen.getByText('快照已变化')).toBeInTheDocument()
    expect(screen.getByLabelText('回退机制')).toHaveTextContent('回放不改变历史安全重试创建新运行原始运行始终保留')
    fireEvent.click(screen.getByRole('button', { name: /回放 run-1/ }))
    await waitFor(() => expect(onReplay).toHaveBeenCalledWith(replay))
    fireEvent.click(screen.getByRole('button', { name: /安全重试 run-2/ }))
    await waitFor(() => expect(retryRun).toHaveBeenCalledWith('run-2', expect.stringMatching(/^retry-/)))
    expect(history).toHaveLength(2)
  })
})
