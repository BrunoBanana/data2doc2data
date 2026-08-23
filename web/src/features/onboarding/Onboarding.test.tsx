import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Onboarding } from './Onboarding'

const providers = [
  { provider_id: 'codex', kind: 'local_cli', state: 'ready', capabilities: ['streaming'], detail: null, reconnect_hint: null },
  { provider_id: 'workbuddy', kind: 'local_cli', state: 'auth_required', capabilities: ['streaming'], detail: '授权失效', reconnect_hint: '请重新登录' },
]

describe('onboarding', () => {
  it('allows model-free task creation without blocking on a provider', async () => {
    const createTask = vi.fn().mockResolvedValue({ task_id: 'task-1', title: '收入复盘', goal: '解释收入下降' })
    render(<Onboarding providers={providers} createTask={createTask} onComplete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: '暂时跳过' }))
    fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '收入复盘' } })
    fireEvent.change(screen.getByLabelText('业务目标'), { target: { value: '解释收入下降' } })
    fireEvent.click(screen.getByRole('button', { name: '创建分析任务' }))

    expect(createTask).toHaveBeenCalledWith('收入复盘', '解释收入下降')
    expect(await screen.findByText('任务已创建')).toBeInTheDocument()
  })

  it('shows reconnect guidance instead of pretending an expired provider is usable', () => {
    render(<Onboarding providers={providers} createTask={vi.fn()} onComplete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /WorkBuddy/ }))

    expect(screen.getByRole('alert')).toHaveTextContent('请重新登录')
  })
})
