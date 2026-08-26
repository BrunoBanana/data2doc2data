import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { EvidenceGraphSpec, RunEvent } from '../../contracts/run-events'
import { RunPlayback } from './RunPlayback'

const events: RunEvent[] = [
  { contract_version: 1, run_id: 'run-1', sequence: 1, kind: 'run.started', phase: 'setup', summary: {}, artifact_refs: [], created_at: '2026-08-23T00:00:00Z' },
  { contract_version: 1, run_id: 'run-1', sequence: 2, kind: 'chart.spec.created', phase: 'dashboard', summary: { block_count: 3 }, artifact_refs: ['dashboard-1'], created_at: '2026-08-23T00:00:01Z' },
  { contract_version: 1, run_id: 'run-1', sequence: 3, kind: 'run.completed', phase: 'finish', summary: { status: 'completed' }, artifact_refs: [], created_at: '2026-08-23T00:00:02Z' },
]
const graph: EvidenceGraphSpec = { contract_version: 1, graph_id: 'graph-1', nodes: [
  { node_id: 'signal-1', kind: 'data_signal', label: '收入趋势', status: 'verified', artifact_ref: 'dashboard-1' },
], edges: [] }

afterEach(() => vi.useRealTimers())

describe('RunPlayback', () => {
  it('plays, pauses, seeks and synchronizes the active evidence artifact', () => {
    vi.useFakeTimers()
    render(<RunPlayback events={events} graph={graph} autoPlay={false} reducedMotionOverride={false} />)
    expect(screen.getByText('开始分析')).toBeInTheDocument()
    expect(screen.queryByText('生成 Dashboard')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '播放回放' }))
    act(() => vi.advanceTimersByTime(900))
    expect(screen.getByText('生成 Dashboard')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /收入趋势/ })).toHaveAttribute('data-active', 'true')
    fireEvent.click(screen.getByRole('button', { name: '暂停回放' }))

    fireEvent.change(screen.getByLabelText('回放进度'), { target: { value: '3' } })
    expect(screen.getByText('分析完成')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('回放速度'), { target: { value: '2' } })
    expect(screen.getByLabelText('回放速度')).toHaveValue('2')
  })

  it('reveals all persisted events immediately when reduced motion is requested', () => {
    render(<RunPlayback events={events} graph={graph} reducedMotionOverride />)
    expect(screen.getByText('分析完成')).toBeInTheDocument()
    expect(screen.getByText('已按减少动态效果设置直接展示全部事件')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '播放回放' })).toBeDisabled()
  })

  it('labels the surface as an audit replay rather than private reasoning', () => {
    render(<RunPlayback events={events} graph={graph} autoPlay={false} />)
    expect(screen.getByText('这是可审计事件回放，不是模型隐性思维过程。')).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('chain_of_thought')
  })
})
