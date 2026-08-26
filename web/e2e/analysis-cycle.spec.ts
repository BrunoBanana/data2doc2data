import { expect, test } from '@playwright/test'

test('persists a three-round data-and-text cycle with inspectable local artifacts', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 })
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await page.getByRole('button', { name: '立即体验 Demo' }).click()
  await page.getByRole('button', { name: '运行 Demo：大促增收、利润与履约恶化' }).click()

  const startedResponse = page.waitForResponse((response) => response.request().method() === 'POST' && /\/api\/workbench\/tasks\/[^/]+\/runs$/.test(response.url()))
  await page.getByRole('button', { name: '运行分析' }).click()
  const started = await (await startedResponse).json() as { run: { run_id: string } }
  await expect(page.getByRole('button', { name: /跳到实时/ })).toBeVisible()
  await page.getByRole('button', { name: /跳到实时/ }).click()
  await expect(page.getByText('分析完成')).toBeVisible({ timeout: 30_000 })
  const diagnostics = page.getByRole('region', { name: '深度诊断产物' })
  await expect(diagnostics.getByRole('heading', { name: '深度诊断产物' })).toBeVisible()
  await expect(diagnostics.getByText(/tfidf_(?:nmf_kmeans|fallback)/)).toBeVisible()
  await expect(page.getByRole('img', { name: /关键词词云/ })).toBeVisible()

  const detailResponse = await page.request.get(`/api/workbench/runs/${encodeURIComponent(started.run.run_id)}`)
  expect(detailResponse.ok()).toBe(true)
  const detail = await detailResponse.json() as {
    events: Array<{ kind: string; summary: Record<string, unknown>; artifact_refs: string[] }>
    artifact_dashboard: { blocks: Array<{ kind: string; provenance: { artifact_ref: string }; observations: Record<string, unknown> }> }
  }
  const planned = detail.events.filter((event) => event.kind === 'round.planned')
  const artifacts = detail.events.filter((event) => event.kind === 'artifact.created')
  expect(planned).toHaveLength(3)
  expect(artifacts).toHaveLength(3)
  expect(artifacts.every((event) => event.artifact_refs.length === 1)).toBe(true)
  expect(planned[1].summary.prior_artifact_refs).toEqual(artifacts[0].artifact_refs)
  expect(planned[2].summary.prior_artifact_refs).toEqual(artifacts[1].artifact_refs)
  const textBlock = detail.artifact_dashboard.blocks.find((block) => block.kind === 'text_ml')
  expect(textBlock?.provenance.artifact_ref).toMatch(/^artifact-text-/)
  expect(String(textBlock?.observations.word_cloud_svg)).toMatch(/^<svg/)
  expect(JSON.stringify({ planned, artifacts })).not.toMatch(/raw_rows|\/Users\/|data_path|document_paths/)

  await page.reload()
  await page.getByRole('button', { name: /大促增收、利润与履约恶化/ }).first().click()
  await page.getByRole('tab', { name: '历史' }).click()
  await page.getByRole('button', { name: new RegExp(`回放 ${started.run.run_id}`) }).click()
  const restoredDiagnostics = page.getByRole('region', { name: '深度诊断产物' })
  await expect(restoredDiagnostics.getByRole('heading', { name: '深度诊断产物' })).toBeVisible()
  await expect(restoredDiagnostics.getByText(/tfidf_(?:nmf_kmeans|fallback)/)).toBeVisible()
  expect(errors).toEqual([])
})

test('keeps deep diagnostics readable without horizontal overflow at 390px', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await page.getByRole('button', { name: '立即体验 Demo' }).click()
  await page.getByRole('button', { name: '运行 Demo：增长提速、留存承压' }).click()
  await page.getByRole('button', { name: '运行分析' }).click()
  await expect(page.getByRole('heading', { name: '深度诊断产物' })).toBeVisible()
  await expect(page.getByRole('img', { name: /关键词词云/ })).toBeVisible()
  await page.getByRole('button', { name: '过程', exact: true }).click()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  expect(await page.getByRole('tab').evaluateAll((tabs) => tabs.every((tab) => tab.scrollWidth <= tab.clientWidth + 1))).toBe(true)
  const cardsFit = await page.locator('.diagnostic-card').evaluateAll((cards) => cards.every((card) => {
    const bounds = card.getBoundingClientRect()
    return bounds.left >= 0 && bounds.right <= document.documentElement.clientWidth + 1
  }))
  expect(cardsFit).toBe(true)
})
