import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TaskHome } from './TaskHome'

describe('task home', () => {
  it('renders recent tasks and opens the selected task', () => {
    const openTask = vi.fn()
    render(
      <TaskHome
        tasks={[{ task_id: 'task-1', title: '收入复盘', goal: '解释收入下降', status: 'active', snapshot_refs: [] }]}
        onOpenTask={openTask}
        onCreateTask={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /收入复盘/ }))
    expect(openTask).toHaveBeenCalledWith('task-1')
  })

  it('offers business templates when there are no tasks', () => {
    render(<TaskHome tasks={[]} onOpenTask={vi.fn()} onCreateTask={vi.fn()} />)
    expect(screen.getByText('异常调查')).toBeInTheDocument()
    expect(screen.getByText('周期复盘')).toBeInTheDocument()
  })
})
