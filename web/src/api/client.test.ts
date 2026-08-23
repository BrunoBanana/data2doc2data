import { beforeEach, describe, expect, it, vi } from 'vitest'

import { WorkbenchClient } from './client'

function response(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('WorkbenchClient', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('calls the browser fetch function without rebinding its receiver', async () => {
    const browserFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError('Illegal invocation')
      return Promise.resolve(response({ csrf_token: 'csrf-1', agents: [] }))
    })
    vi.stubGlobal('fetch', browserFetch)

    await new WorkbenchClient().bootstrap()

    expect(browserFetch).toHaveBeenCalledOnce()
    vi.unstubAllGlobals()
  })

  it('bootstraps a browser session before loading workbench state', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ providers: [{ provider_id: 'codex', kind: 'local_cli', state: 'ready', capabilities: [], detail: null, reconnect_hint: null }] }))
      .mockResolvedValueOnce(response({ tasks: [] }))
      .mockResolvedValueOnce(response({ cases: [] }))
    const client = new WorkbenchClient(fetcher)

    const result = await client.loadWorkspace()

    expect(result.providers[0].provider_id).toBe('codex')
    expect(result.tasks).toEqual([])
    expect(result.cases).toEqual([])
    expect(fetcher).toHaveBeenNthCalledWith(1, '/api/agents', expect.objectContaining({ credentials: 'same-origin' }))
  })

  it('sends csrf for mutations and renews an expired session once', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'old', agents: [] }))
      .mockResolvedValueOnce(response({ error: 'agent request authorization failed' }, 403))
      .mockResolvedValueOnce(response({ csrf_token: 'new', agents: [] }))
      .mockResolvedValueOnce(response({ task: { task_id: 'task-1', title: '复盘', goal: '找变化', status: 'active', snapshot_refs: [] } }))
    const client = new WorkbenchClient(fetcher)

    const task = await client.createTask('复盘', '找变化')

    expect(task.task_id).toBe('task-1')
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/workbench/tasks', expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': 'old' }),
    }))
    expect(fetcher).toHaveBeenNthCalledWith(4, '/api/workbench/tasks', expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': 'new' }),
    }))
  })

  it('uses strict local validation for path previews', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ preview: { format: 'csv', fields: [], row_count: 0, sample_rows: [] }, suggestion: null }))
    const client = new WorkbenchClient(fetcher)

    await client.previewLocalPath('/tmp/data.csv')

    const init = fetcher.mock.calls[1][1] as RequestInit
    expect(JSON.parse(init.body as string)).toEqual({ path: '/tmp/data.csv', validate_local: true })
  })

  it('uploads a browser file and previews the stored local snapshot', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ path: '/private/upload.csv', filename: 'upload.csv' }))
      .mockResolvedValueOnce(response({ preview: { format: 'csv', fields: ['date'], row_count: 1, sample_rows: [] }, suggestion: null }))
    const client = new WorkbenchClient(fetcher)

    const result = await client.uploadFile(new File(['date\n2026-01-01'], 'upload.csv', { type: 'text/csv' }))

    expect(result.source_path).toBe('/private/upload.csv')
    expect(JSON.parse(fetcher.mock.calls[1][1].body as string)).toMatchObject({ filename: 'upload.csv' })
    expect(JSON.parse(fetcher.mock.calls[2][1].body as string)).toEqual({ path: '/private/upload.csv', validate_local: false })
  })

  it('creates a local HTTPS API snapshot for preview', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ snapshot: { path: '/private/api.json' }, preview: { format: 'json', fields: [], row_count: 1, sample_rows: [] }, suggestion: null }))
    const client = new WorkbenchClient(fetcher)

    const result = await client.previewApi('https://example.test/metrics')

    expect(result.source_path).toBe('/private/api.json')
    expect(JSON.parse(fetcher.mock.calls[1][1].body as string)).toEqual({ url: 'https://example.test/metrics' })
  })

  it('attaches the immutable dataset snapshot to the current task', async () => {
    const snapshot = { kind: 'dataset', snapshot_id: 'dataset-1', sha256: 'a'.repeat(64) }
    const attachedTask = { task_id: 'task-1', title: '复盘', goal: '找变化', status: 'active', snapshot_refs: [snapshot] }
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ snapshot }))
      .mockResolvedValueOnce(response({ task: attachedTask }))
    const client = new WorkbenchClient(fetcher)

    const task = await client.applyImportToTask('task-1', '/tmp/data.csv', { format: 'csv' })

    expect(task.snapshot_refs).toEqual([snapshot])
    expect(JSON.parse(fetcher.mock.calls[2][1].body as string)).toEqual({ snapshot_refs: [snapshot] })
  })

  it('loads a combined task dashboard and imports document paths', async () => {
    const task = { task_id: 'task-1', title: '复盘', goal: '找变化', status: 'active', snapshot_refs: [] }
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ dashboard: null, text_dashboard: null }))
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response({ task, text_dashboard: { corpus_id: 'corpus-1', document_count: 1, failure_count: 0, duplicate_count: 0, topics: [], entities: [], claims: [] } }))
    const client = new WorkbenchClient(fetcher)

    expect(await client.loadTaskDashboard('task-1')).toEqual({ dashboard: null, text_dashboard: null })
    const imported = await client.importDocuments('task-1', ['/tmp/plan.md'])

    expect(imported.task.task_id).toBe('task-1')
    expect(JSON.parse(fetcher.mock.calls[2][1].body as string)).toEqual({ paths: ['/tmp/plan.md'] })
  })

  it('starts a structured observable run without private reasoning fields', async () => {
    const result = { run: { run_id: 'run-1', status: 'completed' }, events: [], evidence_graph: { contract_version: 1, graph_id: 'graph-1', nodes: [], edges: [] } }
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'csrf-1', agents: [] }))
      .mockResolvedValueOnce(response(result, 201))
    const client = new WorkbenchClient(fetcher)

    await client.startAnalysis('task-1', ['价格调整影响收入'])

    expect(JSON.parse(fetcher.mock.calls[1][1].body as string)).toEqual({ execute: true, proposal: { hypotheses: [{ hypothesis_id: 'hypothesis-1', text: '价格调整影响收入' }] } })
    expect(fetcher.mock.calls[1][1].body).not.toContain('chain_of_thought')
  })

  it('surfaces the backend error message', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response({ error: '文件不存在' }, 422))
    const client = new WorkbenchClient(fetcher)

    await expect(client.listTasks()).rejects.toThrow('文件不存在')
  })
})
