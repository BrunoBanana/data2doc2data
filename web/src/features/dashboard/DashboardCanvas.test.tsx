import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DashboardSpec } from '../../contracts/dashboard'
import { DashboardCanvas } from './DashboardCanvas'

const provenance = { snapshot_id: 'dataset-1', sha256: 'a'.repeat(64), expression: 'count rows', fields: ['date'], result_row_count: 1 }
const dashboard: DashboardSpec = {
  contract_version: 1,
  dashboard_id: 'dashboard-1',
  title: '数据概览',
  blocks: [
    { block_id: 'records', kind: 'kpi', title: '记录数', value: 12, data: [], provenance },
    { block_id: 'trend', kind: 'chart', title: '指标趋势', value: null, provenance: { ...provenance, result_row_count: 4 }, data: [{ date: '2026-01-01', metric: 'gmv', value: 4_000_000 }, { date: '2026-02-01', metric: 'gmv', value: 4_200_000 }, { date: '2026-01-01', metric: 'gross_margin_rate', value: .36 }, { date: '2026-02-01', metric: 'gross_margin_rate', value: .315 }], chart: { mark: 'line', encoding: { x: { field: 'date', type: 'temporal' }, y: { field: 'value', type: 'quantitative' }, color: { field: 'metric', type: 'nominal' } }, transforms: [] } },
    { block_id: 'table', kind: 'table', title: '指标分布', value: null, provenance: { ...provenance, result_row_count: 1 }, data: [{ metric: 'gross_margin_rate', count: 26, minimum: .271, maximum: .36, average: .315 }] },
  ],
}

describe('DashboardCanvas', () => {
  it('renders KPIs, charts, tables and source-backed provenance', () => {
    render(<DashboardCanvas dashboard={dashboard} />)

    expect(screen.getByText('记录数').parentElement).toHaveTextContent('12')
    expect(screen.getByRole('heading', { name: '指标趋势' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '指标摘要' })).toBeInTheDocument()
    expect(screen.getByLabelText('选择趋势指标')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'GMV' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: '毛利率' }))
    expect(screen.getByRole('img', { name: '毛利率趋势图' })).toBeInTheDocument()
    expect(screen.getAllByText('31.5%')).toHaveLength(2)
    expect(screen.getByRole('table')).toHaveTextContent('指标均值范围样本')
    expect(screen.getByRole('table')).toHaveTextContent(/毛利率.*31\.5%.*27\.1%–36\.0%.*26/)
    expect(screen.queryByText('minimum')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: '查看依据' })[0])
    expect(screen.getByRole('dialog')).toHaveTextContent('count rows')
  })

  it('rejects unknown chart operators instead of rendering them', () => {
    const unsafe = structuredClone(dashboard)
    unsafe.blocks[1].chart!.transforms = [{ type: 'execute' }]

    render(<DashboardCanvas dashboard={unsafe} />)

    expect(screen.getByRole('alert')).toHaveTextContent('不受支持')
  })
})
