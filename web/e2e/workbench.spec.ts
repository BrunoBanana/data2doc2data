import { expect, test } from '@playwright/test'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

test('completes the model-free task journey and downloads an offline report', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await page.getByRole('button', { name: '立即体验 Demo' }).click()
  await page.getByRole('button', { name: '运行 Demo：增长提速、留存承压' }).click()
  await expect(page.getByRole('heading', { name: '数据概览' })).toBeVisible()
  await expect(page.getByText('记录数').locator('..')).toContainText('208')
  await expect(page.getByRole('group', { name: '选择趋势指标' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'MRR', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '8 周留存率', exact: true }).click()
  await expect(page.getByRole('button', { name: '8 周留存率', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('当前值').locator('..')).toContainText('%')
  await expect(page.getByRole('heading', { name: '指标摘要' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '样本' })).toBeVisible()

  await page.getByRole('tab', { name: '文本' }).click()
  await expect(page.getByRole('heading', { name: '文本材料分析' })).toBeVisible()
  await expect(page.getByText('4 份文档 · 0 个失败')).toBeVisible()

  await page.getByRole('button', { name: '运行分析' }).click()
  await expect(page.getByRole('heading', { name: '分析过程与证据联动' })).toBeVisible()
  await expect(page.getByText('这是可审计事件回放，不是模型隐性思维过程。')).toBeVisible()
  await expect(page.getByRole('button', { name: '暂停播放' })).toBeVisible()
  await page.waitForTimeout(1_200)
  await expect(page.getByText('分析完成')).not.toBeVisible()
  await page.getByRole('button', { name: /跳到实时/ }).click()
  await expect(page.getByText('分析完成')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByLabel('协议交接')).toContainText('→')
  await expect(page.getByLabel('协议交接')).toContainText('TRACE run-')
  await expect(page.getByText('确定性 Demo Flow 正在本地执行…')).not.toBeVisible()
  const visibleNodes = await page.locator('.agent-flow-node').evaluateAll((nodes) => nodes.filter((node) => {
    const bounds = node.getBoundingClientRect()
    return bounds.width > 0 && bounds.height > 0 && bounds.right > 0 && bounds.bottom > 0 && bounds.left < innerWidth && bounds.top < innerHeight
  }).length)
  expect(visibleNodes).toBeGreaterThanOrEqual(12)
  await page.getByRole('tab', { name: '假设' }).click()
  await expect(page.getByRole('heading', { name: '假设生成与验证树' })).toBeVisible()
  const hypothesisTree = page.getByLabel('可验证假设树')
  await expect(hypothesisTree).toContainText('02 · HYPOTHESIS')
  await expect(hypothesisTree).toContainText('03 · DETERMINISTIC CHECK')
  await expect(hypothesisTree).toContainText('NEXT EVIDENCE / ACTION')
  await page.getByRole('button', { name: '重放生成过程' }).click()
  if (process.env.VISUAL_QA_CAPTURE === '1') {
    await page.getByRole('main').evaluate((element) => { element.scrollTop = 0 })
    await page.screenshot({ path: path.resolve('../docs/design-references/2026-08-24/final/implementation-1440x1024.png') })
  }
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 HTML 报告' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^data2doc2data-task-.+\.html$/)
  const reportPath = testInfo.outputPath(download.suggestedFilename())
  await download.saveAs(reportPath)
  const reportPage = await page.context().newPage()
  const externalRequests: string[] = []
  reportPage.on('request', (request) => {
    if (/^https?:/.test(request.url())) externalRequests.push(request.url())
  })
  await reportPage.goto(pathToFileURL(reportPath).href)
  await expect(reportPage).toHaveTitle('增长提速、留存承压 · Data2Doc2Data 分析报告')
  await expect(reportPage.getByRole('heading', { name: '分析结论' })).toBeVisible()
  await expect(reportPage.getByRole('heading', { name: '通信与恢复审计' })).toBeVisible()
  await expect(reportPage.getByText(/TRACE run-/).first()).toBeVisible()
  await expect(reportPage.getByLabel('证据验证')).toBeVisible()
  await expect(reportPage.getByRole('heading', { name: '假设生成与验证树' })).toBeVisible()
  await expect(reportPage.getByRole('heading', { name: '完整证据明细' })).toBeVisible()
  await expect(reportPage.locator('.tree-branch').first()).toBeVisible()
  await expect(reportPage.locator('.tree-action')).toBeVisible()
  await expect(reportPage.getByRole('heading', { name: '来源与计算口径' })).toBeVisible()
  await expect(reportPage.getByText(/customer-research\.md · 第/).first()).toBeVisible()
  await expect(reportPage.locator('meta[http-equiv="Content-Security-Policy"]')).toHaveAttribute('content', /default-src 'none'/)
  await expect(reportPage.locator('svg').first()).toBeVisible()
  expect(externalRequests).toEqual([])
  await reportPage.close()
  expect(errors).toEqual([])
})

for (const caseName of ['增长提速、留存承压', '大促增收、利润与履约恶化']) {
  test(`loads and analyzes the complete flagship case: ${caseName}`, async ({ page }) => {
    const errors: string[] = []
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
    await page.goto('/')
    await page.getByRole('button', { name: '立即体验 Demo' }).click()
    await page.getByRole('button', { name: `运行 Demo：${caseName}` }).click()
    await expect(page.getByRole('heading', { name: caseName })).toBeVisible()
    await expect(page.getByRole('heading', { name: '数据概览' })).toBeVisible()
    await page.getByRole('tab', { name: '文本' }).click()
    await expect(page.getByRole('heading', { name: '文本材料分析' })).toBeVisible()
    expect(await page.locator('.claim-card').count()).toBeGreaterThanOrEqual(3)
    await page.getByRole('button', { name: '运行分析' }).click()
    await expect(page.getByRole('heading', { name: '数据证据摘要' })).toBeVisible()
    await expect(page.getByLabel('实时 Agent Flow 画布')).toBeVisible()
    await expect(page.getByRole('heading', { name: '执行轨道' })).toBeVisible()
    await expect(page.getByRole('button', { name: /跳到实时/ })).toBeVisible()
    await page.getByRole('button', { name: /跳到实时/ }).click()
    await expect(page.getByText('分析完成')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByLabel('Flow 图统计')).toContainText(/\d+节点.*\d+关系/)
    expect(await page.locator('.agent-flow-node').count()).toBeGreaterThan(4)
    expect(errors).toEqual([])
  })
}

test('keeps the complete workbench usable at 390px and honors reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.getByRole('button', { name: '立即体验 Demo' }).click()
  await page.getByRole('button', { name: '运行 Demo：增长提速、留存承压' }).click()
  await expect(page.getByRole('heading', { name: '增长提速、留存承压' })).toBeVisible()
  const sampleColumn = page.getByRole('columnheader', { name: '样本' })
  await expect(sampleColumn).toBeVisible()
  const sampleColumnBounds = await sampleColumn.boundingBox()
  expect((sampleColumnBounds?.x ?? 391) + (sampleColumnBounds?.width ?? 0)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: '运行分析' }).click()
  await expect(page.getByText('已按减少动态效果设置直接展示全部事件')).toBeVisible()
  await expect(page.getByText('分析完成')).toBeVisible()
  await page.getByRole('button', { name: '过程', exact: true }).click()
  const flowTrackOverlapsCanvas = await page.evaluate(() => {
    const track = document.querySelector('.agent-flow-stepbar')?.getBoundingClientRect()
    const stage = document.querySelector('.agent-flow-stage')?.getBoundingClientRect()
    if (!track || !stage) return true
    return track.top < stage.bottom && track.bottom > stage.top
  })
  expect(flowTrackOverlapsCanvas).toBe(false)
  for (const view of ['分析', '过程', '助手']) {
    await page.getByRole('button', { name: view, exact: true }).click()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  }
  await expect(page.getByRole('complementary', { name: '分析员笔记' })).toBeVisible()
})

test('keeps all workbench columns and the agent composer inside a 1440x1024 viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  await page.goto('/')
  await page.getByRole('button', { name: '立即体验 Demo' }).click()
  await page.getByRole('button', { name: '运行 Demo：增长提速、留存承压' }).click()

  const drawer = page.getByRole('complementary', { name: '分析员笔记' })
  const composer = drawer.locator('[data-fixed-region="composer"]')
  await expect(drawer).toBeVisible()
  await expect(composer).toBeVisible()
  const initialComposer = await composer.boundingBox()
  expect(initialComposer?.y).toBeGreaterThan(0)
  expect((initialComposer?.y ?? 0) + (initialComposer?.height ?? 0)).toBeLessThanOrEqual(1024)
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(1024)

  await page.getByRole('main').evaluate((element) => { element.scrollTop = element.scrollHeight })
  const afterScrollComposer = await composer.boundingBox()
  expect(afterScrollComposer?.y).toBe(initialComposer?.y)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
})
