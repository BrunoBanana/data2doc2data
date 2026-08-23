import { lazy, Suspense, useEffect, useState } from 'react'

import type { CombinedDashboard, TextDashboardSpec } from '../../contracts/dashboard'
import type { AnalysisRunResult, RunHistoryItem } from '../../contracts/run-events'
import type { AgentEvent, AgentProviderStatus, AgentSession, AnalysisTask, PreparedSource, ProviderConnection, SourcePreview } from '../../contracts/workbench'
import { AssistantDrawer } from '../assistant/AssistantDrawer'
import { DataImport } from '../assets/DataImport'
import { DashboardCanvas } from '../dashboard/DashboardCanvas'
import { DocumentImport } from '../documents/DocumentImport'
import { TextDashboard } from '../documents/TextDashboard'
import { EvidenceGraph } from '../evidence/EvidenceGraph'
import { HypothesisPanel } from '../evidence/HypothesisPanel'
import { RunHistory } from '../history/RunHistory'

const tabs = ['总览', '数据', '文本', '证据', '假设', '历史'] as const
const RunPlayback = lazy(() => import('../runs/RunPlayback').then((module) => ({ default: module.RunPlayback })))

interface TaskShellProps {
  task: AnalysisTask
  providers: ProviderConnection[]
  agents: AgentProviderStatus[]
  previewLocalPath: (path: string) => Promise<SourcePreview>
  uploadFile: (file: File) => Promise<PreparedSource>
  previewApi: (url: string) => Promise<PreparedSource>
  applyImport: (path: string, plan: Record<string, string>) => Promise<void>
  loadDashboard: () => Promise<CombinedDashboard>
  importDocuments: (paths: string[]) => Promise<{ task: AnalysisTask; text_dashboard: TextDashboardSpec }>
  startAnalysis: (hypotheses: string[]) => Promise<AnalysisRunResult>
  listTaskRuns: () => Promise<RunHistoryItem[]>
  loadRun: (runId: string) => Promise<AnalysisRunResult>
  retryRun: (runId: string, idempotencyKey: string) => Promise<AnalysisRunResult>
  createAgentSession: (provider: string, permissionMode: AgentSession['permission_mode']) => Promise<AgentSession>
  sendAgentMessage: (sessionId: string, message: string, taskId: string) => Promise<void>
  interruptAgent: (sessionId: string) => Promise<void>
  decideAgentApproval: (sessionId: string, approvalId: string, approved: boolean) => Promise<void>
  openAgentEventStream: (sessionId: string, after: number, onEvent: (event: AgentEvent, eventId: number) => void, onError: () => void) => () => void
  onTaskUpdate: (task: AnalysisTask) => void
  onBack: () => void
  onCreateTask: () => void
}

