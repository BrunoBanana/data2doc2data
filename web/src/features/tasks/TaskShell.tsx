import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import type { CombinedDashboard, DashboardSpec, TextDashboardSpec } from '../../contracts/dashboard'
import type { AnalysisRunResult, AnalysisRunStart, EvidenceGraphSpec, RunEvent, RunHistoryItem } from '../../contracts/run-events'
import type { AgentEvent, AgentProviderStatus, AgentSession, AnalysisTask, PreparedSource, ProviderConnection, SourcePreview } from '../../contracts/workbench'
import { AssistantDrawer } from '../assistant/AssistantDrawer'
import { DataImport } from '../assets/DataImport'
import { DashboardCanvas } from '../dashboard/DashboardCanvas'
import { DiagnosticBlocks } from '../dashboard/DiagnosticBlocks'
import { DocumentImport } from '../documents/DocumentImport'
import { TextDashboard } from '../documents/TextDashboard'
import { EvidenceGraph } from '../evidence/EvidenceGraph'
import { HypothesisPanel } from '../evidence/HypothesisPanel'
import { RunHistory } from '../history/RunHistory'
import { createTrailingRefresh } from './graph-refresh-queue'
import { createRunEventBuffer } from './run-event-buffer'
import { ReportExport } from '../reports/ReportExport'

