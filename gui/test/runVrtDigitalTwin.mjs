// 指向独立测试数据库和模拟仪器的本地服务；此脚本创建执行、接线和报告记录。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const baseURL = process.env.VRT_TEST_URL
if (!baseURL || !['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname)) throw Error('请指定本地测试服务 VRT_TEST_URL')
const browser = await chromium.launch({ channel: process.env.CHROMIUM_CHANNEL })
const page = await browser.newPage({ baseURL, viewport: { width: 1600, height: 1000 } })
const root = '/api/v1/road-test'
async function json(response) {
  assert(response.ok(), await response.text())
  return response.json()
}
async function openLibrary() {
  await page.goto('/')
  await page.getByText('测试管理', { exact: true }).first().click()
  await page.getByText('虚拟路测', { exact: true }).first().click()
}
try {
  if (!(await json(await page.request.get('/api/v1/lab-profiles'))).length) {
    const chambers = await json(await page.request.get('/api/v1/chambers'))
    await json(await page.request.post('/api/v1/lab-profiles', { data: {
      name: '数字孪生浏览器测试实验室', chamber_config_id: chambers.items[0].id, instrument_bindings: [],
    } }))
  }
  await openLibrary()
  const scenario = (await json(await page.request.get(root + '/scenarios')))[0]
  const topology = await json(await page.request.post(root + '/topologies', { data: {
    name: '浏览器验证用模拟接线', topology_type: 'MIMO_2x2',
    base_station: { device_id: 'bs', model: '模拟', tx_ports: 2, max_bandwidth_mhz: 100 },
    channel_emulator: { device_id: 'ce', model: '模拟', input_ports: 2, output_ports: 2 },
    dut: { device_id: 'ue', model: '模拟', antenna_ports: 2 }, connections: [],
  } }))
  const conducted = await json(await page.request.post(root + '/executions', { data: {
    mode: 'conducted', scenario_id: scenario.id, topology_id: topology.id,
  } }))
  const button = name => page.getByRole('button', { name, exact: true })
  async function openCard() {
    await page.getByText('数字孪生', { exact: true }).first().click()
    await page.locator('.mantine-Card-root').filter({ has: page.getByText(scenario.name, { exact: true }) }).getByRole('button', { name: '执行测试' }).click()
  }
  await openCard()
  await page.getByLabel(/随机种子/).fill('7')
  const creation = page.waitForResponse(r => r.url().endsWith('/executions') && r.request().method() === 'POST')
  await button('启动数字孪生').click()
  const record = await json(await creation)
  assert.equal(record.config.digital_twin.model_parameters.seed, 7)
  const url = root + '/executions/' + record.execution_id
  await button('停止数字孪生').waitFor()
  await page.getByText('模拟时间轴', { exact: true }).waitFor()
  await openLibrary()
  await openCard()
  await page.getByText(new RegExp(record.execution_id)).waitFor()
  await page.getByRole('dialog').locator('tbody tr').nth(2).waitFor()
  await button('停止数字孪生').click()
  await button('查看模拟报告').waitFor()
  const stopped = await json(await page.request.get(url + '/timeline'))
  assert(stopped.points.length >= 3)
  await page.getByRole('textbox', { name: '选择传导记录进行对照' }).click()
  await page.getByRole('option', { name: new RegExp(conducted.execution_id) }).click()
  await page.getByText('对照未核验。', { exact: true }).waitFor()
  assert.equal(await page.getByText(/下行吞吐率差值/).count(), 0)
  await button('查看模拟报告').click()
  await page.getByText('数字孪生模拟报告', { exact: true }).waitFor()
  const report = await json(await page.request.get(url + '/report'))
  assert.equal(report.simulation_timeline.formal_kpi, false)
  assert.deepEqual(report.kpi_summary, [])
  assert.deepEqual(report.simulation_timeline.points, stopped.points)
  await page.getByRole('dialog', { name: '测试报告', exact: true }).locator('.mantine-Modal-close').click()
  await button('归档模拟报告').click()
  await page.getByText(/归档报告编号/).waitFor()
  const download = await page.getByRole('link', { name: '下载模拟报告' }).getAttribute('href')
  const archive = await json(await page.request.get(download.replace(/\/download$/, '')))
  assert.equal(archive.content_data.pass_rate, null)
  assert.equal(archive.content_data.overall_result, 'incomplete')
  assert.deepEqual(archive.content_data.kpi_summary, [])
  assert.deepEqual(archive.content_data.simulation_timeline, stopped)
  const pdf = await page.request.get(download)
  assert(pdf.ok() && (await pdf.body()).subarray(0, 4).toString() === '%PDF')
  await button('重新准备模拟执行').click()
  const replayCreation = page.waitForResponse(r => r.url().endsWith('/executions') && r.request().method() === 'POST')
  await button('启动数字孪生').click()
  const replay = await json(await replayCreation)
  assert.deepEqual(replay.config.digital_twin, record.config.digital_twin)
  await button('生成剩余模拟样本并结束').click()
  await button('查看模拟报告').waitFor()
  const full = await json(await page.request.get(root + '/executions/' + replay.execution_id + '/timeline'))
  assert.deepEqual(full.points.slice(0, stopped.points.length), stopped.points)
  assert(full.points.length > stopped.points.length)
  const completedReport = await json(await page.request.get(root + '/executions/' + replay.execution_id + '/report'))
  assert.equal(completedReport.overall_result, 'undetermined')
  assert.deepEqual(completedReport.kpi_summary, [])
  await page.getByRole('dialog').locator('.mantine-Modal-close').click()
  await page.getByRole('tabpanel', { name: '虚拟路测' }).getByRole('tab', { name: '执行历史' }).click()
  await page.getByRole('row').filter({ hasText: record.execution_id.slice(0, 12) }).getByRole('button', { name: '回看模拟执行' }).click()
  await page.getByText('模拟时间轴', { exact: true }).waitFor()
  assert.deepEqual(await json(await page.request.get(url + '/timeline')), stopped)
  console.log('通过相同模型输入复算、启动、刷新恢复、停止、历史、缺少证据的传导对照、模拟报告与归档下载', record.execution_id)
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(-1800))
  throw error
} finally {
  await browser.close()
}
