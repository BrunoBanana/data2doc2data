import { FormEvent, useState } from 'react'

export function DocumentImport({ importDocuments }: { importDocuments: (paths: string[]) => Promise<void> }) {
  const [value, setValue] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const paths = value.split(/\r?\n/).map((path) => path.trim()).filter(Boolean)
    if (!paths.length) return
    setBusy(true)
    try {
      await importDocuments(paths)
      setNotice('已完成文本预处理，可查看主题、实体与待核验主张。')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '文本材料导入失败。')
    } finally {
      setBusy(false)
    }
  }

  return <section className="document-import" aria-labelledby="document-import-title"><div><p className="eyebrow">OPTIONAL MATERIALS</p><h2 id="document-import-title">补充文本材料</h2><p>支持 Markdown / TXT；每行填写一个本地绝对路径。</p></div><form onSubmit={submit}><label>文档路径<textarea aria-label="文档路径" rows={3} value={value} onChange={(event) => setValue(event.target.value)} placeholder={'/Users/name/strategy.md\n/Users/name/review.txt'} /></label><button className="button button--secondary" type="submit" disabled={busy || !value.trim()}>{busy ? '正在预处理…' : '导入文本材料'}</button></form>{notice && <p className="form-notice" role="alert">{notice}</p>}</section>
}
