import { act, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { EvidenceGraphSpec, RunEvent } from '../../contracts/run-events'
import { AgentFlowCanvas, analysisCycleProgress, shouldAutoFitFlow } from './AgentFlowCanvas'

vi.mock('motion/react', () => ({ useReducedMotion: () => false }))
vi.mock('@xyflow/react', () => ({
  Background: () => null,
  Controls: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => <div aria-label="Flow 小地图" />,
  ReactFlow: ({ nodes, children }: { nodes: Array<{ id: string; data: { label: string } }>; children: ReactNode }) => <div>
    {nodes.map((node) => <span key={node.id}>{node.data.label}</span>)}
    {children}
  </div>,
}))

function event(sequence: number, kind: RunEvent['kind'], summary: Record<string, unknown> = {}): RunEvent {
  return {
    contract_version: 1,
    run_id: 'run-burst',
    sequence,
    kind,
    phase: 'cross-reasoning',
    summary,
    artifact_refs: [],
    created_at: `2026-08-24T00:00:${String(sequence).padStart(2, '0')}Z`,
  }
}

const events: RunEvent[] = [
  event(1, 'run.started'),
  event(2, 'node.added', { node_id: 'signal-1', node_kind: 'data_signal', label: '第一条数据信号', status: 'verified' }),
  event(3, 'node.added', { node_id: 'claim-1', node_kind: 'claim', label: '第二条文本主张', status: 'pending' }),
  event(4, 'run.completed'),
]

const graph: EvidenceGraphSpec = {
  contract_version: 1,
  graph_id: 'graph-burst',
  nodes: [
    { node_id: 'signal-1', kind: 'data_signal', label: '第一条数据信号', status: 'verified', artifact_ref: null },
    { node_id: 'claim-1', kind: 'claim', label: '第二条文本主张', status: 'pending', artifact_ref: null },
  ],
  edges: [],
}

afterEach(() => {
  vi.useRealTimers()
})

describe('AgentFlowCanvas readable event playback', () => {
  it('fits the canvas only for first reveal or terminal convergence', () => {
    expect(shouldAutoFitFlow(0, 1, false, false)).toBe(true)
    expect(shouldAutoFitFlow(1, 2, false, false)).toBe(false)
    expect(shouldAutoFitFlow(8, 9, false, true)).toBe(true)
    expect(shouldAutoFitFlow(9, 10, true, true)).toBe(false)
  })

  it('summarizes persisted cycle progress without exposing private reasoning', () => {
    const progress = analysisCycleProgress([
      event(1, 'cycle.started', { max_rounds: 3 }),
      event(2, 'round.completed', { round_number: 1, artifact_count: 1 }),
      event(3, 'round.completed', { round_number: 2, artifact_count: 2 }),
    ])
    expect(progress).toEqual({ completedRounds: 2, maxRounds: 3, artifactCount: 3 })
  })
  it('lets the analyst pause and resume a readable semantic playback', async () => {
    vi.useFakeTimers()
    render(<AgentFlowCanvas events={events} graph={graph} />)

    expect(screen.getByLabelText('播放速度')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '暂停播放' }))
    await act(async () => vi.advanceTimersByTime(2_000))
    expect(screen.queryByText('第一条数据信号')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '继续播放' }))
    expect(screen.queryByText('第二条文本主张')).not.toBeInTheDocument()
    expect(screen.queryByText('分析完成')).not.toBeInTheDocument()

    await act(async () => vi.advanceTimersByTime(600))
    expect(screen.getAllByText('第一条数据信号').length).toBeGreaterThan(0)
    expect(screen.queryByText('第二条文本主张')).not.toBeInTheDocument()

    await act(async () => vi.advanceTimersByTime(600))
    expect(screen.getAllByText('第二条文本主张').length).toBeGreaterThan(0)
    expect(screen.queryByText('分析完成')).not.toBeInTheDocument()

    await act(async () => vi.advanceTimersByTime(600))
    expect(screen.getByText('分析完成')).toBeInTheDocument()
  })

  it('places the execution track before the canvas workspace instead of overlaying it', () => {
    const { container } = render(<AgentFlowCanvas events={events} graph={graph} />)
    const track = container.querySelector('.agent-flow-stepbar')
    const workspace = container.querySelector('.agent-flow-workspace')

    expect(track).not.toBeNull()
    expect(workspace).not.toBeNull()
    expect(track!.compareDocumentPosition(workspace as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('keeps the process canvas focused by omitting the minimap', () => {
    render(<AgentFlowCanvas events={events} graph={graph} />)
    fireEvent.click(screen.getByRole('button', { name: /跳到实时/ }))

    expect(screen.queryByLabelText('Flow 小地图')).not.toBeInTheDocument()
  })

  it('does not claim there is a result when playback has caught up but the run is still active', () => {
    const runningEvents = events.slice(0, -1)
    render(<AgentFlowCanvas events={runningEvents} graph={graph} />)

    fireEvent.click(screen.getByRole('button', { name: /跳到实时/ }))

    expect(screen.getByRole('button', { name: '等待结果' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: '跳到结果' })).not.toBeInTheDocument()
    expect(screen.getByText('Flow 构建中')).toBeInTheDocument()
  })
})
