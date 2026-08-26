import { describe, expect, it } from 'vitest'

import type { RunEvent } from '../../contracts/run-events'
import { emptyFlowProjection, projectFlowEvent, projectFlowEvents } from './flow-projection'

function event(sequence: number, kind: RunEvent['kind'], summary: Record<string, unknown> = {}, artifactRefs: string[] = []): RunEvent {
  return {
    contract_version: 1,
    run_id: 'run-live',
    sequence,
    kind,
    phase: 'cross-reasoning',
    summary,
    artifact_refs: artifactRefs,
    created_at: `2026-08-24T00:00:${String(sequence).padStart(2, '0')}Z`,
  }
}

describe('flow event projection', () => {
  it('starts empty and grows only when persisted graph mutations arrive', () => {
    let projection = emptyFlowProjection()
    projection = projectFlowEvent(projection, event(1, 'run.started'))
    projection = projectFlowEvent(projection, event(2, 'plan.created', { plan_id: 'plan-1' }))
    projection = projectFlowEvent(projection, event(3, 'tool.started', { step_id: 'profile', tool: 'profile_data' }))
    expect(projection.nodes).toEqual([])

    projection = projectFlowEvent(projection, event(4, 'node.added', {
      node_id: 'data-signal', node_kind: 'data_signal', label: '本地数据画像', status: 'verified',
    }, ['data-signal', 'dashboard-1']))
    expect(projection.nodes.map((node) => node.id)).toEqual(['data-signal'])
    expect(projection.nodes[0]).toMatchObject({ lane: 'compute', artifactRef: 'dashboard-1' })
  })

  it('updates tool activity, retains revised branches, activates edges, and converges at the report', () => {
    const events = [
      event(1, 'node.added', { node_id: 'claim-a', node_kind: 'claim', label: '增长来自产品改版', status: 'pending' }),
      event(2, 'node.added', { node_id: 'claim-b', node_kind: 'claim', label: '增长来自渠道扩量', status: 'pending' }),
      event(3, 'node.added', { node_id: 'validation-1', node_kind: 'validation', label: '交叉核验', status: 'insufficient' }),
      event(4, 'edge.added', { edge_id: 'edge-a', source: 'claim-a', target: 'validation-1', relationship: 'tests' }),
      event(5, 'edge.activated', { edge_id: 'edge-a', source: 'claim-a', target: 'validation-1', relationship: 'tests' }),
      event(6, 'plan.revised', { revision: 1, reason: '新增反证分支' }),
      event(7, 'edge.added', { edge_id: 'edge-conflict', source: 'claim-a', target: 'claim-b', relationship: 'contradicts' }),
      event(8, 'conflict.detected', { left_claim_id: 'claim-a', right_claim_id: 'claim-b' }, ['edge-conflict']),
      event(9, 'tool.progress', { step_id: 'align', tool: 'align_evidence', progress: 0.7 }),
      event(10, 'node.updated', { node_id: 'validation-1', status: 'supported', label: '交叉核验完成' }),
      event(11, 'report.generated', { filename: 'report.html', sha256: 'a'.repeat(64) }),
    ]

    const projection = projectFlowEvents(events)

    expect(projection.nodes.map((node) => node.id)).toEqual(['claim-a', 'claim-b', 'validation-1'])
    expect(projection.nodes.find((node) => node.id === 'validation-1')).toMatchObject({ status: 'supported', label: '交叉核验完成' })
    expect(projection.edges.map((edge) => edge.id)).toEqual(['edge-a', 'edge-conflict'])
    expect(projection.activeEdgeIds).toContain('edge-conflict')
    expect(projection.conflictCount).toBe(1)
    expect(projection.planRevisionCount).toBe(1)
    expect(projection.activeTool).toMatchObject({ stepId: 'align', name: 'align_evidence', state: 'running' })
    expect(projection.converged).toBe(true)
    expect(projection.report).toMatchObject({ filename: 'report.html' })
  })

  it('does not project private or raw event payloads into nodes', () => {
    const projection = projectFlowEvents([
      event(1, 'tool.result', { tool: 'query_data', row_count: 120, result: 'bounded summary' }),
    ])

    expect(JSON.stringify(projection)).not.toContain('raw_rows')
    expect(projection.nodes).toEqual([])
  })

  it('projects real communication handoffs while keeping legacy events compatible', () => {
    const protocolEvent = {
      ...event(1, 'tool.started', { step_id: 'profile', tool: 'profile_data' }),
      communication: {
        protocol_version: 1,
        message_id: 'msg-run-live-1',
        trace_id: 'run-live',
        causation_id: null,
        sender: 'orchestrator',
        receiver: 'tool.profile_data',
        attempt: 2,
        idempotency_key: 'delivery-abc',
        deadline_at: '2026-08-24T00:01:00Z',
      },
    } as unknown as RunEvent

    expect(projectFlowEvents([protocolEvent]).communication).toEqual({
      traceId: 'run-live',
      messageId: 'msg-run-live-1',
      sender: 'orchestrator',
      receiver: 'tool.profile_data',
      attempt: 2,
      idempotencyKey: 'delivery-abc',
      deadlineAt: '2026-08-24T00:01:00Z',
    })
    expect(projectFlowEvents([event(1, 'run.started')]).communication).toBeNull()
  })

  it('draws planned tool steps and their dependencies before evidence results exist', () => {
    const projection = projectFlowEvents([
      event(1, 'plan.created', { plan_id: 'plan-1' }),
      event(2, 'step.added', { step_id: 'inspect', tool: 'inspect_sources', purpose: '识别输入材料', dependencies: [] }),
      event(3, 'step.added', { step_id: 'profile', tool: 'profile_data', purpose: '生成本地数据画像', dependencies: ['inspect'] }),
      event(4, 'step.started', { step_id: 'inspect', tool: 'inspect_sources' }),
      event(5, 'tool.started', { step_id: 'inspect', tool: 'inspect_sources' }),
      event(6, 'tool.result', { step_id: 'inspect', tool: 'inspect_sources', duration_ms: 12 }),
      event(7, 'step.completed', { step_id: 'inspect', tool: 'inspect_sources', duration_ms: 12 }),
    ])

    expect(projection.nodes.map((node) => node.id)).toEqual(['inspect', 'profile'])
    expect(projection.nodes.find((node) => node.id === 'inspect')).toMatchObject({ status: 'verified', kind: 'tool_step' })
    expect(projection.edges).toContainEqual(expect.objectContaining({ source: 'inspect', target: 'profile', relationship: 'derived_from' }))
  })

  it('projects persisted rounds and links a revision to the prior artifact', () => {
    const projection = projectFlowEvents([
      event(1, 'cycle.started', { cycle_id: 'cycle-1', max_rounds: 3 }),
      event(2, 'round.planned', { cycle_id: 'cycle-1', round_number: 1, tool: 'detect_anomalies', rationale_summary: '检查异常', prior_artifact_refs: [] }),
      event(3, 'round.started', { cycle_id: 'cycle-1', round_number: 1, tool: 'detect_anomalies' }),
      event(4, 'artifact.created', { cycle_id: 'cycle-1', round_number: 1, artifact_ref: 'artifact-1', method: 'detect_anomalies' }, ['artifact-1']),
      event(5, 'round.completed', { cycle_id: 'cycle-1', round_number: 1 }),
      event(6, 'round.planned', { cycle_id: 'cycle-1', round_number: 2, tool: 'detect_change_points', rationale_summary: '根据异常检查变化点', prior_artifact_refs: ['artifact-1'] }, ['artifact-1']),
      event(7, 'artifact.created', { cycle_id: 'cycle-1', round_number: 2, artifact_ref: 'artifact-2', method: 'detect_change_points' }, ['artifact-2']),
    ])

    expect(projection.nodes.map((node) => node.id)).toEqual(['round-1', 'artifact-1', 'round-2', 'artifact-2'])
    expect(projection.nodes.find((node) => node.id === 'round-1')?.label).toBe('第 1 轮 · 检查异常')
    expect(projection.nodes.find((node) => node.id === 'artifact-1')?.label).toBe('稳健异常检测')
    expect(projection.edges).toContainEqual(expect.objectContaining({ source: 'artifact-1', target: 'round-2' }))
    expect(projection.edges).toContainEqual(expect.objectContaining({ source: 'round-2', target: 'artifact-2' }))
  })

  it('makes connected-agent orchestration visible on the public flow node', () => {
    const projection = projectFlowEvents([
      event(1, 'round.planned', {
        round_number: 1, tool: 'detect_anomalies', rationale_summary: '检查异常', prior_artifact_refs: [], planner: 'connected_agent',
      }),
    ])

    expect(projection.nodes[0].label).toBe('Agent 规划 · 第 1 轮 · 检查异常')
  })
})
