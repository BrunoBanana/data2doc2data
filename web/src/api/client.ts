import type { AgentEvent, AgentProviderStatus, AgentSession, AnalysisTask, PreparedSource, ProviderConnection, SnapshotRef, SourcePreview } from '../contracts/workbench'
import type { CombinedDashboard, TextDashboardSpec } from '../contracts/dashboard'
import type { AnalysisRunResult, EvidenceGraphSpec, RunEvent } from '../contracts/run-events'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

interface BootstrapResponse {
  csrf_token: string
  agents: AgentProviderStatus[]
}

interface ErrorPayload {
  error?: string
}

export interface WorkspaceState {
  providers: ProviderConnection[]
  tasks: AnalysisTask[]
  agents: AgentProviderStatus[]
}

export type AgentEventStream = (
  sessionId: string,
  after: number,
  onEvent: (event: AgentEvent, eventId: number) => void,
  onError: () => void,
) => () => void

export class WorkbenchClient {
  private csrfToken = ''
  private agents: AgentProviderStatus[] = []

  constructor(private readonly fetcher: Fetcher = fetch) {}

  async bootstrap(): Promise<void> {
    const payload = await this.request<BootstrapResponse>('/api/agents', { method: 'GET' }, false)
    if (!payload.csrf_token) throw new Error('无法建立本地工作台会话。')
    this.csrfToken = payload.csrf_token
    this.agents = Array.isArray(payload.agents) ? payload.agents : []
  }

  async loadWorkspace(): Promise<WorkspaceState> {
    await this.bootstrap()
    const [providers, tasks] = await Promise.all([this.listProviders(), this.listTasks()])
    return { providers, tasks, agents: this.agents }
  }

  async listProviders(): Promise<ProviderConnection[]> {
    const payload = await this.read<{ providers: ProviderConnection[] }>('/api/workbench/providers')
    return payload.providers
  }

  async listTasks(): Promise<AnalysisTask[]> {
    const payload = await this.read<{ tasks: AnalysisTask[] }>('/api/workbench/tasks')
    return payload.tasks
  }

  async createTask(title: string, goal: string): Promise<AnalysisTask> {
    await this.ensureSession()
    const payload = await this.mutate<{ task: AnalysisTask }>('/api/workbench/tasks', { title, goal })
    return payload.task
  }

  async previewLocalPath(path: string): Promise<SourcePreview> {
    await this.ensureSession()
    return this.mutate<SourcePreview>('/api/ingest/preview', { path, validate_local: true })
  }

  async uploadFile(file: File): Promise<PreparedSource> {
    await this.ensureSession()
    const uploaded = await this.mutate<{ path: string }>('/api/ingest/upload', {
      filename: file.name,
      content: await fileAsBase64(file),
    })
    const preview = await this.mutate<SourcePreview>('/api/ingest/preview', {
      path: uploaded.path,
      validate_local: false,
    })
    return { ...preview, source_path: uploaded.path }
  }

  async previewApi(url: string): Promise<PreparedSource> {
    await this.ensureSession()
    const result = await this.mutate<SourcePreview & { snapshot: { path: string } }>('/api/ingest/api-snapshot', { url })
    return { preview: result.preview, suggestion: result.suggestion, source_path: result.snapshot.path }
  }

  async applyImport(path: string, plan: Record<string, string>): Promise<void> {
    await this.ensureSession()
    await this.mutate('/api/ingest/apply', { path, plan, mode: 'local' })
  }

  async applyImportToTask(taskId: string, path: string, plan: Record<string, string>): Promise<AnalysisTask> {
    await this.ensureSession()
    const applied = await this.mutate<{ snapshot: SnapshotRef }>('/api/ingest/apply', { path, plan, mode: 'local' })
    const attached = await this.mutate<{ task: AnalysisTask }>(`/api/workbench/tasks/${encodeURIComponent(taskId)}/assets`, {
      snapshot_refs: [applied.snapshot],
    })
    return attached.task
  }

  async loadTaskDashboard(taskId: string): Promise<CombinedDashboard> {
    return this.read<CombinedDashboard>(`/api/workbench/tasks/${encodeURIComponent(taskId)}/dashboard`)
  }

  async importDocuments(taskId: string, paths: string[]): Promise<{ task: AnalysisTask; text_dashboard: TextDashboardSpec }> {
    await this.ensureSession()
    return this.mutate(`/api/workbench/tasks/${encodeURIComponent(taskId)}/documents`, { paths })
  }

