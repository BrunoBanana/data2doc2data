import { FormEvent, useState } from 'react'

import type { AnalysisTask, ProviderConnection } from '../../contracts/workbench'

interface OnboardingProps {
  providers: ProviderConnection[]
  createTask: (title: string, goal: string) => Promise<AnalysisTask>
  onComplete: (task: AnalysisTask) => void
}

const providerName = (id: string) => id === 'workbuddy' ? '腾讯 WorkBuddy / CodeBuddy' : id === 'codex' ? 'Codex CLI' : id

export function Onboarding({ providers, createTask, onComplete }: OnboardingProps) {
  const [step, setStep] = useState<'provider' | 'task'>('provider')
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  function chooseProvider(provider: ProviderConnection) {
    if (provider.state === 'ready' || provider.state === 'connected') {
      setNotice(`${providerName(provider.provider_id)} 已可用`)
      setStep('task')
      return
    }
    setNotice(provider.reconnect_hint || provider.detail || '当前连接不可用，请检查本地配置。')
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim() || !goal.trim()) {
      setNotice('请填写任务名称和业务目标。')
      return
    }
    setBusy(true)
    try {
      const task = await createTask(title.trim(), goal.trim())
      setNotice('任务已创建')
      onComplete(task)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '任务创建失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="onboarding" aria-labelledby="onboarding-title">
      <div className="onboarding-progress" aria-label="接入进度">
        <span className="is-active">1 连接智能能力</span><span>2 创建任务</span><span>3 接入数据</span>
      </div>
      {step === 'provider' ? (
        <div className="onboarding-panel">
          <p className="eyebrow">STEP 1 OF 3</p>
          <h1 id="onboarding-title">先选择你的分析协作者</h1>
          <p>原始数据仍在本机计算；助手只接收有界统计、必要样例和相关证据。</p>
          <div className="provider-grid">
            {providers.filter((provider) => provider.kind !== 'none').map((provider) => (
              <button key={provider.provider_id} type="button" className="provider-card" onClick={() => chooseProvider(provider)}>
                <strong>{providerName(provider.provider_id)}</strong>
                <span>{provider.state === 'ready' ? '可连接' : provider.state === 'connected' ? '已连接' : '需要处理'}</span>
                <small>{provider.detail || '本地 CLI，可流式分析并请求操作审批。'}</small>
              </button>
            ))}
          </div>
          <button className="button button--quiet" type="button" onClick={() => setStep('task')}>暂时跳过</button>
        </div>
      ) : (
        <form className="onboarding-panel task-form" onSubmit={submit}>
          <p className="eyebrow">STEP 2 OF 3</p>
          <h1 id="onboarding-title">定义这次业务分析</h1>
          <label>任务名称<input aria-label="任务名称" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} /></label>
          <label>业务目标<textarea aria-label="业务目标" value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={2000} rows={4} /></label>
          <div className="template-row" aria-label="任务模板">
            <button type="button" onClick={() => { setTitle('异常调查'); setGoal('定位核心指标异常的范围、证据和可能原因') }}>异常调查</button>
            <button type="button" onClick={() => { setTitle('周期复盘'); setGoal('总结本周期业务表现、变化与风险') }}>周期复盘</button>
            <button type="button" onClick={() => { setTitle('策略核验'); setGoal('用数据验证策略文档中的目标与假设') }}>策略核验</button>
          </div>
          <button className="button button--primary" type="submit" disabled={busy}>{busy ? '正在创建…' : '创建分析任务'}</button>
        </form>
      )}
      {notice && <p className="form-notice" role="alert">{notice}</p>}
    </section>
  )
}
