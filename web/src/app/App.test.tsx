import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    startAnalysis: async () => ({ accepted: true, run: { contract_version: 1, run_id: 'run-1', task_id: 'task-1', status: 'running', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: null }, stream_url: '/api/workbench/runs/run-1/stream' }),
    loadEvidenceGraph: async () => ({ contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] }),
    openRunEventStream: () => () => undefined,
    cancelRun: async () => undefined,
    listTaskRuns: async () => [],
    loadRun: async () => ({ run: { contract_version: 1, run_id: 'run-1', task_id: 'task-1', status: 'completed', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] } }),
    retryRun: async () => ({ run: { contract_version: 1, run_id: 'run-2', task_id: 'task-1', status: 'completed', snapshot_refs: [], created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-2', nodes: [], edges: [] } }),
    downloadTaskReport: async () => ({ blob: new Blob(['<!doctype html>']), filename: 'report.html' }),
    createAgentSession: async () => ({ id: 'session-1', provider: 'codex', workspace: '/tmp', permission_mode: 'collaborative', resumed: false }),
    sendAgentMessage: async () => undefined,
    interruptAgent: async () => undefined,
    decideAgentApproval: async () => undefined,
    openAgentEventStream: () => () => undefined,
    heartbeat: async () => undefined,
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
    expect(document.querySelector('.workbench-grid')).toHaveAttribute('data-viewport-shell', 'true')
    expect(screen.getByRole('navigation', { name: '案例与资产' })).toHaveAttribute('data-scroll-owner', 'asset-rail')
    expect(screen.getByRole('main')).toHaveAttribute('data-scroll-owner', 'analysis-canvas')
  })

  it('offers deterministic analysis when no assistant is connected', async () => {
    render(<App client={client()} />)

    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(screen.getByText(/助手未连接/)).toBeInTheDocument()
    expect(screen.getByText('未发现可用助手；确定性分析仍可使用。')).toBeInTheDocument()
  })

  it('starts with explicit Demo and connected-Agent journeys when there are no tasks', async () => {
    render(<App client={client([])} />)

    expect(await screen.findByRole('heading', { name: '选择你的分析方式' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立即体验 Demo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '连接 Agent 开始分析' })).toBeInTheDocument()
  })

  it('loads the deterministic dashboard for a task snapshot', async () => {
    const snapshotTask = { ...task, snapshot_refs: [{ kind: 'dataset' as const, snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }] }
    const provenance = { snapshot_id: 'dataset-1', sha256: 'a'.repeat(64), expression: 'count rows', fields: ['date'], result_row_count: 1 }
    render(<App client={client([snapshotTask], { dashboard: { contract_version: 1, dashboard_id: 'dashboard-1', title: '数据概览', blocks: [{ block_id: 'records', kind: 'kpi', title: '记录数', value: 12, data: [], provenance }] }, text_dashboard: null })} />)

    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(await screen.findByRole('heading', { name: '数据概览' })).toBeInTheDocument()
    expect(screen.getByText('记录数').parentElement).toHaveTextContent('12')

    fireEvent.click(screen.getByRole('button', { name: '运行分析' }))
    expect(await screen.findByRole('heading', { name: '数据证据摘要' })).toBeInTheDocument()
    expect(screen.getByLabelText('数据证据摘要')).toHaveTextContent('记录数12')
  })

  it('reloads persisted analytical artifacts when a live run completes', async () => {
    const snapshotTask = { ...task, snapshot_refs: [{ kind: 'dataset' as const, snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }] }
    const api = client([snapshotTask])
    api.openRunEventStream = (_runId, _after, onEvent) => {
      window.setTimeout(() => onEvent({
        contract_version: 1,
        run_id: 'run-1',
        sequence: 1,
        kind: 'run.completed',
        phase: 'delivery',
        summary: {},
        artifact_refs: [],
        created_at: '2026-08-23T00:00:01Z',
      }, 1), 0)
      return () => undefined
    }
    api.loadRun = async () => ({
      run: { contract_version: 1, run_id: 'run-1', task_id: 'task-1', status: 'completed', snapshot_refs: snapshotTask.snapshot_refs, created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' },
      events: [],
      evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] },
      artifact_dashboard: {
        contract_version: 1,
        dashboard_id: 'dashboard-cycle-1',
        blocks: [{
          block_id: 'block-anomaly', kind: 'anomalies', title: '检测到 1 个异常点。', status: 'completed',
          provenance: { artifact_ref: 'artifact-1', method: 'detect_anomalies', sample_size: 12, limitations: ['异常不代表因果。'] },
          observations: { anomalies: [{ date: '2026-04-13', value: 50, robust_score: 8.2 }] },
        }],
      },
    })

    render(<App client={api} />)
    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))
    fireEvent.click(await screen.findByRole('button', { name: '运行分析' }))

    const diagnostics = await screen.findByRole('heading', { name: '深度诊断产物' })
    const liveProcess = await screen.findByRole('heading', { name: '分析过程与证据联动' })
    expect(liveProcess.compareDocumentPosition(diagnostics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('detect_anomalies')).toBeInTheDocument()
  })

  it('restores the latest completed run when reopening a task', async () => {
    const snapshotTask = { ...task, snapshot_refs: [{ kind: 'dataset' as const, snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }] }
    const api = client([snapshotTask])
    api.listTaskRuns = async () => [{
      contract_version: 1, run_id: 'run-latest', task_id: task.task_id, status: 'completed', snapshot_refs: snapshotTask.snapshot_refs,
      created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z', stale: false, event_count: 12, failure_type: null,
    }]
    api.loadRun = async () => ({
      run: { contract_version: 1, run_id: 'run-latest', task_id: task.task_id, status: 'completed', snapshot_refs: snapshotTask.snapshot_refs, created_at: '2026-08-23T00:00:00Z', started_at: '2026-08-23T00:00:00Z', completed_at: '2026-08-23T00:00:01Z' },
      events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-latest', nodes: [], edges: [] },
      artifact_dashboard: { contract_version: 1, dashboard_id: 'dashboard-latest', blocks: [{
        block_id: 'block-latest', kind: 'period_comparison', title: '最近一次周期比较', status: 'completed',
        provenance: { artifact_ref: 'artifact-latest', method: 'compare_periods', sample_size: 12, limitations: [] }, observations: {},
      }] },
    })

    render(<App client={api} />)
    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))

    expect(await screen.findByRole('heading', { name: '深度诊断产物' })).toBeInTheDocument()
    expect(screen.getByText('最近一次周期比较')).toBeInTheDocument()
  })

  it('does not override a tab the user selects while a previous run is restoring', async () => {
    const api = client()
    const completedRun = {
      contract_version: 1 as const,
      run_id: 'run-latest',
      task_id: task.task_id,
      status: 'completed' as const,
      snapshot_refs: [],
      created_at: '2026-08-23T00:00:00Z',
      started_at: '2026-08-23T00:00:00Z',
      completed_at: '2026-08-23T00:00:01Z',
    }
    api.listTaskRuns = async () => [{
      ...completedRun,
      stale: false,
      event_count: 12,
      failure_type: null,
    }]
    let finishRestoring!: (value: Awaited<ReturnType<WorkbenchApi['loadRun']>>) => void
    api.loadRun = () => new Promise((resolve) => { finishRestoring = resolve })

    render(<App client={api} />)
    fireEvent.click(await screen.findByRole('button', { name: /业务分析工作台/ }))
    await waitFor(() => expect(finishRestoring).toBeTypeOf('function'))

    fireEvent.click(screen.getByRole('tab', { name: '历史' }))
    expect(screen.getByRole('tab', { name: '历史' })).toHaveAttribute('aria-selected', 'true')

    await act(async () => finishRestoring({
      run: completedRun,
      events: [],
      evidence_graph: { contract_version: 1, graph_id: 'graph-latest', nodes: [], edges: [] },
    }))

    expect(screen.getByRole('tab', { name: '历史' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: '运行历史' })).toBeInTheDocument()
  })
})
