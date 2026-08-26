import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TextDashboard } from './TextDashboard'

describe('TextDashboard', () => {
  it('separates extracted claims from verified conclusions', () => {
    render(<TextDashboard dashboard={{ corpus_id: 'corpus-1', document_count: 1, failure_count: 0, duplicate_count: 0, topics: ['收入'], entities: ['华东区'], claims: [{ claim_id: 'claim-1', text: '收入将持续增长', status: 'pending', citation: { document: 'plan.md', sha256: 'a'.repeat(64), start_line: 2, end_line: 2, excerpt: '主张：收入将持续增长' }, conflicts_with: [] }] }} />)

    expect(screen.getByText('收入')).toBeInTheDocument()
    expect(screen.getByText('华东区')).toBeInTheDocument()
    expect(screen.getByText('待数据核验')).toBeInTheDocument()
    expect(screen.getByText('plan.md · 第 2 行')).toBeInTheDocument()
  })
})
