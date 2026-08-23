import { useEffect, useMemo, useRef, useState } from 'react'

import type { AgentApproval, AgentEvent, AgentProviderStatus, AgentSession, AnalysisTask } from '../../contracts/workbench'
import { ApprovalCard } from './ApprovalCard'
import { SafeMarkdown } from './SafeMarkdown'

type PermissionMode = AgentSession['permission_mode']

interface AssistantDrawerProps {
  task: AnalysisTask
  agents: AgentProviderStatus[]
  createSession: (provider: string, permissionMode: PermissionMode) => Promise<AgentSession>
  sendMessage: (sessionId: string, message: string, taskId: string) => Promise<void>
  interrupt: (sessionId: string) => Promise<void>
  decideApproval: (sessionId: string, approvalId: string, approved: boolean) => Promise<void>
  openEventStream: (sessionId: string, after: number, onEvent: (event: AgentEvent, eventId: number) => void, onError: () => void) => () => void
}

interface Message { id: string; role: 'user' | 'assistant'; text: string }
interface Operation { key: string; title: string; text: string }

export function AssistantDrawer(props: AssistantDrawerProps) {
  const usable = useMemo(() => props.agents.filter((agent) => agent.available && agent.authenticated && agent.compatible), [props.agents])
  const preferred = usable.find((agent) => agent.name === 'workbuddy')?.name ?? usable[0]?.name ?? ''
  const [provider, setProvider] = useState(preferred)
  const [permissionMode, setPermissionMode] = useState<PermissionMode>('collaborative')
  const [session, setSession] = useState<AgentSession | null>(null)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [operations, setOperations] = useState<Operation[]>([])
  const [approvals, setApprovals] = useState<AgentApproval[]>([])
  const [notice, setNotice] = useState(usable.length ? '连接后，助手只接收当前任务的有界上下文。' : '未发现可用助手；确定性分析仍可使用。')
  const [turnActive, setTurnActive] = useState(false)
  const lastEventId = useRef(0)
  const closeStream = useRef<(() => void) | null>(null)
  const turnId = useRef(0)

  useEffect(() => () => closeStream.current?.(), [])

  function attachStream(sessionId: string) {
    closeStream.current?.()
    closeStream.current = props.openEventStream(sessionId, lastEventId.current, handleEvent, () => {
      setNotice('助手连接暂时中断；已接收内容会保留，可重新发送。')
    })
  }

  function handleEvent(event: AgentEvent, eventId: number) {
    lastEventId.current = Math.max(lastEventId.current, eventId)
    const payload = event.payload ?? {}
    if (event.kind === 'context.attached') {
      const compressed = payload.compressed ? ' · 已压缩' : ''
      setNotice(`任务证据已附带${compressed} · ${Number(payload.record_count ?? 0)} 条记录`)
      return
    }
    if (event.kind === 'message.delta') {
      const fragment = typeof payload.text === 'string' ? payload.text : ''
      setMessages((current) => {
        const id = `assistant-${turnId.current}`
        const existing = current.find((item) => item.id === id)
        return existing ? current.map((item) => item.id === id ? { ...item, text: item.text + fragment } : item) : [...current, { id, role: 'assistant', text: fragment }]
      })
      return
    }
    const operation = operationFromEvent(event)
    if (operation) {
      setOperations((current) => {
        const existing = current.find((item) => item.key === operation.key)
        return existing ? current.map((item) => item.key === operation.key ? { ...item, text: item.text + operation.text } : item) : [...current, operation]
      })
      return
    }
    if (event.kind === 'approval.request' && typeof payload.request_id === 'string') {
      setApprovals((current) => current.some((item) => item.request_id === payload.request_id) ? current : [payload as unknown as AgentApproval, ...current])
      return
    }
    if (['turn.completed', 'turn.cancelled', 'turn.error', 'provider.error'].includes(event.kind)) {
      setTurnActive(false)
      setNotice(event.kind === 'turn.completed' ? '助手任务已完成。' : event.kind === 'turn.cancelled' ? '助手任务已停止。' : String(payload.message ?? '助手暂时不可用。'))
      closeStream.current?.()
      closeStream.current = null
    }
  }

  async function connect() {
    if (!provider) return
    setNotice('正在连接本地助手…')
    try {
      const created = await props.createSession(provider, permissionMode)
      setSession(created)
      lastEventId.current = 0
      attachStream(created.id)
      setNotice(`${providerLabel(created.provider)} 已连接`)
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '助手连接失败。')
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const copy = message.trim()
    if (!session || !copy || turnActive) return
    turnId.current += 1
    setMessage('')
    setMessages((current) => [...current, { id: `user-${turnId.current}`, role: 'user', text: copy }])
    setOperations([])
    setTurnActive(true)
    if (!closeStream.current) attachStream(session.id)
    try {
      await props.sendMessage(session.id, copy, props.task.task_id)
      setNotice('助手正在基于当前任务处理…')
    } catch (reason) {
      setTurnActive(false)
      setNotice(reason instanceof Error ? reason.message : '无法发送给助手。')
    }
  }

  async function stop() {
    if (!session || !turnActive) return
    try {
      await props.interrupt(session.id)
      setNotice('正在停止当前任务…')
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : '无法停止当前任务。')
    }
  }

  return <aside className="assistant-drawer" aria-label="AI 助手">
    <div className="assistant-heading"><div><p className="eyebrow">协作分析</p><h2>AI 助手</h2></div><span className={`connection-badge${session ? ' connection-badge--ready' : ''}`}>{session ? '已连接' : '本地'}</span></div>
    {!session && <div className="assistant-connect-panel">
      <label>本地助手<select aria-label="本地助手" value={provider} onChange={(event) => setProvider(event.target.value)} disabled={!usable.length}>{usable.length ? usable.map((agent) => <option value={agent.name} key={agent.name}>{providerLabel(agent.name)}</option>) : <option value="">未发现可用助手</option>}</select></label>
      <label>权限模式<select aria-label="权限模式" value={permissionMode} onChange={(event) => setPermissionMode(event.target.value as PermissionMode)}><option value="read_only">只读</option><option value="collaborative">协作 · 每次变更需批准</option><option value="trusted_session">信任本次会话</option></select></label>
      <button className="button button--secondary" type="button" disabled={!provider} onClick={connect}>连接助手</button>
    </div>}
    <div className="assistant-context"><span>当前任务</span><strong>{props.task.title}</strong><small>{props.task.snapshot_refs.length} 项锁定资产 · 不发送原始数据</small></div>
    <p className="assistant-notice" role="status">{notice}</p>
    <div className="assistant-operation-queue" aria-label="助手操作">
      {approvals.map((approval) => <ApprovalCard key={approval.request_id} approval={approval} decide={(approved) => session ? props.decideApproval(session.id, approval.request_id, approved) : Promise.reject(new Error('助手未连接'))} />)}
      {operations.map((operation) => <article className="assistant-operation" key={operation.key}><strong>{operation.title}</strong><pre>{operation.text}</pre></article>)}
    </div>
    <div className="assistant-conversation" role="log" aria-live="polite" aria-busy={turnActive}>
      {messages.length ? messages.map((item) => <article className={`assistant-message assistant-message--${item.role}`} key={item.id}><span>{item.role === 'user' ? '你' : '助手'}</span><SafeMarkdown text={item.text} /></article>) : <div className="assistant-empty"><div className="assistant-orb" aria-hidden="true" /><strong>{session ? '可以继续分析' : '先连接本地助手'}</strong><p>Dashboard、计算过程和证据链仍是工作台中心。</p></div>}
    </div>
    <form className="assistant-composer" onSubmit={submit}><label htmlFor="assistant-message">发送给助手</label><textarea id="assistant-message" rows={3} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="解释证据、提出假设或建议下一步…" disabled={!session || turnActive} maxLength={20_000} /><div><button className="button button--quiet" type="button" aria-label="停止当前任务" disabled={!turnActive} onClick={stop}>停止</button><button className="button button--primary" type="submit" disabled={!session || turnActive || !message.trim()}>发送</button></div></form>
  </aside>
}

