import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DataImport } from './DataImport'

describe('data import', () => {
  it('previews a local path and asks for mapping confirmation', async () => {
    const preview = vi.fn().mockResolvedValue({
      preview: { format: 'csv', fields: ['date', 'metric', 'value'], row_count: 12, sample_rows: [] },
      suggestion: { format: 'csv', date_field: 'date', metric_field: 'metric', value_field: 'value' },
    })
    render(<DataImport previewLocalPath={preview} applyImport={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('本地数据文件路径'), { target: { value: '/tmp/metrics.csv' } })
    fireEvent.click(screen.getByRole('button', { name: '预览数据' }))

    expect(await screen.findByText('12 条记录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认映射并导入' })).toBeInTheDocument()
  })

  it('offers browser upload and HTTPS API sources', () => {
    render(<DataImport previewLocalPath={vi.fn()} uploadFile={vi.fn()} previewApi={vi.fn()} applyImport={vi.fn()} />)

    expect(screen.getByRole('button', { name: '上传文件' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'HTTPS API' })).toBeInTheDocument()
  })
})
