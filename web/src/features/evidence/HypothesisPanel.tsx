import { FormEvent, useState } from 'react'

export function HypothesisPanel({ onRun, disabled }: { onRun: (hypotheses: string[]) => Promise<void>; disabled: boolean }) {
  const [value, setValue] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    const hypotheses = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).slice(0, 20)
    setBusy(true)
    try { await onRun(hypotheses); setNotice('分析运行已完成，可检查证据链和核验状态。') }
    catch (error) { setNotice(error instanceof Error ? error.message : '分析运行失败。') }
    finally { setBusy(false) }
  }
  return <section className="hypothesis-panel" aria-labelledby="hypothesis-title"><div><p className="eyebrow">TESTABLE HYPOTHESES</p><h2 id="hypothesis-title">提出待验证假设</h2><p>每行一条。系统只记录结构化假设和验证结果，不展示或保存模型私有思维链。</p></div><form onSubmit={submit}><label>待验证假设<textarea aria-label="待验证假设" rows={3} maxLength={4000} value={value} onChange={(event) => setValue(event.target.value)} placeholder="例如：价格调整导致了收入下降" /></label><button className="button button--primary" type="submit" disabled={disabled || busy}>{busy ? '正在运行…' : '运行证据分析'}</button></form>{notice && <p className="form-notice" role="alert">{notice}</p>}</section>
}
