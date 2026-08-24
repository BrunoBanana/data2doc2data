import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReportExport } from './ReportExport'

describe('ReportExport', () => {
  it('downloads the authenticated standalone HTML artifact', async () => {
    const download = vi.fn(async () => ({ blob: new Blob(['<!doctype html>'], { type: 'text/html' }), filename: 'analysis.html' }))
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(document.body.contains(this)).toBe(true)
      expect(this.download).toBe('analysis.html')
    })
    render(<ReportExport download={download} />)

    fireEvent.click(screen.getByRole('button', { name: '下载 HTML 报告' }))
    await waitFor(() => expect(download).toHaveBeenCalledOnce())
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(document.querySelector('a[download="analysis.html"]')).toBeNull()
    expect(revokeObjectURL).not.toHaveBeenCalled()

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:report'))

    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
    click.mockRestore()
  })
})