export function TaskShell(props: TaskShellProps) {
  const { task, providers, agents, previewLocalPath, uploadFile, previewApi, applyImport, loadDashboard, importDocuments, startAnalysis, listTaskRuns, loadRun, retryRun, createAgentSession, sendAgentMessage, interruptAgent, decideAgentApproval, openAgentEventStream, onTaskUpdate, onBack, onCreateTask } = props
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('总览')
  const [assistantOpen, setAssistantOpen] = useState(true)
  const [combined, setCombined] = useState<CombinedDashboard | null>(null)
  const [dashboardError, setDashboardError] = useState('')
  const [loadingDashboard, setLoadingDashboard] = useState(false)
  const [runResult, setRunResult] = useState<AnalysisRunResult | null>(null)
  const [running, setRunning] = useState(false)
  const [runs, setRuns] = useState<RunHistoryItem[]>([])
  const readyProvider = providers.find((provider) => provider.state === 'ready' || provider.state === 'connected')
  const datasets = task.snapshot_refs.filter((ref) => ref.kind === 'dataset').length
  const documents = task.snapshot_refs.filter((ref) => ref.kind === 'document').length
  const snapshotKey = task.snapshot_refs.map((ref) => `${ref.kind}:${ref.snapshot_id}:${ref.sha256}`).join('|')

  useEffect(() => {
    if (!snapshotKey) { setCombined(null); return }
    let active = true
    setLoadingDashboard(true)
    setDashboardError('')
    loadDashboard().then((dashboard) => { if (active) setCombined(dashboard) }).catch((reason) => {
      if (active) setDashboardError(reason instanceof Error ? reason.message : 'Dashboard 加载失败。')
    }).finally(() => { if (active) setLoadingDashboard(false) })
    return () => { active = false }
  }, [loadDashboard, snapshotKey])

  useEffect(() => {
    let active = true
    listTaskRuns().then((items) => { if (active) setRuns(items) }).catch(() => { if (active) setRuns([]) })
    return () => { active = false }
  }, [listTaskRuns, task.task_id])

  async function addDocuments(paths: string[]) {
    const imported = await importDocuments(paths)
    setCombined((current) => ({ dashboard: current?.dashboard ?? null, text_dashboard: imported.text_dashboard }))
    onTaskUpdate(imported.task)
  }

  async function runAnalysis(hypotheses: string[]) {
    setRunning(true)
    setDashboardError('')
    try {
      const result = await startAnalysis(hypotheses)
      setRunResult(result)
      const refreshed = await listTaskRuns().catch(() => [])
      setRuns(refreshed)
      setActiveTab('证据')
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : '分析运行失败。')
      throw error
    } finally {
      setRunning(false)
    }
  }

  return <>
    <header className="topbar">
      <button className="brand brand--button" type="button" onClick={onBack} aria-label="返回任务首页"><span className="brand-mark" aria-hidden="true">D2</span><span>Data2Doc2Data</span></button>
      <div className="topbar-status" role="status"><span className={`status-dot${readyProvider ? ' status-dot--ready' : ' status-dot--idle'}`} aria-hidden="true" />{readyProvider ? `${readyProvider.provider_id} 可用` : '未连接助手'}</div>
      <button className="button button--quiet" type="button" onClick={() => setAssistantOpen((open) => !open)}>{assistantOpen ? '收起助手' : '打开助手'}</button>
    </header>
    <div className={`workbench-grid${assistantOpen ? '' : ' workbench-grid--assistant-closed'}`}>
      <nav className="asset-rail" aria-label="任务与资产">
        <div className="rail-heading"><span>分析任务</span><button className="icon-button" type="button" aria-label="新建分析任务" onClick={onCreateTask}>＋</button></div>
        <button className="task-card task-card--active" type="button" onClick={onBack}><span className="task-card__eyebrow">当前任务</span><strong>{task.title}</strong><span>{task.goal}</span></button>
        <div className="rail-section"><h2>任务资产</h2><button type="button" onClick={() => setActiveTab('数据')}><span aria-hidden="true">▦</span> 数据集 <b>{datasets}</b></button><button type="button" onClick={() => setActiveTab('文本')}><span aria-hidden="true">▤</span> 文档 <b>{documents}</b></button><button type="button" onClick={() => setActiveTab('历史')}><span aria-hidden="true">◇</span> 运行记录 <b>{runs.length}</b></button></div>
      </nav>
      <main className="analysis-canvas">
        <div className="canvas-heading"><div><p className="eyebrow">任务工作区</p><h1>{task.title}</h1><p>{task.goal}</p></div>{datasets ? <button className="button button--primary" type="button" disabled={running} onClick={() => runAnalysis([])}>{running ? '分析运行中…' : '运行分析'}</button> : <button className="button button--primary" type="button" onClick={() => setActiveTab('数据')}>接入数据</button>}</div>
        <div className="tabs" role="tablist" aria-label="分析视图">{tabs.map((tab) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? 'tab tab--active' : 'tab'} onClick={() => setActiveTab(tab)}>{tab}</button>)}</div>
        {dashboardError && <p className="form-notice" role="alert">{dashboardError}</p>}
        {loadingDashboard && <section className="dashboard-loading" aria-busy="true">正在基于锁定快照生成 Dashboard…</section>}
        {!loadingDashboard && activeTab === '总览' && <>{datasets === 0 ? <DataImport previewLocalPath={previewLocalPath} uploadFile={uploadFile} previewApi={previewApi} applyImport={applyImport} /> : combined?.dashboard && <DashboardCanvas dashboard={combined.dashboard} />}{datasets > 0 && <DocumentImport importDocuments={addDocuments} />}{combined?.text_dashboard && <TextDashboard dashboard={combined.text_dashboard} />}</>}
        {!loadingDashboard && activeTab === '数据' && (datasets === 0 ? <DataImport previewLocalPath={previewLocalPath} uploadFile={uploadFile} previewApi={previewApi} applyImport={applyImport} /> : combined?.dashboard && <DashboardCanvas dashboard={combined.dashboard} />)}
        {!loadingDashboard && activeTab === '文本' && <><DocumentImport importDocuments={addDocuments} />{combined?.text_dashboard && <TextDashboard dashboard={combined.text_dashboard} />}</>}
        {!loadingDashboard && activeTab === '假设' && <><HypothesisPanel onRun={runAnalysis} disabled={!datasets || running} />{runResult && <EvidenceGraph graph={runResult.evidence_graph} />}</>}
        {!loadingDashboard && activeTab === '证据' && (runResult ? <Suspense fallback={<section className="dashboard-loading" aria-busy="true">正在加载过程回放…</section>}><RunPlayback events={runResult.events} graph={runResult.evidence_graph} /></Suspense> : <section className="empty-workspace" aria-labelledby="view-title"><div className="empty-visual" aria-hidden="true"><span className="empty-node" /><span className="empty-line" /><span className="empty-node empty-node--accent" /></div><p className="eyebrow">EVIDENCE</p><h2 id="view-title">运行一次可观察分析</h2><p>系统将展示计算事件、文档抽取、证据关系与假设验证状态。</p></section>)}
        {!loadingDashboard && activeTab === '历史' && <RunHistory runs={runs} loadRun={loadRun} retryRun={retryRun} onReplay={async (result) => { setRunResult(result); setActiveTab('证据'); setRuns(await listTaskRuns().catch(() => runs)) }} />}
      </main>
      {assistantOpen && <AssistantDrawer task={task} agents={agents} createSession={createAgentSession} sendMessage={sendAgentMessage} interrupt={interruptAgent} decideApproval={decideAgentApproval} openEventStream={openAgentEventStream} />}
    </div>
  </>
}
