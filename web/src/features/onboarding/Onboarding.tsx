import { type FormEvent, useState } from 'react'

import type { AnalysisTask, FlagshipCaseSummary, ProviderConnection, TaskLaunchOptions } from '../../contracts/workbench'

interface OnboardingProps {
  providers: ProviderConnection[]
  cases: FlagshipCaseSummary[]
  createTask: (title: string, goal: string, options: TaskLaunchOptions) => Promise<AnalysisTask>
  loadCase: (caseId: string, options: TaskLaunchOptions) => Promise<AnalysisTask>
  onComplete: (task: AnalysisTask) => void
}

const providerName = (id: string) => id === 'workbuddy' ? '腾讯 WorkBuddy / CodeBuddy' : id === 'codex' ? 'Codex CLI' : id

export function Onboarding({ providers, cases, createTask, loadCase, onComplete }: OnboardingProps) {
  const [step, setStep] = useState<'entry' | 'demo' | 'provider' | 'connected'>('entry')
  const [selectedProvider, setSelectedProvider] = useState('')
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  function chooseProvider(provider: ProviderConnection) {
    if (provider.state === 'ready' || provider.state === 'connected') {
      setSelectedProvider(provider.provider_id)
      setNotice(`${providerName(provider.provider_id)} 已可用`)
      setStep('connected')
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
      const task = await createTask(title.trim(), goal.trim(), {
        analysis_mode: 'connected',
        agent_provider: selectedProvider,
      })
      setNotice('任务已创建')
      onComplete(task)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '任务创建失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  async function chooseCase(caseId: string, mode: 'demo' | 'connected') {
    setBusy(true)
    setNotice(mode === 'demo' ? '正在装载确定性 Demo Flow…' : '正在装载材料包，不注入 Demo 预设答案…')
    try {
      const task = await loadCase(caseId, {
        analysis_mode: mode,
        agent_provider: mode === 'connected' ? selectedProvider : null,
      })
      setNotice(mode === 'demo' ? '完整 Demo 已装载' : '材料包已装载')
      onComplete(task)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '案例装载失败，请重试。')
    } finally {
      setBusy(false)
    }
  }

  return <section className="onboarding" aria-labelledby="onboarding-title">
    <div className="onboarding-progress" aria-label="接入进度">
      <span className={step === 'entry' ? 'is-active' : ''}>1 选择体验方式</span>
      <span className={step === 'provider' ? 'is-active' : ''}>2 连接 Agent</span>
      <span className={step === 'demo' || step === 'connected' ? 'is-active' : ''}>3 选择材料</span>
    </div>

    {step === 'entry' && <div className="onboarding-panel journey-panel">
      <p className="eyebrow">START HERE</p>
      <h1 id="onboarding-title">选择你的分析方式</h1>
      <p>两条路径使用相同的本地工具、证据协议和报告格式；区别只在于谁来规划分析过程。</p>
      <div className="journey-grid">
        <button type="button" className="journey-card journey-card--demo" aria-label="立即体验 Demo" onClick={() => setStep('demo')}>
          <span>01 · NO MODEL REQUIRED</span><strong>立即体验 Demo</strong>
          <p>无需连接任何模型。装载完整合成案例，观看确定性的 Data + Text 推理 Flow。</p>
          <small>真实本地计算 · 完整动态过程 · 可下载报告</small>
        </button>
        <button type="button" className="journey-card journey-card--connected" aria-label="连接 Agent 开始分析" onClick={() => setStep('provider')}>
          <span>02 · CONNECTED AGENT</span><strong>连接 Agent 开始分析</strong>
          <p>由 Codex 或腾讯 WorkBuddy/CodeBuddy 规划，并调用受约束的本地分析工具。</p>
          <small>可使用材料包、单个混合文档或自己的数据</small>
        </button>
      </div>
    </div>}

    {step === 'demo' && <div className="onboarding-panel">
      <p className="eyebrow">DETERMINISTIC DEMO</p><h1 id="onboarding-title">选择一个完整 Demo</h1>
      <p>以下数据与文档均为合成材料；分析由内置 Demo Flow 执行，不需要也不会调用外部模型。</p>
      <CaseLibrary cases={cases} busy={busy} title="完整 Demo 案例" actionLabel="运行 Demo" onChoose={(caseId) => chooseCase(caseId, 'demo')} />
      <button className="button button--quiet" type="button" onClick={() => setStep('entry')}>返回体验方式</button>
    </div>}

    {step === 'provider' && <div className="onboarding-panel">
      <p className="eyebrow">CONNECTED AGENT</p><h1 id="onboarding-title">选择可用的分析 Agent</h1>
      <p>原始数据仍在本机计算；Agent 只接收有界统计、必要证据与工具结果。</p>
      <div className="provider-grid">{providers.filter((provider) => provider.kind !== 'none').map((provider) => <button key={provider.provider_id} type="button" className="provider-card" onClick={() => chooseProvider(provider)}><strong>{providerName(provider.provider_id)}</strong><span>{provider.state === 'ready' ? '可连接' : provider.state === 'connected' ? '已连接' : '需要处理'}</span><small>{provider.detail || '本地 CLI，可流式规划并请求操作审批。'}</small></button>)}</div>
      <button className="button button--quiet" type="button" onClick={() => setStep('entry')}>返回体验方式</button>
    </div>}

    {step === 'connected' && <form className="onboarding-panel task-form" onSubmit={submit}>
      <p className="eyebrow">CONNECTED · {providerName(selectedProvider)}</p><h1 id="onboarding-title">定义任务或选择材料包</h1>
      <label>任务名称<input aria-label="任务名称" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} /></label>
      <label>业务目标<textarea aria-label="业务目标" value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={2000} rows={4} /></label>
      <div className="template-row" aria-label="任务模板"><button type="button" onClick={() => { setTitle('异常调查'); setGoal('定位核心指标异常的范围、证据和可能原因') }}>异常调查</button><button type="button" onClick={() => { setTitle('周期复盘'); setGoal('总结本周期业务表现、变化与风险') }}>周期复盘</button><button type="button" onClick={() => { setTitle('策略核验'); setGoal('用数据验证策略文档中的目标与假设') }}>策略核验</button></div>
      <button className="button button--primary" type="submit" disabled={busy}>{busy ? '正在创建…' : '创建分析任务'}</button>
      <CaseLibrary cases={cases} busy={busy} title="也可以从完整材料包开始" actionLabel="使用材料包" onChoose={(caseId) => chooseCase(caseId, 'connected')} />
    </form>}
    {notice && <p className="form-notice" role="alert">{notice}</p>}
  </section>
}

function CaseLibrary({ cases, busy, title, actionLabel, onChoose }: { cases: FlagshipCaseSummary[]; busy: boolean; title: string; actionLabel: string; onChoose: (caseId: string) => void }) {
  return <section className="case-library" aria-labelledby="case-library-title"><div className="case-library__heading"><div><p className="eyebrow">MATERIAL CASEBOOK</p><h2 id="case-library-title">{title}</h2></div><span>合成数据 + 文档 · 可重复</span></div><div className="case-grid">{cases.map((item, index) => <article className="case-card" key={item.id}><span className="case-card__number">{String(index + 1).padStart(2, '0')}</span><h3>{item.title}</h3><p>{item.summary}</p><strong>{item.record_count} 条指标记录 · {item.metric_count} 个指标 · {item.document_count} 份文档</strong><small>{item.time_range.start} — {item.time_range.end}</small><button className="button button--secondary" type="button" disabled={busy} aria-label={`${actionLabel}：${item.title}`} onClick={() => onChoose(item.id)}>{actionLabel}</button></article>)}</div></section>
}
