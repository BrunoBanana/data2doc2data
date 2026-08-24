import { useEffect, useMemo, useState } from 'react'

import { WorkbenchClient, type WorkspaceState } from '../api/client'
import type { CombinedDashboard, TextDashboardSpec } from '../contracts/dashboard'
import type { AnalysisRunResult, AnalysisRunStart, EvidenceGraphSpec, RunHistoryItem } from '../contracts/run-events'
import type { AnalysisTask, PreparedSource, SourcePreview, TaskLaunchOptions } from '../contracts/workbench'
import { Onboarding } from '../features/onboarding/Onboarding'
import { TaskHome } from '../features/tasks/TaskHome'
import { TaskShell } from '../features/tasks/TaskShell'

export interface WorkbenchApi {
  loadWorkspace: () => Promise<WorkspaceState>
  createTask: (title: string, goal: string, options?: TaskLaunchOptions) => Promise<AnalysisTask>
  loadCase: (caseId: string, options?: TaskLaunchOptions) => Promise<AnalysisTask>
  previewLocalPath: (path: string) => Promise<SourcePreview>
  uploadFile: (file: File) => Promise<PreparedSource>
  previewApi: (url: string) => Promise<PreparedSource>
  applyImportToTask: (taskId: string, path: string, plan: Record<string, string>) => Promise<AnalysisTask>
  loadTaskDashboard: (taskId: string) => Promise<CombinedDashboard>
  importDocuments: (taskId: string, paths: string[]) => Promise<{ task: AnalysisTask; text_dashboard: TextDashboardSpec }>
  startAnalysis: (taskId: string, hypotheses: string[]) => Promise<AnalysisRunStart>
  loadEvidenceGraph: (runId: string) => Promise<EvidenceGraphSpec>
  openRunEventStream: WorkbenchClient['openRunEventStream']
  cancelRun: WorkbenchClient['cancelRun']
  listTaskRuns: (taskId: string) => Promise<RunHistoryItem[]>
  loadRun: (runId: string) => Promise<AnalysisRunResult>
  retryRun: (runId: string, idempotencyKey: string) => Promise<AnalysisRunResult>
  downloadTaskReport: (taskId: string) => Promise<{ blob: Blob; filename: string }>
  createAgentSession: WorkbenchClient['createAgentSession']
  sendAgentMessage: WorkbenchClient['sendAgentMessage']
  interruptAgent: WorkbenchClient['interruptAgent']
  decideAgentApproval: WorkbenchClient['decideAgentApproval']
  openAgentEventStream: WorkbenchClient['openAgentEventStream']
  heartbeat: WorkbenchClient['heartbeat']
}

interface AppProps {
  client?: WorkbenchApi
}

export function App({ client: suppliedClient }: AppProps) {
  const client = useMemo(() => suppliedClient ?? new WorkbenchClient(), [suppliedClient])
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null)
  const [selectedTask, setSelectedTask] = useState<AnalysisTask | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    client.loadWorkspace().then((state) => {
      if (!active) return
      setWorkspace(state)
      setShowOnboarding(state.tasks.length === 0)
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : '无法加载本地工作台。')
    })
    return () => { active = false }
  }, [client])

  useEffect(() => {
    if (!workspace) return
    const timer = window.setInterval(() => client.heartbeat().catch(() => undefined), 120_000)
    return () => window.clearInterval(timer)
  }, [client, workspace])

  if (error) {
    return <main className="startup-state"><p className="eyebrow">LOCAL SERVICE</p><h1>工作台暂时无法启动</h1><p role="alert">{error}</p><button className="button button--primary" type="button" onClick={() => window.location.reload()}>重新连接</button></main>
  }
  if (!workspace) return <main className="startup-state" aria-busy="true"><div className="assistant-orb" aria-hidden="true" /><p>正在连接本地分析服务…</p></main>

  function completeOnboarding(task: AnalysisTask) {
    setWorkspace((current) => current ? { ...current, tasks: [task, ...current.tasks] } : current)
    setShowOnboarding(false)
    setSelectedTask(task)
  }

  if (showOnboarding) {
    return <div className="app-frame onboarding-frame"><Onboarding providers={workspace.providers} cases={workspace.cases} createTask={client.createTask.bind(client)} loadCase={client.loadCase.bind(client)} onComplete={completeOnboarding} /></div>
  }
  if (selectedTask) {
    const updateCurrentTask = (updated: AnalysisTask) => {
      setSelectedTask(updated)
      setWorkspace((current) => current ? { ...current, tasks: current.tasks.map((task) => task.task_id === updated.task_id ? updated : task) } : current)
    }
    const applyToCurrentTask = async (path: string, plan: Record<string, string>) => {
      const updated = await client.applyImportToTask(selectedTask.task_id, path, plan)
      updateCurrentTask(updated)
    }
    return <div className="app-frame"><TaskShell task={selectedTask} providers={workspace.providers} agents={workspace.agents} previewLocalPath={client.previewLocalPath.bind(client)} uploadFile={client.uploadFile.bind(client)} previewApi={client.previewApi.bind(client)} applyImport={applyToCurrentTask} loadDashboard={() => client.loadTaskDashboard(selectedTask.task_id)} importDocuments={(paths) => client.importDocuments(selectedTask.task_id, paths)} startAnalysis={(hypotheses, flowPlan) => client.startAnalysis(selectedTask.task_id, hypotheses, flowPlan)} loadEvidenceGraph={client.loadEvidenceGraph.bind(client)} openRunEventStream={client.openRunEventStream} cancelRun={client.cancelRun.bind(client)} listTaskRuns={() => client.listTaskRuns(selectedTask.task_id)} loadRun={client.loadRun.bind(client)} retryRun={client.retryRun.bind(client)} downloadTaskReport={() => client.downloadTaskReport(selectedTask.task_id)} createAgentSession={client.createAgentSession.bind(client)} sendAgentMessage={client.sendAgentMessage.bind(client)} interruptAgent={client.interruptAgent.bind(client)} decideAgentApproval={client.decideAgentApproval.bind(client)} openAgentEventStream={client.openAgentEventStream} onTaskUpdate={updateCurrentTask} onBack={() => setSelectedTask(null)} onCreateTask={() => setShowOnboarding(true)} /></div>
  }
  return (
    <div className="app-frame">
      <header className="topbar"><a className="brand" href="/" aria-label="Data2Doc2Data 首页"><span className="brand-mark" aria-hidden="true"><img src="/favicon.svg" alt="" /></span><span>Data2Doc2Data</span></a><div className="topbar-status" role="status">本地工作台已就绪</div></header>
      <main className="task-home-canvas"><TaskHome tasks={workspace.tasks} onOpenTask={(taskId) => setSelectedTask(workspace.tasks.find((task) => task.task_id === taskId) ?? null)} onCreateTask={() => setShowOnboarding(true)} /></main>
    </div>
  )
}
