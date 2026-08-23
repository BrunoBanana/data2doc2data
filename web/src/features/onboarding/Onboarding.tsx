import { FormEvent, useState } from 'react'

import type { AnalysisTask, FlagshipCaseSummary, ProviderConnection } from '../../contracts/workbench'

interface OnboardingProps {
  providers: ProviderConnection[]
  cases: FlagshipCaseSummary[]
  createTask: (title: string, goal: string) => Promise<AnalysisTask>
  loadCase: (caseId: string) => Promise<AnalysisTask>
  onComplete: (task: AnalysisTask) => void
}

const providerName = (id: string) => id === 'workbuddy' ? '腾讯 WorkBuddy / CodeBuddy' : id === 'codex' ? 'Codex CLI' : id

export function Onboarding({ providers, cases, createTask, loadCase, onComplete }: OnboardingProps) {
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

  async function chooseCase(caseId: string) {
    setBusy(true)
    setNotice('正在创建隔离任务并装载数据、文档与规则…')
    try {
      const task = await loadCase(caseId)
      setNotice('完整案例已装载')
      onComplete(task)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '案例装载失败，请重试。')
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
          <section className="case-library" aria-labelledby="case-library-title">
            <div className="case-library__heading"><div><p className="eyebrow">DEMO CASEBOOK</p><h2 id="case-library-title">完整示例案例</h2></div><span>合成数据 · 一键装载</span></div>
            <div className="case-grid">
              {cases.map((item, index) => (
                <article className="case-card" key={item.id}>
                  <span className="case-card__number">{String(index + 1).padStart(2, '0')}</span>
                  <h3>{item.title}</h3>
                  <p>{item.summary}</p>
                  <strong>{item.record_count} 条指标记录 · {item.metric_count} 个指标 · {item.document_count} 份文档</strong>
                  <small>{item.time_range.start} — {item.time_range.end}</small>
                  <button className="button button--secondary" type="button" disabled={busy} aria-label={`加载案例：${item.title}`} onClick={() => chooseCase(item.id)}>加载完整案例</button>
                </article>
              ))}
            </div>
          </section>
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
