import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ArtifactDashboardSpec } from '../../contracts/dashboard'
import { DiagnosticBlocks } from './DiagnosticBlocks'

describe('DiagnosticBlocks', () => {
  it('renders anomaly evidence with method, sample, and limitations', () => {
    const dashboard: ArtifactDashboardSpec = {
      contract_version: 1,
      dashboard_id: 'dashboard-cycle-1',
      blocks: [{
        block_id: 'block-artifact-1', kind: 'anomalies', title: '检测到 1 个异常点。', status: 'completed',
        provenance: { artifact_ref: 'artifact-1', method: 'detect_anomalies', sample_size: 10, limitations: ['异常不代表因果。'] },
        observations: { anomaly_count: 1, anomalies: [{ date: '2026-04-13', value: 50, robust_score: 8.2 }] },
      }],
    }

    render(<DiagnosticBlocks dashboard={dashboard} />)

    expect(screen.getByRole('heading', { name: '深度诊断产物' })).toBeInTheDocument()
    expect(screen.getByText('稳健异常检测')).toBeInTheDocument()
    expect(screen.getByText('detect_anomalies')).toBeInTheDocument()
    expect(screen.getByText('样本 10')).toBeInTheDocument()
    expect(screen.getByText('2026-04-13')).toBeInTheDocument()
    expect(screen.getByText('异常不代表因果。')).toBeInTheDocument()
  })

  it('renders only a locally generated safe word cloud svg', () => {
    const dashboard: ArtifactDashboardSpec = {
      contract_version: 1,
      dashboard_id: 'dashboard-cycle-2',
      blocks: [{
        block_id: 'block-text', kind: 'text_ml', title: '文本主题与聚类', status: 'completed',
        provenance: { artifact_ref: 'artifact-text', method: 'tfidf_nmf_kmeans', sample_size: 2, limitations: [] },
        observations: { word_cloud_svg: '<svg role="img" aria-label="关键词词云：退款、延迟"><text>退款</text></svg>', topics: [] },
      }],
    }

    render(<DiagnosticBlocks dashboard={dashboard} />)

    expect(screen.getByRole('img', { name: '关键词词云：退款、延迟' })).toBeInTheDocument()
  })

  it('renders contribution rows and text clusters as inspectable evidence', () => {
    const dashboard: ArtifactDashboardSpec = {
      contract_version: 1,
      dashboard_id: 'dashboard-cycle-3',
      blocks: [
        {
          block_id: 'block-contribution', kind: 'contribution', title: 'GMV 变化贡献', status: 'completed',
          provenance: { artifact_ref: 'artifact-contribution', method: 'decompose_change', sample_size: 48, limitations: [] },
          observations: { total_delta: -120, contributors: [{ member: '华东', baseline: 800, current: 680, delta: -120, contribution_percent: 100 }] },
        },
        {
          block_id: 'block-text', kind: 'text_ml', title: '文本主题与聚类', status: 'completed',
          provenance: { artifact_ref: 'artifact-text', method: 'tfidf_nmf_kmeans', sample_size: 2, limitations: [] },
          observations: { topics: [], clusters: [{ cluster_id: 'cluster-1', label: '履约延迟', keywords: ['延迟', '缺货'], documents: ['ops-review.md'] }] },
        },
      ],
    }

    render(<DiagnosticBlocks dashboard={dashboard} />)

    expect(screen.getByRole('table', { name: '贡献分解明细' })).toHaveTextContent('华东800680-120100%')
    expect(screen.getByRole('list', { name: '文本聚类' })).toHaveTextContent('履约延迟延迟 · 缺货1 份材料')
  })

  it('surfaces bounded scalar findings instead of hiding them in artifact json', () => {
    const dashboard: ArtifactDashboardSpec = {
      contract_version: 1, dashboard_id: 'dashboard-cycle-4', blocks: [{
        block_id: 'block-period', kind: 'period_comparison', title: '当前期下降', status: 'completed',
        provenance: { artifact_ref: 'artifact-period', method: 'compare_periods', sample_size: 20, limitations: [] },
        observations: { baseline: 0.72, current: 0.64, absolute_change: -0.08, change_percent: -11.11, baseline_count: 10, current_count: 10 },
      }],
    }

    render(<DiagnosticBlocks dashboard={dashboard} />)

    expect(screen.getByLabelText('关键计算结果')).toHaveTextContent('基准值0.72当前值0.64绝对变化-0.08变化率-11.11%')
  })

  it('explains an unavailable diagnostic instead of showing an ambiguous evidence label', () => {
    const dashboard: ArtifactDashboardSpec = {
      contract_version: 1, dashboard_id: 'dashboard-cycle-5', blocks: [{
        block_id: 'block-text', kind: 'text_ml', title: '文本主题与聚类', status: 'unavailable',
        provenance: { artifact_ref: 'artifact-text', method: 'tfidf_fallback', sample_size: 1, limitations: [] },
        observations: {},
      }],
    }

    render(<DiagnosticBlocks dashboard={dashboard} />)

    expect(screen.getByText('不可用')).toBeInTheDocument()
    expect(screen.getByText('当前输入不足以完成该方法；产物已保留，可补充材料后安全重试。')).toBeInTheDocument()
  })
})
