import { useEffect, useMemo, useState } from 'react'

import { WorkbenchClient, type WorkspaceState } from '../api/client'
import type { AnalysisTask, PreparedSource, SourcePreview } from '../contracts/workbench'
import { Onboarding } from '../features/onboarding/Onboarding'
import { TaskHome } from '../features/tasks/TaskHome'
import { TaskShell } from '../features/tasks/TaskShell'

export interface WorkbenchApi {
  loadWorkspace: () => Promise<WorkspaceState>
  createTask: (title: string, goal: string) => Promise<AnalysisTask>
  previewLocalPath: (path: string) => Promise<SourcePreview>
  uploadFile: (file: File) => Promise<PreparedSource>
  previewApi: (url: string) => Promise<PreparedSource>
  applyImportToTask: (taskId: string, path: string, plan: Record<string, string>) => Promise<AnalysisTask>
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
    return <div className="app-frame onboarding-frame"><Onboarding providers={workspace.providers} createTask={client.createTask.bind(client)} onComplete={completeOnboarding} /></div>
  }
  if (selectedTask) {
    const applyToCurrentTask = async (path: string, plan: Record<string, string>) => {
      const updated = await client.applyImportToTask(selectedTask.task_id, path, plan)
      setSelectedTask(updated)
      setWorkspace((current) => current ? { ...current, tasks: current.tasks.map((task) => task.task_id === updated.task_id ? updated : task) } : current)
    }
    return <div className="app-frame"><TaskShell task={selectedTask} providers={workspace.providers} previewLocalPath={client.previewLocalPath.bind(client)} uploadFile={client.uploadFile.bind(client)} previewApi={client.previewApi.bind(client)} applyImport={applyToCurrentTask} onBack={() => setSelectedTask(null)} onCreateTask={() => setShowOnboarding(true)} /></div>
  }
  return (
    <div className="app-frame">
      <header className="topbar"><a className="brand" href="/" aria-label="Data2Doc2Data 首页"><span className="brand-mark" aria-hidden="true">D2</span><span>Data2Doc2Data</span></a><div className="topbar-status" role="status">本地工作台已就绪</div></header>
      <main className="task-home-canvas"><TaskHome tasks={workspace.tasks} onOpenTask={(taskId) => setSelectedTask(workspace.tasks.find((task) => task.task_id === taskId) ?? null)} onCreateTask={() => setShowOnboarding(true)} /></main>
    </div>
  )
}
