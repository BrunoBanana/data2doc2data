import { useState } from 'react'

interface ReportExportProps {
  download: () => Promise<{ blob: Blob; filename: string }>
}

export function ReportExport({ download }: ReportExportProps) {
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  async function save() {
    setBusy(true)
    setNotice('')
    try {
      const artifact = await download()
      const url = URL.createObjectURL(artifact.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = artifact.filename
      anchor.click()
      URL.revokeObjectURL(url)
      setNotice('HTML 报告已生成，可离线打开或打印。')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '报告生成失败。')
    } finally {
      setBusy(false)
    }
  }

  return <div className="report-export"><button className="button button--secondary" type="button" disabled={busy} onClick={save}>{busy ? '正在生成…' : '下载 HTML 报告'}</button>{notice && <span role="status">{notice}</span>}</div>
}
