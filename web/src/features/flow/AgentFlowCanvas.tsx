import { Background, Controls, MarkerType, ReactFlow, type Edge, type ReactFlowInstance } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { EvidenceGraphSpec, RunEvent } from '../../contracts/run-events'
import { FlowInspector } from './FlowInspector'
import { FlowNode, type AgentFlowNode } from './FlowNode'
import { laneForKind, projectFlowEvents, type FlowLane } from './flow-projection'
import { useReadableEventStream } from './readable-event-stream'

const nodeTypes = { agentFlow: FlowNode }
const lanes: Array<{ id: FlowLane; label: string; number: string }> = [
  { id: 'inputs', label: '输入材料', number: '01' },
  { id: 'compute', label: '本地计算', number: '02' },
  { id: 'reasoning', label: '交叉推理', number: '03' },
  { id: 'verification', label: '证据核验', number: '04' },
  { id: 'delivery', label: '结论交付', number: '05' },
]
const relationshipColors: Record<string, string> = {
  derived_from: '#6f6b60', supports: '#00a955', contradicts: '#c43d3d', tests: '#b87621', insufficient_for: '#8a8477',
}

export function AgentFlowCanvas({ events, graph }: { events: RunEvent[]; graph: EvidenceGraphSpec }) {
  const reducedMotion = Boolean(useReducedMotion())
  const { visibleEvents, pendingCount, paused, speed, revealLatest, togglePaused, setSpeed } = useReadableEventStream(events, reducedMotion)
  const projection = useMemo(() => enrichProjection(projectFlowEvents(visibleEvents), graph), [visibleEvents, graph])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [flow, setFlow] = useState<ReactFlowInstance<AgentFlowNode, Edge> | null>(null)
  const selected = projection.nodes.find((node) => node.id === selectedId) ?? null
  const activeNodes = new Set(projection.activeNodeIds)
  const activeEdges = new Set(projection.activeEdgeIds)
  const rows = new Map<FlowLane, number>()
  const nodes: AgentFlowNode[] = projection.nodes.map((node) => {
    const laneIndex = lanes.findIndex((lane) => lane.id === node.lane)
    const row = rows.get(node.lane) ?? 0
    rows.set(node.lane, row + 1)
    return {
      id: node.id,
      type: 'agentFlow',
      position: { x: laneIndex * 200 + 28, y: row * 150 + 64 },
      data: { label: node.label, kind: node.kind, lane: node.lane, status: node.status, active: activeNodes.has(node.id), addedAt: node.addedAt },
    }
  })
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges: Edge[] = projection.edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: relationshipLabel(edge.relationship),
      animated: !reducedMotion && activeEdges.has(edge.id),
      markerEnd: { type: MarkerType.ArrowClosed, color: relationshipColors[edge.relationship] ?? '#6f6b60' },
      style: { stroke: relationshipColors[edge.relationship] ?? '#6f6b60', strokeWidth: activeEdges.has(edge.id) ? 3 : 1.5 },
      className: edge.conflicted ? 'agent-flow-edge--conflict' : undefined,
    }))
  const completed = visibleEvents.some((event) => event.kind === 'run.completed')
  const terminal = completed || visibleEvents.some((event) => event.kind === 'run.failed' || event.kind === 'run.interrupted')
  const cycleProgress = analysisCycleProgress(visibleEvents)
  const previousViewport = useRef({ nodeCount: 0, terminal: false })

  useEffect(() => {
    if (!flow) return
    const previous = previousViewport.current
    previousViewport.current = { nodeCount: nodes.length, terminal }
    if (!shouldAutoFitFlow(previous.nodeCount, nodes.length, previous.terminal, terminal)) return
    const frame = window.requestAnimationFrame(() => {
      flow.fitView({ duration: reducedMotion ? 0 : 240, padding: .14, maxZoom: .9 })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [flow, nodes.length, reducedMotion, terminal])

  function focusNode(nodeId: string) {
    setSelectedId(nodeId)
    const duration = reducedMotion ? 0 : 280
    flow?.fitView({ nodes: [{ id: nodeId }], duration, padding: .9, maxZoom: 1.1 })
  }

  function jumpToResult() {
    if (pendingCount > 0) {
      revealLatest()
      return
    }
    if (!terminal) return
    const last = projection.nodes.at(-1)
    if (last) focusNode(last.id)
    else flow?.fitView({ duration: reducedMotion ? 0 : 280, padding: .2 })
  }

  const jumpLabel = pendingCount > 0 ? `跳到实时 · ${pendingCount}` : !terminal ? '等待结果' : completed ? '跳到结果' : '查看终态'
  return <section className="agent-flow-surface" aria-labelledby="agent-flow-title">
    <header className="agent-flow-heading">
      <div><p className="eyebrow">LIVE AGENT FLOW</p><h2 id="agent-flow-title">分析过程与证据联动</h2><p>这是可审计事件回放，不是模型隐性思维过程。</p></div>
      <div className="agent-flow-heading__actions">
        <div className="agent-flow-status" role="status"><span data-state={completed ? 'completed' : paused ? 'paused' : 'running'} />{completed ? '分析完成' : paused ? '回放已暂停' : 'Flow 构建中'}<b>{cycleProgress.maxRounds ? `${cycleProgress.completedRounds} / ${cycleProgress.maxRounds} 轮 · ${cycleProgress.artifactCount} 产物` : `${projection.lastSequence} / ${events.at(-1)?.sequence ?? 0} EVENTS`}</b></div>
        {!reducedMotion && pendingCount > 0 && <div className="agent-flow-playback-controls">
          <button className="button button--quiet" type="button" onClick={togglePaused}>{paused ? '继续播放' : '暂停播放'}</button>
          <label>播放速度<select aria-label="播放速度" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
            <option value={0.75}>0.75×</option><option value={1}>1×</option><option value={1.5}>1.5×</option><option value={2}>2×</option>
          </select></label>
        </div>}
      </div>
    </header>
    {reducedMotion && <p className="reduced-motion-notice">已按减少动态效果设置直接展示全部事件</p>}
    <footer className="agent-flow-stepbar" aria-label="执行轨道">
      <div><h3>执行轨道</h3><b>{projection.nodes.length} / {projection.edges.length}</b></div>
      <nav aria-label="Flow 节点导航">{projection.nodes.map((node) => <button key={node.id} type="button" data-active={selectedId === node.id || undefined} onClick={() => focusNode(node.id)}><span>{String(node.addedAt).padStart(2, '0')}</span>{node.label}</button>)}</nav>
      <button className="button button--quiet" type="button" onClick={jumpToResult} disabled={!terminal && pendingCount === 0}>{jumpLabel}</button>
    </footer>
    <div className="agent-flow-workspace">
      <div className="agent-flow-stage" aria-label="实时 Agent Flow 画布">
        <div className="agent-flow-lanes" aria-hidden="true">{lanes.map((lane) => <span key={lane.id}><b>{lane.number}</b>{lane.label}</span>)}</div>
        {nodes.length ? <ReactFlow<AgentFlowNode, Edge>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onInit={setFlow}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
          fitViewOptions={{ padding: .18, maxZoom: .95 }}
          minZoom={.35}
          maxZoom={1.4}
          nodesConnectable={false}
          nodesDraggable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#d7d1c4" gap={24} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow> : <div className="agent-flow-awaiting"><span>等待第一个证据节点</span><strong>Flow 将随本地工具事件逐步构建</strong><p>{projection.activeTool ? `正在执行 ${projection.activeTool.name || projection.activeTool.stepId}` : '正在解析任务与输入材料'}</p></div>}
      </div>
      <FlowInspector projection={projection} selected={selected} />
    </div>
  </section>
}

export function shouldAutoFitFlow(previousNodeCount: number, nodeCount: number, wasTerminal: boolean, terminal: boolean) {
  return (previousNodeCount === 0 && nodeCount > 0) || (!wasTerminal && terminal)
}

export function analysisCycleProgress(events: RunEvent[]) {
  let maxRounds = 0
  let completedRounds = 0
  let artifactCount = 0
  for (const event of events) {
    if (event.kind === 'cycle.started') maxRounds = Number(event.summary.max_rounds) || maxRounds
    if (event.kind === 'round.completed') {
      completedRounds = Math.max(completedRounds, Number(event.summary.round_number) || 0)
      artifactCount += Number(event.summary.artifact_count) || 0
    }
  }
  return { completedRounds, maxRounds, artifactCount }
}

function enrichProjection(projection: ReturnType<typeof projectFlowEvents>, graph: EvidenceGraphSpec) {
  const byId = new Map(graph.nodes.map((node) => [node.node_id, node]))
  return {
    ...projection,
    nodes: projection.nodes.map((node) => {
      const persisted = byId.get(node.id)
      return persisted ? { ...node, label: persisted.label, kind: persisted.kind, status: persisted.status, lane: laneForKind(persisted.kind), artifactRef: persisted.artifact_ref } : node
    }),
  }
}

function relationshipLabel(relationship: string) {
  return ({ derived_from: '派生', supports: '支持', contradicts: '冲突', tests: '检验', insufficient_for: '不足' } as Record<string, string>)[relationship] ?? relationship
}
