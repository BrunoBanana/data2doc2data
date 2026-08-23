import { useState } from 'react'

import type { AnalysisRunResult, RunHistoryItem } from '../../contracts/run-events'

interface RunHistoryProps {
  runs: RunHistoryItem[]
  loadRun: (runId: string) => Promise<AnalysisRunResult>
  retryRun: (runId: string, idempotencyKey: string) => Promise<AnalysisRunResult>
  onReplay: (result: AnalysisRunResult) => void
}

export function RunHistory({ runs, loadRun, retryRun, onReplay }: RunHistoryProps) {
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  async function replay(runId: string) {
    setBusy(runId)
    try {
      onReplay(await loadRun(runId))
      setNotice('已载入不可变运行记录。')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '运行回放加载失败。')
    } finally {
      setBusy('')
    }
  }

  async function retry(runId: string) {
    setBusy(runId)
    const key = `retry-${runId}-${Date.now().toString(36)}`
    try {
      onReplay(await retryRun(runId, key))
      setNotice('已从当前锁定资产创建新运行；原记录保持不变。')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '安全重试失败。')
    } finally {
      setBusy('')
    }
  }

  return <section className="run-history" aria-labelledby="run-history-title">
    <div className="dashboard-heading"><div><p className="eyebrow">IMMUTABLE HISTORY</p><h2 id="run-history-title">运行历史</h2></div><span>{runs.length} 次运行</span></div>
    {runs.length ? <div className="run-history-list">{runs.map((run) => <article key={run.run_id} className={`run-history-card run-history-card--${run.status}`}>
      <header><div><strong>{statusLabel(run.status)}</strong><code>{run.run_id}</code></div><time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time></header>
      <div className="run-history-meta"><span>{run.event_count} 个事件</span>{run.failure_type && <span className="failure-type">{run.failure_type}</span>}{run.stale && <span className="stale-warning">快照已变化</span>}</div>
      <p>{run.stale ? '回放仍使用当时的不可变快照；重试将使用任务当前锁定资产。' : '该运行与任务当前锁定资产一致。'}</p>
      <div className="run-history-actions"><button className="button button--secondary" type="button" disabled={busy === run.run_id} aria-label={`回放 ${run.run_id}`} onClick={() => replay(run.run_id)}>回放过程</button><button className="button button--quiet" type="button" disabled={busy === run.run_id} aria-label={`安全重试 ${run.run_id}`} onClick={() => retry(run.run_id)}>安全重试</button></div>
    </article>)}</div> : <div className="empty-workspace"><p className="eyebrow">NO RUNS</p><h2>还没有运行记录</h2><p>运行一次分析后，事件、证据图和快照引用会保存到这里。</p></div>}
    {notice && <p className="form-notice" role="status">{notice}</p>}
  </section>
}

function statusLabel(status: RunHistoryItem['status']) {
  return ({ queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', interrupted: '已停止' })[status]
}