  async startAnalysis(taskId: string, hypotheses: string[]): Promise<AnalysisRunResult> {
    await this.ensureSession()
    return this.mutate(`/api/workbench/tasks/${encodeURIComponent(taskId)}/runs`, {
      execute: true,
      proposal: {
        hypotheses: hypotheses.slice(0, 20).map((hypothesis, index) => ({
          hypothesis_id: `hypothesis-${index + 1}`,
          text: hypothesis.slice(0, 500),
        })),
      },
    })
  }

  async runEventsAfter(runId: string, after: number): Promise<RunEvent[]> {
    const payload = await this.read<{ events: RunEvent[] }>(`/api/workbench/runs/${encodeURIComponent(runId)}/events?after=${Math.max(0, after)}`)
    return payload.events
  }

  async loadEvidenceGraph(runId: string): Promise<EvidenceGraphSpec> {
    const payload = await this.read<{ evidence_graph: EvidenceGraphSpec }>(`/api/workbench/runs/${encodeURIComponent(runId)}/graph`)
    return payload.evidence_graph
  }

  async createAgentSession(provider: string, permissionMode: AgentSession['permission_mode']): Promise<AgentSession> {
    await this.ensureSession()
    const payload = await this.mutate<{ session: AgentSession }>('/api/agent-sessions', {
      provider,
      permission_mode: permissionMode,
    })
    return payload.session
  }

  async sendAgentMessage(sessionId: string, message: string, taskId: string): Promise<void> {
    await this.ensureSession()
    await this.mutate(`/api/agent-sessions/${encodeURIComponent(sessionId)}/messages`, {
      message: message.slice(0, 20_000),
      task_id: taskId,
    })
  }

  async interruptAgent(sessionId: string): Promise<void> {
    await this.ensureSession()
    await this.mutate(`/api/agent-sessions/${encodeURIComponent(sessionId)}/interrupt`, {})
  }

  async decideAgentApproval(sessionId: string, approvalId: string, approved: boolean): Promise<void> {
    await this.ensureSession()
    await this.mutate(`/api/agent-sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}`, { approved })
  }

  openAgentEventStream: AgentEventStream = (sessionId, after, onEvent, onError) => {
    const source = new EventSource(`/api/agent-sessions/${encodeURIComponent(sessionId)}/events?after=${Math.max(0, after)}`)
    source.onmessage = (message) => {
      try {
        const eventId = Number.parseInt(message.lastEventId, 10)
        const parsed = JSON.parse(message.data) as AgentEvent
        onEvent(parsed, Number.isFinite(eventId) ? eventId : after)
      } catch {
        onError()
      }
    }
    source.onerror = onError
    return () => source.close()
  }

  private async ensureSession(): Promise<void> {
    if (!this.csrfToken) await this.bootstrap()
  }

  private async read<T>(path: string): Promise<T> {
    try {
      return await this.request<T>(path)
    } catch (error) {
      if (!(error instanceof HttpError) || error.status !== 403 || !this.csrfToken) throw error
      await this.bootstrap()
      return this.request<T>(path)
    }
  }

  private async mutate<T = unknown>(path: string, body: object): Promise<T> {
    const init = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': this.csrfToken,
      },
      body: JSON.stringify(body),
    }
    try {
      return await this.request<T>(path, init)
    } catch (error) {
      if (!(error instanceof HttpError) || error.status !== 403) throw error
      await this.bootstrap()
      return this.request<T>(path, {
        ...init,
        headers: { ...init.headers, 'X-CSRF-Token': this.csrfToken },
      })
    }
  }

  private async request<T>(path: string, init: RequestInit = {}, renew = true): Promise<T> {
    const response = await this.fetcher(path, { credentials: 'same-origin', ...init })
    const payload = await parseJson<T & ErrorPayload>(response)
    if (!response.ok) {
      if (renew && response.status === 403 && this.csrfToken) {
        throw new HttpError(response.status, payload.error || '本地会话已失效。')
      }
      throw new HttpError(response.status, payload.error || `请求失败（${response.status}）`)
    }
    return payload
  }
}

class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T
  } catch {
    throw new Error('本地服务返回了无法解析的响应。')
  }
}

function fileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('无法读取选择的文件。'))
    reader.onload = () => {
      const value = String(reader.result ?? '')
      const separator = value.indexOf(',')
      if (separator < 0) reject(new Error('无法编码选择的文件。'))
      else resolve(value.slice(separator + 1))
    }
    reader.readAsDataURL(file)
  })
}
