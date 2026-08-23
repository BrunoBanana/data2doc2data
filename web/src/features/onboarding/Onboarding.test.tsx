import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Onboarding } from './Onboarding'
import type { FlagshipCaseSummary } from '../../contracts/workbench'

const cases: FlagshipCaseSummary[] = [
  { id: 'saas-growth-retention', title: '增长提速、留存承压', summary: '增长与留存背离', business_question: '增长是否健康？', learning_objective: '验证增长质量', metric_count: 8, record_count: 208, document_count: 4, synthetic: true as const, time_range: { start: '2026-01-05', end: '2026-06-29', grain: 'week' } },
  { id: 'retail-promotion-fulfillment', title: '大促增收、利润与履约恶化', summary: '规模与利润背离', business_question: '大促是否健康？', learning_objective: '验证促销质量', metric_count: 10, record_count: 260, document_count: 5, synthetic: true as const, time_range: { start: '2026-01-05', end: '2026-06-29', grain: 'week' } },
]

const providers = [
  { provider_id: 'codex', kind: 'local_cli', state: 'ready', capabilities: ['streaming'], detail: null, reconnect_hint: null },
  { provider_id: 'workbuddy', kind: 'local_cli', state: 'auth_required', capabilities: ['streaming'], detail: '授权失效', reconnect_hint: '请重新登录' },
]

describe('onboarding', () => {
  it('allows model-free task creation without blocking on a provider', async () => {
    const createTask = vi.fn().mockResolvedValue({ task_id: 'task-1', title: '收入复盘', goal: '解释收入下降' })
    render(<Onboarding providers={providers} cases={cases} createTask={createTask} loadCase={vi.fn()} onComplete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: '暂时跳过' }))
    fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '收入复盘' } })
    fireEvent.change(screen.getByLabelText('业务目标'), { target: { value: '解释收入下降' } })
    fireEvent.click(screen.getByRole('button', { name: '创建分析任务' }))

    expect(createTask).toHaveBeenCalledWith('收入复盘', '解释收入下降')
    expect(await screen.findByText('任务已创建')).toBeInTheDocument()
  })

  it('shows reconnect guidance instead of pretending an expired provider is usable', () => {
    render(<Onboarding providers={providers} cases={cases} createTask={vi.fn()} loadCase={vi.fn()} onComplete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /WorkBuddy/ }))

    expect(screen.getByRole('alert')).toHaveTextContent('请重新登录')
  })

  it('loads either complete synthetic case in one click', async () => {
    const loaded = { task_id: 'task-case', title: cases[0].title, goal: cases[0].business_question, status: 'active', snapshot_refs: [] }
    const loadCase = vi.fn().mockResolvedValue(loaded)
    const onComplete = vi.fn()
    render(<Onboarding providers={providers} cases={cases} createTask={vi.fn()} loadCase={loadCase} onComplete={onComplete} />)

    expect(screen.getByRole('heading', { name: '完整示例案例' })).toBeInTheDocument()
    expect(screen.getByText('208 条指标记录 · 8 个指标 · 4 份文档')).toBeInTheDocument()
    expect(screen.getByText('260 条指标记录 · 10 个指标 · 5 份文档')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '加载案例：增长提速、留存承压' }))

    expect(loadCase).toHaveBeenCalledWith('saas-growth-retention')
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(loaded))
  })
})
