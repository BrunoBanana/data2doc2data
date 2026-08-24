import type { FlowPlanPayload } from '../../contracts/run-events'
import type { AgentEvent, AgentSession, AnalysisTask } from '../../contracts/workbench'

interface ConnectedPlannerOptions {
  task: AnalysisTask
  createSession: (provider: string, permissionMode: AgentSession['permission_mode']) => Promise<AgentSession>
  sendMessage: (sessionId: string, message: string, taskId: string) => Promise<void>
  openEventStream: (
    sessionId: string,
    after: number,
    onEvent: (event: AgentEvent, eventId: number) => void,
    onError: () => void,
  ) => () => void
  timeoutMs?: number
}

export async function requestConnectedFlowPlan(options: ConnectedPlannerOptions): Promise<FlowPlanPayload> {
  const provider = options.task.agent_provider
  if (!provider) throw new Error('连接模式缺少 Agent 提供方。')
  const session = await options.createSession(provider, 'read_only')
  const prompt = buildPlannerPrompt(options.task)

  return new Promise<FlowPlanPayload>((resolve, reject) => {
    let buffer = ''
    let settled = false
    let close: () => void = () => undefined
    const timer = globalThis.setTimeout(() => fail(new Error('Agent 规划超时，请检查本地连接后重试。')), options.timeoutMs ?? 120_000)

    function finish(plan: FlowPlanPayload) {
      if (settled) return
      settled = true
      globalThis.clearTimeout(timer)
      close()
      resolve(plan)
    }

    function fail(error: unknown) {
      if (settled) return
      settled = true
      globalThis.clearTimeout(timer)
      close()
      reject(error instanceof Error ? error : new Error('Agent Flow 规划失败。'))
    }

    close = options.openEventStream(session.id, 0, (event) => {
      const text = typeof event.payload?.text === 'string' ? event.payload.text : ''
      if (event.kind === 'plan.delta' || event.kind === 'message.delta') buffer += text
      if (event.kind === 'approval.request') {
        fail(new Error('Agent 请求了额外操作；规划阶段不允许执行命令或读取文件，请检查本地 Agent 配置后重试。'))
      } else if (event.kind === 'turn.completed') {
        try { finish(parseFlowPlan(buffer)) } catch (error) { fail(error) }
      } else if (event.kind === 'turn.error' || event.kind === 'provider.error' || event.kind === 'turn.cancelled') {
        fail(new Error(String(event.payload?.message ?? 'Agent 未能完成 Flow 规划。')))
      }
    }, () => fail(new Error('Agent 规划连接已断开，请重连后重试。')))

    options.sendMessage(session.id, prompt, options.task.task_id).catch(fail)
  })
}

function parseFlowPlan(text: string): FlowPlanPayload {
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('Agent 未返回可执行的结构化 Flow 计划。')
  let payload: unknown
  try { payload = JSON.parse(text.slice(start, end + 1)) } catch { throw new Error('Agent 未返回可执行的结构化 Flow 计划。') }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Agent 未返回可执行的结构化 Flow 计划。')
  const candidate = payload as Partial<FlowPlanPayload>
  if (typeof candidate.plan_id !== 'string' || !Array.isArray(candidate.steps) || candidate.steps.length === 0) {
    throw new Error('Agent 未返回可执行的结构化 Flow 计划。')
  }
  return candidate as FlowPlanPayload
}

function buildPlannerPrompt(task: AnalysisTask) {
  const datasets = task.snapshot_refs.filter((ref) => ref.kind === 'dataset').length
  const documents = task.snapshot_refs.filter((ref) => ref.kind === 'document').length
  const required = documents > 0
    ? '必须包含 inspect_sources、profile_data、extract_claims、align_evidence。'
    : '必须包含 inspect_sources、profile_data。'
  return [
    '你是 Data2Doc2Data 的 Flow 规划器。只输出一个 JSON 对象，不要 Markdown、解释或代码。',
    '这是纯规划任务：不要调用任何工具，不要执行命令，不要检查文件。不得读取或返回原始记录；宿主会在本地执行所有计算。不得使用 shell、code、command、raw、rows 或 records 参数。',
    `任务：${task.title}。目标：${task.goal}。输入：${datasets} 个数据快照，${documents} 份文本材料。`,
    `可用工具：inspect_sources、profile_data、query_data、extract_claims、align_evidence、test_hypothesis。${required}`,
    '格式：{"plan_id":"stable-id","steps":[{"step_id":"stable-id","tool":"registered_tool","purpose":"业务目的","dependencies":[],"arguments":{}}]}。',
    '最多 12 步，依赖必须无环；query_data 仅可传 metric，test_hypothesis 仅可传结构化 hypothesis。',
  ].join('\n')
}
