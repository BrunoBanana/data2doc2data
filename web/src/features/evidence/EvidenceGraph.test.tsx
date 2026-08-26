import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EvidenceGraph } from './EvidenceGraph'
import type { EvidenceGraphSpec } from '../../contracts/run-events'

const graph: EvidenceGraphSpec = { contract_version: 1, graph_id: 'graph-1', nodes: [
  { node_id: 'signal-1', kind: 'data_signal', label: '收入下降 8%', status: 'verified', artifact_ref: 'dashboard-1' },
  { node_id: 'claim-1', kind: 'claim', label: '收入目标增长', status: 'contradicted', artifact_ref: 'claim-source' },
  { node_id: 'hypothesis-1', kind: 'hypothesis', label: '价格调整导致收入下降', status: 'supported', artifact_ref: null },
  { node_id: 'validation-1', kind: 'validation', label: '收入方向符合假设', status: 'supported', artifact_ref: 'validation-artifact' },
  { node_id: 'hypothesis-2', kind: 'hypothesis', label: '渠道结构没有变化', status: 'contradicted', artifact_ref: null },
  { node_id: 'validation-2', kind: 'validation', label: '渠道变化反驳该假设', status: 'contradicted', artifact_ref: 'segment-artifact' },
  { node_id: 'hypothesis-3', kind: 'hypothesis', label: '仓库延迟导致退款', status: 'insufficient', artifact_ref: null },
  { node_id: 'validation-3', kind: 'validation', label: '缺少仓库维度', status: 'insufficient', artifact_ref: null },
  { node_id: 'conclusion-1', kind: 'conclusion', label: '一项支持、一项冲突、一项待补证', status: 'supported', artifact_ref: 'graph-1' },
  { node_id: 'action-1', kind: 'action', label: '补充仓库和渠道明细后重新运行', status: 'pending', artifact_ref: 'graph-1' },
], edges: [
  { edge_id: 'edge-1', source: 'signal-1', target: 'claim-1', relationship: 'contradicts' },
  { edge_id: 'edge-2', source: 'validation-1', target: 'hypothesis-1', relationship: 'tests' },
  { edge_id: 'edge-3', source: 'signal-1', target: 'validation-1', relationship: 'supports' },
  { edge_id: 'edge-4', source: 'validation-2', target: 'hypothesis-2', relationship: 'tests' },
  { edge_id: 'edge-5', source: 'signal-1', target: 'validation-2', relationship: 'contradicts' },
  { edge_id: 'edge-6', source: 'validation-3', target: 'hypothesis-3', relationship: 'tests' },
  { edge_id: 'edge-7', source: 'signal-1', target: 'validation-3', relationship: 'insufficient_for' },
  { edge_id: 'edge-8', source: 'conclusion-1', target: 'action-1', relationship: 'derived_from' },
] }

describe('EvidenceGraph', () => {
  it('filters and expands evidence nodes without exposing private reasoning', () => {
    render(<EvidenceGraph graph={graph} question="为什么收入下降？" />)

    expect(screen.getByRole('heading', { name: '假设生成与验证树' })).toBeInTheDocument()
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('为什么收入下降？')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('价格调整导致收入下降')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('收入方向符合假设')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('获得支持')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('存在冲突')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('证据不足')
    expect(screen.getByLabelText('可验证假设树')).toHaveTextContent('补充仓库和渠道明细后重新运行')
    expect(screen.getByText('这里只展示公开决策摘要、注册工具结果与证据关系，不展示模型私有思维链。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重放生成过程' }))
    expect(screen.getAllByText('已验证').length).toBeGreaterThan(0)
    expect(screen.getAllByText('存在冲突').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: '存在冲突' }))
    expect(screen.getAllByText('收入目标增长').length).toBeGreaterThan(0)
    expect(screen.queryByText('收入下降 8%')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByText('收入目标增长')[0])
    expect(screen.getByRole('dialog')).toHaveTextContent('claim-source')
  })
})
