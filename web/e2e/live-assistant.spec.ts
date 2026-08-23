import { expect, test } from '@playwright/test'

const liveTest = process.env.LIVE_ASSISTANT === '1' ? test : test.skip

liveTest('connects the real WorkBuddy CLI with read-only bounded task context', async ({ page }) => {
  test.setTimeout(180_000)
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  await page.goto('/')
  await page.getByRole('button', { name: '暂时跳过' }).click()
  await page.getByLabel('任务名称').fill('助手联调任务')
  await page.getByLabel('业务目标').fill('验证本地助手只接收有界任务上下文')
  await page.getByRole('button', { name: '创建分析任务' }).click()

  await page.getByLabel('本地助手').selectOption('workbuddy')
  await page.getByLabel('权限模式').selectOption('read_only')
  await page.getByRole('button', { name: '连接助手' }).click()
  await expect(page.getByText('腾讯 WorkBuddy / CodeBuddy 已连接')).toBeVisible({ timeout: 60_000 })

  await page.getByLabel('发送给助手').fill('请只根据 WORKBENCH TASK CONTEXT 回答，严格输出：任务=当前任务名称；锁定资产=数字。')
  await page.getByRole('button', { name: '发送' }).click()
  const reply = page.locator('.assistant-message--assistant')
  await expect(reply).toContainText('助手联调任务', { timeout: 120_000 })
  await expect(reply).toContainText(/锁定资产\s*=\s*0/)
  await expect(page.getByText('助手任务已完成。')).toBeVisible()
  expect(await page.locator('.assistant-approval').count()).toBe(0)
  expect(errors).toEqual([])
})
