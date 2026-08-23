import { expect, test } from '@playwright/test'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const dataset = path.resolve('../src/data2doc2data/sample/scenarios/growth-quality-alert/metrics.csv')
const document = path.resolve('../src/data2doc2data/sample/scenarios/growth-quality-alert/strategy.md')

test('completes the model-free task journey and downloads an offline report', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await page.getByLabel('任务名称').fill('增长质量复盘')
  await page.getByLabel('业务目标').fill('解释激活与留存变化并形成证据报告')
  await page.getByRole('button', { name: '创建分析任务' }).click()

  await page.getByLabel('本地数据文件路径').fill(dataset)
  await page.getByRole('button', { name: '预览数据' }).click()
  await expect(page.getByText('12 条记录')).toBeVisible()
  await page.getByRole('button', { name: '确认映射并导入' }).click()
  await expect(page.getByRole('heading', { name: '数据概览' })).toBeVisible()
  await expect(page.getByText('记录数').locator('..')).toContainText('12')

  await page.getByRole('tab', { name: '文本' }).click()
  await page.getByLabel('文档路径').fill(`${document}\n${path.resolve('../missing-synthetic-document.md')}`)
  await page.getByRole('button', { name: '导入文本材料' }).click()
  await expect(page.getByRole('heading', { name: '文本材料分析' })).toBeVisible()
  await expect(page.getByText('1 份文档 · 1 个失败')).toBeVisible()

  await page.getByRole('button', { name: '运行分析' }).click()
  await expect(page.getByRole('heading', { name: '分析过程与证据联动' })).toBeVisible()
  await expect(page.getByText('这是可审计事件回放，不是模型隐性思维过程。')).toBeVisible()
  await page.getByRole('button', { name: '跳到结果' }).click()
  await expect(page.getByText('分析完成')).toBeVisible()

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
  await expect(reportPage.getByRole('heading', { name: '分析结论' })).toBeVisible()
  await expect(reportPage.getByLabel('证据验证')).toBeVisible()
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
    await page.getByRole('button', { name: `加载案例：${caseName}` }).click()
    await expect(page.getByRole('heading', { name: caseName })).toBeVisible()
    await expect(page.getByRole('heading', { name: '数据概览' })).toBeVisible()
    await page.getByRole('tab', { name: '文本' }).click()
    await expect(page.getByRole('heading', { name: '文本材料分析' })).toBeVisible()
    await expect(page.locator('.claim-card')).toHaveCount(3)
    await page.getByRole('button', { name: '运行分析' }).click()
    await expect(page.getByRole('heading', { name: '数据证据摘要' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '执行轨道' })).toBeVisible()
    await page.getByRole('button', { name: '跳到结果' }).click()
    await expect(page.getByText('分析完成')).toBeVisible()
    await expect(page.getByText(/\d+ 个节点 · \d+ 条关系/)).toBeVisible()
    expect(errors).toEqual([])
  })
}

test('keeps the complete workbench usable at 390px and honors reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.getByRole('button', { name: '加载案例：增长提速、留存承压' }).click()
  await expect(page.getByRole('heading', { name: '增长提速、留存承压' })).toBeVisible()
  await page.getByRole('button', { name: '运行分析' }).click()
  await expect(page.getByText('已按减少动态效果设置直接展示全部事件')).toBeVisible()
  await expect(page.getByText('分析完成')).toBeVisible()
  for (const view of ['分析', '过程', '助手']) {
    await page.getByRole('button', { name: view, exact: true }).click()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  }
  await expect(page.getByRole('complementary', { name: '分析员笔记' })).toBeVisible()
})
