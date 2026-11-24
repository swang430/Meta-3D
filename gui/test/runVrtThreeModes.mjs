import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const baseURL = process.env.VRT_TEST_URL
assert(baseURL && ['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname), '请指定本地模拟测试服务')
const browser = await chromium.launch({ channel: process.env.CHROMIUM_CHANNEL })
try {
  const page = await browser.newPage({ baseURL, viewport: { width: 1600, height: 1000 } })
  await page.goto('/')
  await page.getByText('测试管理', { exact: true }).first().click()
  await page.getByRole('tab', { name: '虚拟路测' }).click()
  await page.getByText('OTA测试', { exact: true }).first().click()
  await page.getByRole('button', { name: '执行测试' }).first().click()
  await page.getByRole('dialog', { name: '辐射测试准备与执行' }).waitFor({timeout: 5000})
} finally {
  await browser.close()
}
