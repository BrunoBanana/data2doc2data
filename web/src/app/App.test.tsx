import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('analysis workbench shell', () => {
  it('keeps tasks and analysis as the primary workspace', () => {
    render(<App />)

    expect(screen.getByRole('banner')).toHaveTextContent('Data2Doc2Data')
    expect(screen.getByRole('navigation', { name: '任务与资产' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveTextContent('业务分析工作台')
    expect(screen.getByRole('complementary', { name: 'AI 助手' })).toBeInTheDocument()
  })

  it('offers deterministic analysis when no assistant is connected', () => {
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('未连接助手')
    expect(screen.getByText('仍可使用本地数据画像与确定性 Dashboard')).toBeInTheDocument()
  })
})
