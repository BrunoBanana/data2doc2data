import { ChangeEvent, FormEvent, useState } from 'react'

import type { PreparedSource, SourcePreview } from '../../contracts/workbench'

type SourceMode = 'path' | 'upload' | 'api'

interface DataImportProps {
  previewLocalPath: (path: string) => Promise<SourcePreview>
  uploadFile?: (file: File) => Promise<PreparedSource>
  previewApi?: (url: string) => Promise<PreparedSource>
  applyImport: (path: string, plan: Record<string, string>) => Promise<void>
}

export function DataImport({ previewLocalPath, uploadFile, previewApi, applyImport }: DataImportProps) {
  const [mode, setMode] = useState<SourceMode>('path')
  const [value, setValue] = useState('')
  const [sourcePath, setSourcePath] = useState('')
  const [result, setResult] = useState<SourcePreview | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  function changeMode(nextMode: SourceMode) {
    setMode(nextMode)
    setValue('')
    setSourcePath('')
    setResult(null)
    setNotice('')
  }

  async function prepare(event: FormEvent) {
    event.preventDefault()
    if (mode === 'upload') return
    setBusy(true)
    try {
      if (mode === 'path') {
        setResult(await previewLocalPath(value.trim()))
        setSourcePath(value.trim())
      } else if (previewApi) {
        const prepared = await previewApi(value.trim())
        setResult(prepared)
        setSourcePath(prepared.source_path)
      }
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '数据预览失败。')
    } finally {
      setBusy(false)
    }
  }

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file || !uploadFile) return
    setBusy(true)
    try {
      const prepared = await uploadFile(file)
      setResult(prepared)
      setSourcePath(prepared.source_path)
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '文件上传失败。')
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!result?.suggestion || !sourcePath) return
    setBusy(true)
    try {
      await applyImport(sourcePath, result.suggestion)
      setNotice('数据已导入，正在生成画像。')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '数据导入失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="data-import" aria-labelledby="data-import-title">
      <p className="eyebrow">STEP 3 OF 3</p><h2 id="data-import-title">接入业务数据</h2>
      <div className="source-tabs" aria-label="数据源类型">
        <button type="button" aria-pressed={mode === 'path'} onClick={() => changeMode('path')}>本地路径</button>
        {uploadFile && <button type="button" aria-pressed={mode === 'upload'} onClick={() => changeMode('upload')}>上传文件</button>}
        {previewApi && <button type="button" aria-pressed={mode === 'api'} onClick={() => changeMode('api')}>HTTPS API</button>}
      </div>
      {mode === 'upload' ? (
        <label className="file-drop">选择数据文件<input aria-label="选择数据文件" type="file" accept=".csv,.tsv,.json,.xlsx,.xlsm" onChange={selectFile} disabled={busy} /><span>CSV、JSON 或 Excel，原始文件只在本机处理</span></label>
      ) : (
        <form onSubmit={prepare}>
          <label>{mode === 'path' ? '本地数据文件路径' : 'HTTPS API 地址'}<input aria-label={mode === 'path' ? '本地数据文件路径' : 'HTTPS API 地址'} value={value} onChange={(event) => setValue(event.target.value)} placeholder={mode === 'path' ? '/Users/name/data.csv' : 'https://api.example.com/metrics'} /></label>
          <button className="button button--secondary" type="submit" disabled={busy || !value.trim()}>{mode === 'path' ? '预览数据' : '获取快照'}</button>
        </form>
      )}
      {result && <div className="mapping-preview"><strong>{result.preview.row_count ?? '未知'} 条记录</strong><span>{result.preview.format.toUpperCase()} · {result.preview.fields.length} 个字段</span><div>{result.preview.fields.map((field) => <code key={field}>{field}</code>)}</div><button className="button button--primary" type="button" disabled={!result.suggestion || busy} onClick={apply}>确认映射并导入</button></div>}
      {notice && <p role="alert" className="form-notice">{notice}</p>}
    </section>
  )
}
