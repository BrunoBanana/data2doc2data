import { describe, expect, it, vi } from 'vitest'

import type { AgentEvent, AnalysisTask } from '../../contracts/workbench'
import { requestConnectedFlowPlan } from './agent-flow-planner'

const task: AnalysisTask = {
  task_id: 'task-connected',
  title: '增长复盘',
  goal: '解释增长与留存背离',
  status: 'active',
  analysis_mode: 'connected',
  agent_provider: 'codex',
  snapshot_refs: [
    { kind: 'dataset', snapshot_id: 'data-1', sha256: 'a'.repeat(64) },
    { kind: 'document', snapshot_id: 'doc-1', sha256: 'b'.repeat(64) },
  ],
}

describe('requestConnectedFlowPlan', () => {
  it('collects an agent-authored plan before host execution', async () => {
    let onEvent: ((event: AgentEvent, eventId: number) => void) | undefined
    const close = vi.fn()
    const createSession = vi.fn().mockResolvedValue({ id: 'session-1', provider: 'codex', workspace: '/workspace', permission_mode: 'read_only', resumed: false })
    const sendMessage = vi.fn().mockResolvedValue(undefined)
    const openEventStream = vi.fn((_id, _after, callback) => { onEvent = callback; return close })

    const pending = requestConnectedFlowPlan({ task, createSession, sendMessage, openEventStream, timeoutMs: 1_000 })
    await vi.waitFor(() => expect(sendMessage).toHaveBeenCalledOnce())
    onEvent?.({ kind: 'plan.delta', payload: { text: '```json\n{"plan_id":"agent-plan","steps":[' } }, 1)
    onEvent?.({ kind: 'message.delta', payload: { text: '{"step_id":"inspect","tool":"inspect_sources","purpose":"识别输入","dependencies":[],"arguments":{}},{"step_id":"profile","tool":"profile_data","purpose":"计算画像","dependencies":["inspect"],"arguments":{}},{"step_id":"extract","tool":"extract_claims","purpose":"抽取主张","dependencies":["inspect"],"arguments":{}},{"step_id":"align","tool":"align_evidence","purpose":"交叉验证","dependencies":["profile","extract"],"arguments":{}}]}\n```' } }, 2)
    onEvent?.({ kind: 'turn.completed', payload: {} }, 3)

    const plan = await pending
    expect(plan.plan_id).toBe('agent-plan')
    expect(plan.steps[0]).toMatchObject({ tool: 'inspect_sources' })
    expect(createSession).toHaveBeenCalledWith('codex', 'read_only')
    expect(sendMessage.mock.calls[0][1]).toContain('不得读取或返回原始记录')
    expect(close).toHaveBeenCalledOnce()
  })

  it('does not silently replace an invalid agent response with a Demo plan', async () => {
    let onEvent: ((event: AgentEvent, eventId: number) => void) | undefined
    const pending = requestConnectedFlowPlan({
      task,
      createSession: vi.fn().mockResolvedValue({ id: 'session-1', provider: 'codex', workspace: '/workspace', permission_mode: 'read_only', resumed: false }),
      sendMessage: vi.fn().mockResolvedValue(undefined),
      openEventStream: vi.fn((_id, _after, callback) => { onEvent = callback; return vi.fn() }),
      timeoutMs: 1_000,
    })
    await vi.waitFor(() => expect(onEvent).toBeTypeOf('function'))
    onEvent?.({ kind: 'message.delta', payload: { text: '我建议先看看数据。' } }, 1)
    onEvent?.({ kind: 'turn.completed', payload: {} }, 2)

    await expect(pending).rejects.toThrow('Agent 未返回可执行的结构化 Flow 计划')
  })

  it('fails immediately when a read-only planning turn requests approval', async () => {
    let onEvent: ((event: AgentEvent, eventId: number) => void) | undefined
    const close = vi.fn()
    const pending = requestConnectedFlowPlan({
      task,
      createSession: vi.fn().mockResolvedValue({ id: 'session-1', provider: 'codex', workspace: '/workspace', permission_mode: 'read_only', resumed: false }),
      sendMessage: vi.fn().mockResolvedValue(undefined),
      openEventStream: vi.fn((_id, _after, callback) => { onEvent = callback; return close }),
      timeoutMs: 60_000,
    })
    await vi.waitFor(() => expect(onEvent).toBeTypeOf('function'))
    onEvent?.({ kind: 'approval.request', payload: { request_id: 'approval-1', operation: 'command' } }, 1)

    await expect(pending).rejects.toThrow('规划阶段不允许执行命令或读取文件')
    expect(close).toHaveBeenCalledOnce()
  })
})
