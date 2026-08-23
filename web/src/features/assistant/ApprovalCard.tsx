import { useState } from 'react'

import type { AgentApproval } from '../../contracts/workbench'

interface ApprovalCardProps {
  approval: AgentApproval
  decide: (approved: boolean) => Promise<void>
}

export function ApprovalCard({ approval, decide }: ApprovalCardProps) {
  const [decision, setDecision] = useState<'approved' | 'rejected' | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function choose(approved: boolean) {
    setBusy(true)
    setError('')
    try {
      await decide(approved)
      setDecision(approved ? 'approved' : 'rejected')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法提交审批决定。')
    } finally {
      setBusy(false)
    }
  }

  return <article className="assistant-approval" role="alert" data-decision={decision || undefined}>
    <div><span className="approval-pulse" aria-hidden="true" /><strong>等待批准</strong></div>
    <dl>
      <dt>操作</dt><dd>{approval.operation || '未知操作'}</dd>
      {approval.command && <><dt>命令</dt><dd><code>{approval.command}</code></dd></>}
      {approval.target_paths?.length ? <><dt>目标</dt><dd>{approval.target_paths.join('、')}</dd></> : null}
      {approval.diff && <><dt>差异</dt><dd><pre>{approval.diff}</pre></dd></>}
    </dl>
    {decision ? <p className="approval-result">{decision === 'approved' ? '已批准' : '已拒绝'}</p> : <div className="approval-actions"><button className="button button--primary" type="button" disabled={busy} onClick={() => choose(true)}>批准</button><button className="button button--danger" type="button" disabled={busy} onClick={() => choose(false)}>拒绝</button></div>}
    {error && <p role="alert" className="form-notice">{error}</p>}
  </article>
}
