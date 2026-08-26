import { type CSSProperties, useMemo, useState } from 'react'

import type { EvidenceEdge, EvidenceGraphSpec, EvidenceNode } from '../../contracts/run-events'

const statusLabels: Record<EvidenceNode['status'], string> = {
  pending: '待验证',
  verified: '已验证',
  supported: '获得支持',
  contradicted: '存在冲突',
  insufficient: '证据不足',
}

const relationshipLabels: Record<EvidenceEdge['relationship'], string> = {
  derived_from: '派生自',
  supports: '支持',
  contradicts: '反证',
  tests: '检验',
  insufficient_for: '证据不足',
}

interface HypothesisBranch {
  hypothesis: EvidenceNode
  validation: EvidenceNode | null
  evidence: Array<{ node: EvidenceNode; relationship: EvidenceEdge['relationship'] }>
}

interface HypothesisTreeProjection {
  branches: HypothesisBranch[]
  conclusion: EvidenceNode | null
  action: EvidenceNode | null
}

export function projectHypothesisTree(graph: EvidenceGraphSpec): HypothesisTreeProjection {
  const nodeById = new Map(graph.nodes.map((node) => [node.node_id, node]))
  const branches = graph.nodes.filter((node) => node.kind === 'hypothesis').map((hypothesis) => {
    const testEdge = graph.edges.find((edge) => {
      if (edge.relationship !== 'tests') return false
      const source = nodeById.get(edge.source)
      const target = nodeById.get(edge.target)
      return (edge.target === hypothesis.node_id && source?.kind === 'validation')
        || (edge.source === hypothesis.node_id && target?.kind === 'validation')
    })
    const validationId = testEdge
      ? (testEdge.source === hypothesis.node_id ? testEdge.target : testEdge.source)
      : null
    const validation = validationId ? nodeById.get(validationId) ?? null : null
    const evidence = validation ? graph.edges.flatMap((edge) => {
      if (edge.relationship === 'tests') return []
      const otherId = edge.target === validation.node_id
        ? edge.source
        : edge.source === validation.node_id ? edge.target : null
      const node = otherId ? nodeById.get(otherId) : null
      return node && node.kind !== 'hypothesis' && node.kind !== 'conclusion' && node.kind !== 'action'
        ? [{ node, relationship: edge.relationship }]
        : []
    }) : []
    return { hypothesis, validation, evidence }
  })
  return {
    branches,
    conclusion: graph.nodes.find((node) => node.kind === 'conclusion') ?? null,
    action: graph.nodes.find((node) => node.kind === 'action') ?? null,
  }
}

function verdict(branch: HypothesisBranch) {
  return branch.validation?.status ?? branch.hypothesis.status
}

export function HypothesisTree({ graph, question }: { graph: EvidenceGraphSpec; question: string }) {
  const [replay, setReplay] = useState(0)
  const projection = useMemo(() => projectHypothesisTree(graph), [graph])

  return <section className="hypothesis-tree-product" aria-labelledby="hypothesis-tree-title">
    <header className="hypothesis-tree__header">
      <div><p className="eyebrow">OBSERVABLE HYPOTHESIS TREE</p><h2 id="hypothesis-tree-title">假设生成与验证树</h2></div>
      <button className="button button--quiet" type="button" onClick={() => setReplay((value) => value + 1)}>重放生成过程</button>
    </header>
    <div className="hypothesis-tree__body" aria-label="可验证假设树" key={replay}>
      <article className="hypothesis-tree__question">
        <span>01 · BUSINESS QUESTION</span>
        <strong>{question}</strong>
      </article>
      {projection.branches.length ? <div className="hypothesis-tree__branches">
        {projection.branches.map((branch, index) => {
          const status = verdict(branch)
          const evidenceSummary = branch.evidence.length
            ? branch.evidence.map(({ relationship }) => relationshipLabels[relationship]).filter((value, item, values) => values.indexOf(value) === item).join(' · ')
            : '等待证据接入'
          return <article className="hypothesis-tree__branch" data-status={status} key={branch.hypothesis.node_id} style={{ '--branch-index': index } as CSSProperties}>
            <div className="hypothesis-tree__stage"><span>02 · HYPOTHESIS {String(index + 1).padStart(2, '0')}</span><strong>{branch.hypothesis.label}</strong></div>
            <div className="hypothesis-tree__connector" aria-hidden="true"><i /></div>
            <div className="hypothesis-tree__stage"><span>03 · DETERMINISTIC CHECK</span><strong>{branch.validation?.label ?? '尚未生成验证步骤'}</strong><small>{branch.evidence.length} 条显式证据 · {evidenceSummary}</small></div>
            <div className="hypothesis-tree__verdict"><span>04 · VERDICT</span><b>{statusLabels[status]}</b></div>
          </article>
        })}
      </div> : <article className="hypothesis-tree__empty"><strong>尚未生成结构化假设</strong><span>运行分析后，系统会把注册工具结果投影为可审计分支。</span></article>}
      <div className="hypothesis-tree__outcome">
        <article><span>05 · CONCLUSION</span><strong>{projection.conclusion?.label ?? '等待所有假设完成验证'}</strong></article>
        <article className="hypothesis-tree__action"><span>NEXT EVIDENCE / ACTION</span><strong>{projection.action?.label ?? '根据证据缺口安排下一轮分析'}</strong></article>
      </div>
    </div>
    <p className="hypothesis-tree__boundary">这里只展示公开决策摘要、注册工具结果与证据关系，不展示模型私有思维链。</p>
  </section>
}
