import { useState } from 'react'

import type { AnalysisTask, PreparedSource, ProviderConnection, SourcePreview } from '../../contracts/workbench'
import { DataImport } from '../assets/DataImport'

const tabs = ['总览', '数据', '文本', '证据', '假设', '历史'] as const

interface TaskShellProps {
  task: AnalysisTask
  providers: ProviderConnection[]
  previewLocalPath: (path: string) => Promise<SourcePreview>
  uploadFile: (file: File) => Promise<PreparedSource>
  previewApi: (url: string) => Promise<PreparedSource>
  applyImport: (path: string, plan: Record<string, string>) => Promise<void>
  onBack: () => void
  onCreateTask: () => void
}

export function TaskShell({ task, providers, previewLocalPath, uploadFile, previewApi, applyImport, onBack, onCreateTask }: TaskShellProps) {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('总览')
  const [assistantOpen, setAssistantOpen] = useState(true)
  const readyProvider = providers.find((provider) => provider.state === 'ready' || provider.state === 'connected')
  const datasets = task.snapshot_refs.filter((ref) => ref.kind === 'dataset').length
  const documents = task.snapshot_refs.filter((ref) => ref.kind === 'document').length

  return (
    <>
      <header className="topbar">
        <button className="brand brand--button" type="button" onClick={onBack} aria-label="返回任务首页"><span className="brand-mark" aria-hidden="true">D2</span><span>Data2Doc2Data</span></button>
        <div className="topbar-status" role="status"><span className={`status-dot${readyProvider ? ' status-dot--ready' : ' status-dot--idle'}`} aria-hidden="true" />{readyProvider ? `${readyProvider.provider_id} 可用` : '未连接助手'}</div>
        <button className="button button--quiet" type="button" onClick={() => setAssistantOpen((open) => !open)}>{assistantOpen ? '收起助手' : '打开助手'}</button>
      </header>
      <div className={`workbench-grid${assistantOpen ? '' : ' workbench-grid--assistant-closed'}`}>
        <nav className="asset-rail" aria-label="任务与资产">
          <div className="rail-heading"><span>分析任务</span><button className="icon-button" type="button" aria-label="新建分析任务" onClick={onCreateTask}>＋</button></div>
          <button className="task-card task-card--active" type="button" onClick={onBack}><span className="task-card__eyebrow">当前任务</span><strong>{task.title}</strong><span>{task.goal}</span></button>
          <div className="rail-section"><h2>任务资产</h2><button type="button"><span aria-hidden="true">▦</span> 数据集 <b>{datasets}</b></button><button type="button"><span aria-hidden="true">▤</span> 文档 <b>{documents}</b></button><button type="button"><span aria-hidden="true">◇</span> 运行记录 <b>0</b></button></div>
        </nav>
        <main className="analysis-canvas">
          <div className="canvas-heading"><div><p className="eyebrow">任务工作区</p><h1>{task.title}</h1><p>{task.goal}</p></div><button className="button button--primary" type="button" onClick={() => setActiveTab('数据')}>接入数据</button></div>
          <div className="tabs" role="tablist" aria-label="分析视图">{tabs.map((tab) => <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? 'tab tab--active' : 'tab'} onClick={() => setActiveTab(tab)}>{tab}</button>)}</div>
          {(activeTab === '总览' || activeTab === '数据') && datasets === 0 ? <DataImport previewLocalPath={previewLocalPath} uploadFile={uploadFile} previewApi={previewApi} applyImport={applyImport} /> : <section className="empty-workspace" aria-labelledby="view-title"><div className="empty-visual" aria-hidden="true"><span className="empty-node" /><span className="empty-line" /><span className="empty-node empty-node--accent" /></div><p className="eyebrow">{activeTab.toUpperCase()}</p><h2 id="view-title">{activeTab}工作区</h2><p>这一视图将在任务资产准备好后生成，并保留可回溯的来源与计算过程。</p></section>}
        </main>
        {assistantOpen && <aside className="assistant-drawer" aria-label="AI 助手"><div className="assistant-heading"><div><p className="eyebrow">协作分析</p><h2>AI 助手</h2></div><span className="connection-badge">{readyProvider ? '可用' : '未连接助手'}</span></div><div className="assistant-empty"><div className="assistant-orb" aria-hidden="true" /><strong>{readyProvider ? '等待任务上下文' : '先完成连接，或直接分析'}</strong><p>仍可使用本地数据画像与确定性 Dashboard</p><button className="button button--secondary" type="button">连接 Codex / WorkBuddy</button></div><form className="assistant-composer"><label htmlFor="assistant-message">发送给助手</label><textarea id="assistant-message" rows={3} placeholder="连接助手后，可基于当前任务继续分析…" disabled /><button className="button button--primary" type="submit" disabled>发送</button></form></aside>}
      </div>
    </>
  )
}
