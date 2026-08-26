import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DocumentImport } from './DocumentImport'

describe('DocumentImport', () => {
  it('imports optional local document paths with explicit confirmation', async () => {
    const importDocuments = vi.fn().mockResolvedValue(undefined)
    render(<DocumentImport importDocuments={importDocuments} />)

    fireEvent.change(screen.getByLabelText('文档路径'), { target: { value: '/tmp/plan.md\n/tmp/review.txt' } })
    fireEvent.click(screen.getByRole('button', { name: '导入文本材料' }))

    expect(importDocuments).toHaveBeenCalledWith(['/tmp/plan.md', '/tmp/review.txt'])
    expect(await screen.findByRole('alert')).toHaveTextContent('已完成文本预处理')
  })
})