const tabs = ['总览', '数据', '文本', '证据', '假设', '历史'] as const
const AgentFlowCanvas = lazy(() => import('../flow/AgentFlowCanvas').then((module) => ({ default: module.AgentFlowCanvas })))

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
  startAnalysis: (hypotheses: string[]) => Promise<AnalysisRunStart>
  loadEvidenceGraph: (runId: string) => Promise<EvidenceGraphSpec>
  openRunEventStream: (runId: string, after: number, onEvent: (event: RunEvent, cursor: number) => void, onError: () => void) => () => void
  cancelRun: (runId: string) => Promise<void>
  listTaskRuns: () => Promise<RunHistoryItem[]>
  loadRun: (runId: string) => Promise<AnalysisRunResult>
  retryRun: (runId: string, idempotencyKey: string) => Promise<AnalysisRunResult>
  downloadTaskReport: () => Promise<{ blob: Blob; filename: string }>
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
  const { task, providers, agents, previewLocalPath, uploadFile, previewApi, applyImport, loadDashboard, importDocuments, startAnalysis, loadEvidenceGraph, openRunEventStream, cancelRun, listTaskRuns, loadRun, retryRun, downloadTaskReport, createAgentSession, sendAgentMessage, interruptAgent, decideAgentApproval, openAgentEventStream, onTaskUpdate, onBack, onCreateTask } = props
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('总览')
  const [assistantOpen, setAssistantOpen] = useState(true)
  const [mobileView, setMobileView] = useState<'analysis' | 'process' | 'assistant'>('analysis')
  const [combined, setCombined] = useState<CombinedDashboard | null>(null)
  const [dashboardError, setDashboardError] = useState('')
  const [flowNotice, setFlowNotice] = useState('')
  const [loadingDashboard, setLoadingDashboard] = useState(false)
  const [runResult, setRunResult] = useState<AnalysisRunResult | null>(null)
  const [running, setRunning] = useState(false)
  const [runs, setRuns] = useState<RunHistoryItem[]>([])
  const closeRunStream = useRef<(() => void) | null>(null)
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
    listTaskRuns().then((items) => {
      if (!active) return
      setRuns(items)
      const unfinished = items.find((item) => item.status === 'running' || item.status === 'queued')
      if (unfinished) {
        loadRun(unfinished.run_id).then((result) => {
          if (!active) return
          setRunResult(result)
          const stillRunning = result.run.status === 'running' || result.run.status === 'queued'
          setRunning(stillRunning)
          setActiveTab('证据')
          if (stillRunning) {
            attachRunStream(unfinished.run_id, Math.max(0, ...result.events.map((event) => event.sequence)))
          } else {
            listTaskRuns().then((latest) => { if (active) setRuns(latest) }).catch(() => undefined)
          }
        }).catch(() => undefined)
      }
    }).catch(() => { if (active) setRuns([]) })
    return () => { active = false }
  }, [listTaskRuns, task.task_id])

  useEffect(() => () => closeRunStream.current?.(), [])

  async function addDocuments(paths: string[]) {
    const imported = await importDocuments(paths)
    setCombined((current) => ({ dashboard: current?.dashboard ?? null, text_dashboard: imported.text_dashboard }))
    onTaskUpdate(imported.task)
  }

  async function runAnalysis(hypotheses: string[]) {
    setRunning(true)
    setDashboardError('')
    try {
      if (task.analysis_mode === 'connected') {
        setFlowNotice(`${task.agent_provider ?? 'Agent'} 正在由后端规划受约束的本地分析轮次…`)
      } else {
        setFlowNotice('确定性 Demo Flow 正在本地执行…')
      }
      const started = await startAnalysis(hypotheses)
      const runId = started.run.run_id
      const emptyGraph: EvidenceGraphSpec = { contract_version: 1, graph_id: `graph-${runId}`, nodes: [], edges: [] }
      setRunResult({ run: started.run, events: [], evidence_graph: emptyGraph })
      setActiveTab('证据')
      attachRunStream(runId, 0)
    } catch (error) {
      setRunning(false)
      setFlowNotice('')
      setDashboardError(error instanceof Error ? error.message : '分析运行失败。')
      throw error
    }
  }

  function attachRunStream(runId: string, after: number) {
    closeRunStream.current?.()
    const graphRefresh = createTrailingRefresh(
      () => loadEvidenceGraph(runId),
      (graph) => setRunResult((current) => current?.run.run_id === runId ? { ...current, evidence_graph: graph } : current),
    )
    const eventBuffer = createRunEventBuffer((batch) => {
      setRunResult((current) => {
        if (!current || current.run.run_id !== runId) return current
        const known = new Set(current.events.map((item) => item.sequence))
        const additions = batch.filter((event) => !known.has(event.sequence))
        if (additions.length === 0) return current
        let terminal: RunEvent | undefined
        for (const event of additions) {
          if (['run.completed', 'run.failed', 'run.interrupted'].includes(event.kind)) terminal = event
        }
        const terminalStatus = terminal?.kind === 'run.completed' ? 'completed' : terminal?.kind === 'run.failed' ? 'failed' : terminal?.kind === 'run.interrupted' ? 'interrupted' : current.run.status
        return { ...current, run: { ...current.run, status: terminalStatus }, events: [...current.events, ...additions].sort((left, right) => left.sequence - right.sequence) }
      })
    })
    const closeSource = openRunEventStream(runId, after, (event) => {
      eventBuffer.push(event)
      if (event.kind === 'node.added' || event.kind === 'node.updated' || event.kind === 'edge.added' || event.kind === 'edge.activated') {
        graphRefresh.schedule()
      }
      if (event.kind === 'run.completed' || event.kind === 'run.failed' || event.kind === 'run.interrupted') {
        setRunning(false)
        setFlowNotice('')
        graphRefresh.schedule()
        loadRun(runId).then((result) => setRunResult((current) => current?.run.run_id === runId ? result : current)).catch(() => undefined)
        listTaskRuns().then(setRuns).catch(() => undefined)
      }
    }, () => setDashboardError('实时过程暂时断开，正在等待浏览器自动续接。'))
    closeRunStream.current = () => {
      eventBuffer.dispose()
      closeSource()
    }
  }

  async function stopAnalysis() {
    if (!runResult || !running) return
    await cancelRun(runResult.run.run_id)
  }

  return <>
    <header className="topbar">
      <button className="brand brand--button" type="button" onClick={onBack} aria-label="返回任务首页"><span className="brand-mark" aria-hidden="true"><img src="/favicon.svg" alt="" /></span><span>Data2Doc2Data</span></button>
      <div className="topbar-case"><span>{task.analysis_mode === 'connected' ? `CONNECTED · ${task.agent_provider ?? 'AGENT'}` : 'DEMO · 合成数据'}</span><strong>{task.title}</strong></div>
      <div className="topbar-status" role="status"><span className="status-dot status-dot--ready" aria-hidden="true" />本地计算 <i aria-hidden="true">·</i> {readyProvider ? `${readyProvider.provider_id} 可用` : '助手未连接'}</div>
      <button className="button button--quiet" type="button" onClick={() => setAssistantOpen((open) => !open)}>{assistantOpen ? '收起笔记' : '打开笔记'}</button>
    </header>
    <nav className="mobile-view-switcher" aria-label="移动工作台视图">
      <button type="button" aria-pressed={mobileView === 'analysis'} onClick={() => setMobileView('analysis')}>分析</button>
      <button type="button" aria-pressed={mobileView === 'process'} onClick={() => { setMobileView('process'); setActiveTab('证据') }}>过程</button>
      <button type="button" aria-pressed={mobileView === 'assistant'} onClick={() => { setAssistantOpen(true); setMobileView('assistant') }}>助手</button>
    </nav>
    <div data-viewport-shell="true" className={`workbench-grid workbench-grid--mobile-${mobileView}${assistantOpen ? '' : ' workbench-grid--assistant-closed'}`}>
      <nav className="asset-rail" aria-label="案例与资产" data-scroll-owner="asset-rail">
        <div className="rail-heading"><span>案例与资产</span><button className="icon-button rail-create-button" type="button" aria-label="新建分析任务" onClick={onCreateTask}>新建</button></div>
        <button className="task-card task-card--active" type="button" onClick={onBack}><span className="task-card__eyebrow">{task.analysis_mode === 'connected' ? 'CONNECTED TASK' : 'DETERMINISTIC DEMO'}</span><strong>{task.title}</strong><span>{task.goal}</span></button>
        <div className="rail-section"><h2>锁定资产</h2><button type="button" onClick={() => setActiveTab('数据')}>数据集 <b>{datasets}</b></button><button type="button" onClick={() => setActiveTab('文本')}>文档材料 <b>{documents}</b></button><button type="button" onClick={() => setActiveTab('历史')}>运行记录 <b>{runs.length}</b></button></div>
      </nav>
      <main className="analysis-canvas" data-scroll-owner="analysis-canvas">
        <div className="canvas-heading"><div><p className="eyebrow">ANALYSIS BLUEPRINT</p><h1>{task.title}</h1><p>{task.goal}</p></div><div className="task-actions"><ReportExport download={downloadTaskReport} />{running ? <button className="button button--quiet" type="button" onClick={stopAnalysis}>停止当前任务</button> : datasets ? <button className="button button--primary" type="button" onClick={() => runAnalysis([])}>运行分析</button> : <button className="button button--primary" type="button" onClick={() => setActiveTab('数据')}>接入数据</button>}</div></div>
        <div className="tabs" role="tablist" aria-label="分析视图">{tabs.map((tab) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? 'tab tab--active' : 'tab'} onClick={() => setActiveTab(tab)}>{tab}</button>)}</div>
        {dashboardError && <p className="form-notice" role="alert">{dashboardError}</p>}
        {flowNotice && <p className="form-notice" role="status">{flowNotice}</p>}
        {loadingDashboard && <section className="dashboard-loading" aria-busy="true">正在基于锁定快照生成 Dashboard…</section>}
        {!loadingDashboard && activeTab === '总览' && <>{datasets === 0 ? <DataImport previewLocalPath={previewLocalPath} uploadFile={uploadFile} previewApi={previewApi} applyImport={applyImport} /> : combined?.dashboard && <DashboardCanvas dashboard={combined.dashboard} />}{datasets > 0 && <DocumentImport importDocuments={addDocuments} />}{combined?.text_dashboard && <TextDashboard dashboard={combined.text_dashboard} />}</>}
        {!loadingDashboard && activeTab === '数据' && (datasets === 0 ? <DataImport previewLocalPath={previewLocalPath} uploadFile={uploadFile} previewApi={previewApi} applyImport={applyImport} /> : combined?.dashboard && <DashboardCanvas dashboard={combined.dashboard} />)}
        {!loadingDashboard && activeTab === '文本' && <><DocumentImport importDocuments={addDocuments} />{combined?.text_dashboard && <TextDashboard dashboard={combined.text_dashboard} />}</>}
        {!loadingDashboard && activeTab === '假设' && <><HypothesisPanel onRun={runAnalysis} disabled={!datasets || running} />{runResult && <EvidenceGraph graph={runResult.evidence_graph} />}</>}
        {!loadingDashboard && activeTab === '证据' && (runResult ? <><EvidenceBrief dashboard={combined?.dashboard ?? null} graph={runResult.evidence_graph} />{runResult.artifact_dashboard && <DiagnosticBlocks dashboard={runResult.artifact_dashboard} />}<Suspense fallback={<section className="dashboard-loading" aria-busy="true">正在加载实时 Flow 画布…</section>}><AgentFlowCanvas events={runResult.events} graph={runResult.evidence_graph} /></Suspense></> : <section className="empty-workspace" aria-labelledby="view-title"><div className="empty-visual" aria-hidden="true"><span className="empty-node" /><span className="empty-line" /><span className="empty-node empty-node--accent" /></div><p className="eyebrow">EVIDENCE</p><h2 id="view-title">运行一次可观察分析</h2><p>系统将展示计算事件、文档抽取、证据关系与假设验证状态。</p></section>)}
        {!loadingDashboard && activeTab === '历史' && <RunHistory runs={runs} loadRun={loadRun} retryRun={retryRun} onReplay={async (result) => { setRunResult(result); setActiveTab('证据'); setRuns(await listTaskRuns().catch(() => runs)) }} />}
      </main>
      {assistantOpen && <AssistantDrawer task={task} agents={agents} createSession={createAgentSession} sendMessage={sendAgentMessage} interrupt={interruptAgent} decideApproval={decideAgentApproval} openEventStream={openAgentEventStream} />}
    </div>
  </>
}

function EvidenceBrief({ dashboard, graph }: { dashboard: DashboardSpec | null; graph: EvidenceGraphSpec }) {
  const kpis = dashboard?.blocks.filter((block) => block.kind === 'kpi').slice(0, 6) ?? []
  const verified = graph.nodes.filter((node) => node.status === 'verified' || node.status === 'supported').length
  const conflicts = graph.nodes.filter((node) => node.status === 'contradicted').length
  return <section className="evidence-brief" aria-label="数据证据摘要">
    <div className="evidence-brief__heading"><div><p className="eyebrow">LOCAL SIGNALS</p><h2>数据证据摘要</h2></div><span>{verified} 已验证 · {conflicts} 冲突</span></div>
    <div className="evidence-brief__grid">{kpis.map((block) => <article key={block.block_id}><span>{block.title}</span><strong>{String(block.value ?? '—')}</strong></article>)}</div>
  </section>
}
