import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AgentEvent, AgentProviderStatus, AgentSession, AnalysisTask } from '../../contracts/workbench'
import { AssistantDrawer } from './AssistantDrawer'

const task: AnalysisTask = {
  task_id: 'task-1', title: '留存异常调查', goal: '定位留存下降原因', status: 'active',
  snapshot_refs: [{ kind: 'dataset', snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }],
}
const agents: AgentProviderStatus[] = [
  { name: 'codex', available: true, connected: false, version: '1', authenticated: true, compatible: true, detail: null },
  { name: 'workbuddy', available: true, connected: false, version: '2', authenticated: true, compatible: true, detail: null },
]
const session: AgentSession = { id: 'session-1', provider: 'workbuddy', workspace: '/private/workspace', permission_mode: 'collaborative', resumed: false }

function setup() {
  let emit: ((event: AgentEvent, eventId: number) => void) | null = null
  const api = {
    createSession: vi.fn(async () => session),
    sendMessage: vi.fn(async () => undefined),
    interrupt: vi.fn(async () => undefined),
    decideApproval: vi.fn(async () => undefined),
    openEventStream: vi.fn((_id: string, _after: number, onEvent: (event: AgentEvent, eventId: number) => void) => {
      emit = onEvent
      return vi.fn()
    }),
  }
  render(<AssistantDrawer task={task} agents={agents} {...api} />)
  return { api, emit: (event: AgentEvent, id = 1) => emit?.(event, id) }
}

describe('AssistantDrawer', () => {
  it('prefers WorkBuddy and sends bounded task identity with the message', async () => {
    const { api } = setup()
    expect(screen.getByLabelText('本地助手')).toHaveValue('workbuddy')
    fireEvent.click(screen.getByRole('button', { name: '连接助手' }))
    await screen.findByText('腾讯 WorkBuddy / CodeBuddy 已连接')
    fireEvent.change(screen.getByLabelText('发送给助手'), { target: { value: '分析数据有多少' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => expect(api.sendMessage).toHaveBeenCalledWith('session-1', '分析数据有多少', 'task-1'))
    expect(screen.queryByText('/private/workspace')).not.toBeInTheDocument()
  })

  it('aggregates streamed assistant and operation deltas', async () => {
    const { emit } = setup()
    fireEvent.click(screen.getByRole('button', { name: '连接助手' }))
    await screen.findByText('腾讯 WorkBuddy / CodeBuddy 已连接')
    emit({ kind: 'message.delta', payload: { text: '# 结论\n' } }, 1)
    emit({ kind: 'message.delta', payload: { text: '> 留存下降' } }, 2)
    emit({ kind: 'plan.delta', payload: { text: '检查' } }, 3)
    emit({ kind: 'plan.delta', payload: { text: '分群' } }, 4)
    expect(await screen.findByRole('heading', { name: '结论' })).toBeInTheDocument()
    expect(screen.getByText('留存下降')).toBeInTheDocument()
    expect(screen.getByText('检查分群')).toBeInTheDocument()
  })

  it('pins approval requests and supports rejection and interrupt', async () => {
    const { api, emit } = setup()
    fireEvent.click(screen.getByRole('button', { name: '连接助手' }))
    await screen.findByText('腾讯 WorkBuddy / CodeBuddy 已连接')
    emit({ kind: 'plan.delta', payload: { text: '先检查证据' } }, 1)
    emit({ kind: 'approval.request', payload: { request_id: 'approval-1', operation: 'command', command: 'python -m unittest' } }, 2)
    const queue = screen.getByLabelText('助手操作')
    const approval = await within(queue).findByText('等待批准')
    expect(queue.firstElementChild).toContainElement(approval)
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    await waitFor(() => expect(api.decideApproval).toHaveBeenCalledWith('session-1', 'approval-1', false))
    expect(screen.getByText('已拒绝')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('发送给助手'), { target: { value: '继续' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => expect(screen.getByRole('button', { name: '停止当前任务' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '停止当前任务' }))
    await waitFor(() => expect(api.interrupt).toHaveBeenCalledWith('session-1'))
  })

  it('renders provider markup as inert text', async () => {
    const { emit } = setup()
    fireEvent.click(screen.getByRole('button', { name: '连接助手' }))
    await screen.findByText('腾讯 WorkBuddy / CodeBuddy 已连接')
    emit({ kind: 'message.delta', payload: { text: '<script>window.pwned=true</script> **安全文本**' } }, 1)
    expect(await screen.findByText(/<script>window\.pwned=true<\/script>/)).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })

  it('shows reconnecting and recovered provider states without ending the session', async () => {
    const { emit } = setup()
    fireEvent.click(screen.getByRole('button', { name: '连接助手' }))
    await screen.findByText('腾讯 WorkBuddy / CodeBuddy 已连接')

    emit({ kind: 'provider.status', payload: { state: 'reconnecting' } }, 1)
    expect(await screen.findByText('助手连接正在恢复，当前会话会自动续接…')).toBeInTheDocument()
    emit({ kind: 'provider.status', payload: { state: 'connected' } }, 2)

    expect(await screen.findByText('助手连接已恢复。')).toBeInTheDocument()
    expect(screen.getByText('已连接')).toBeInTheDocument()
  })
})
