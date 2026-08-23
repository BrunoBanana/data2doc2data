import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App, type WorkbenchApi } from './App'
import type { CombinedDashboard } from '../contracts/dashboard'
import type { AnalysisTask } from '../contracts/workbench'

const task: AnalysisTask = { task_id: 'task-1', title: '业务分析工作台', goal: '查明业务变化', status: 'active', snapshot_refs: [] }

function client(tasks = [task], dashboard: CombinedDashboard = { dashboard: null, text_dashboard: null }): WorkbenchApi {
  return {
    loadWorkspace: async () => ({ providers: [], tasks, agents: [], cases: [] }),
    createTask: async (title, goal) => ({ ...task, title, goal }),
    loadCase: async () => task,
    previewLocalPath: async () => ({ preview: { format: 'csv', fields: [], row_count: 0, sample_rows: [] }, suggestion: null }),
    uploadFile: async () => ({ source_path: '/tmp/upload.csv', preview: { format: 'csv', fields: [], row_count: 0, sample_rows: [] }, suggestion: null }),
    previewApi: async () => ({ source_path: '/tmp/api.json', preview: { format: 'json', fields: [], row_count: 0, sample_rows: [] }, suggestion: null }),
    applyImportToTask: async () => task,
    loadTaskDashboard: async () => dashboard,
    importDocuments: async () => ({ task, text_dashboard: { corpus_id: 'corpus-1', document_count: 0, failure_count: 0, duplicate_count: 0, topics: [], entities: [], claims: [] } }),
    startAnalysis: async () => ({ run: { contract_version: 1, run_id: 'run-1', task_id: 'task-1', status: 'completed', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] } }),
    listTaskRuns: async () => [],
    loadRun: async () => ({ run: { contract_version: 1, run_id: 'run-1', task_id: 'task-1', status: 'completed', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] } }),
    retryRun: async () => ({ run: { contract_version: 1, run_id: 'run-2', task_id: 'task-1', status: 'completed', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-2', nodes: [], edges: [] } }),
    downloadTaskReport: async () => ({ blob: new Blob(['<!doctype html>']), filename: 'report.html' }),
    createAgentSession: async () => ({ id: 'session-1', provider: 'codex', workspace: '/tmp', permission_mode: 'collaborative', resumed: false }),
    sendAgentMessage: async () => undefined,
    interruptAgent: async () => undefined,
    decideAgentApproval: async () => undefined,
    openAgentEventStream: () => () => undefined,
  }
}

describe('analysis workbench shell', () => {
  it('keeps tasks and analysis as the primary workspace', async () => {
    render(<App client={client()} />)

    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(screen.getByRole('banner')).toHaveTextContent('Data2Doc2Data')
    expect(screen.getByRole('banner')).toHaveTextContent('本地计算')
    expect(screen.getByRole('navigation', { name: '案例与资产' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveTextContent('业务分析工作台')
    expect(screen.getByRole('complementary', { name: '分析员笔记' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '移动工作台视图' })).toHaveTextContent('分析过程助手')
  })

  it('offers deterministic analysis when no assistant is connected', async () => {
    render(<App client={client()} />)

    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(screen.getByText(/助手未连接/)).toBeInTheDocument()
    expect(screen.getByText('未发现可用助手；确定性分析仍可使用。')).toBeInTheDocument()
  })

  it('starts with provider onboarding when there are no tasks', async () => {
    render(<App client={client([])} />)

    expect(await screen.findByRole('heading', { name: '先选择你的分析协作者' })).toBeInTheDocument()
  })

  it('loads the deterministic dashboard for a task snapshot', async () => {
    const snapshotTask = { ...task, snapshot_refs: [{ kind: 'dataset' as const, snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }] }
    const provenance = { snapshot_id: 'dataset-1', sha256: 'a'.repeat(64), expression: 'count rows', fields: ['date'], result_row_count: 1 }
    render(<App client={client([snapshotTask], { dashboard: { contract_version: 1, dashboard_id: 'dashboard-1', title: '数据概览', blocks: [{ block_id: 'records', kind: 'kpi', title: '记录数', value: 12, data: [], provenance }] }, text_dashboard: null })} />)

    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(await screen.findByRole('heading', { name: '数据概览' })).toBeInTheDocument()
    expect(screen.getByText('记录数').parentElement).toHaveTextContent('12')
  })
})
