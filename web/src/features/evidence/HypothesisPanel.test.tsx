import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { HypothesisPanel } from './HypothesisPanel'

describe('HypothesisPanel', () => {
  it('runs explicit hypotheses as structured bounded input', async () => {
    const onRun = vi.fn().mockResolvedValue(undefined)
    render(<HypothesisPanel onRun={onRun} disabled={false} />)

    fireEvent.change(screen.getByLabelText('待验证假设'), { target: { value: '价格调整影响收入' } })
    fireEvent.click(screen.getByRole('button', { name: '运行证据分析' }))

    expect(onRun).toHaveBeenCalledWith(['价格调整影响收入'])
  })
})