function providerLabel(provider: string) {
  if (provider === 'workbuddy' || provider === 'codebuddy') return '腾讯 WorkBuddy / CodeBuddy'
  if (provider === 'codex') return 'Codex CLI'
  return provider
}

function operationFromEvent(event: AgentEvent): Operation | null {
  const payload = event.payload ?? {}
  const text = typeof payload.text === 'string' ? payload.text : typeof payload.diff === 'string' ? payload.diff : typeof payload.result === 'string' ? payload.result : JSON.stringify(payload.result ?? payload.arguments ?? '', null, 2)
  if (event.kind === 'plan.delta') return { key: `plan-${event.kind}`, title: '执行计划', text }
  if (event.kind === 'command.output') return { key: `command-${event.kind}`, title: '命令输出', text }
  if (event.kind === 'file.diff') return { key: `diff-${String(payload.path ?? 'file')}`, title: `文件差异 · ${String(payload.path ?? '未知文件')}`, text }
  if (event.kind === 'tool.call') return { key: `tool-${String(payload.call_id ?? payload.name ?? 'current')}`, title: `工具调用 · ${String(payload.name ?? '工具')}`, text }
  if (event.kind === 'tool.result') return { key: `tool-result-${String(payload.call_id ?? 'current')}`, title: payload.error ? '操作失败' : '操作完成', text }
  return null
}
