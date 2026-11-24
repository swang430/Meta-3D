// 连接已登记八路 ASC 的隔离模拟实验室。所有控制和报告均由真实 API 处理。
;async (page, fixture) => {
  const check = (value, message) => { if (!value) throw Error(message) }
  const button = name => page.getByRole('button', { name, exact: true })
  async function openScenario() {
    await page.getByText('测试管理', { exact: true }).first().click()
    await page.getByRole('tab', { name: '虚拟路测' }).click()
    const card = page.locator('.mantine-Card-root').filter({ hasText: fixture.scenario })
    await card.getByRole('button', { name: '执行测试' }).click()
    await page.getByRole('dialog', { name: '传导测试准备与执行' }).waitFor()
  }
  await openScenario()
  check(await button('启动传导测试').isDisabled(), '缺少绑定却允许启动')
  if (fixture.missingCalibrationFile) {
    const submitted = page.waitForResponse(r => r.url().endsWith('/conducted/calibrations') && r.request().method() === 'POST')
    await page.getByLabel('实验室已审核目录中的报告文件名').fill(fixture.missingCalibrationFile)
    await button('登记逐端口校准').click()
    const response = await submitted
    const { detail } = await response.json()
    check(response.request().postDataJSON().report_file === fixture.missingCalibrationFile, '登记请求缺少报告文件名')
    check(response.status() === 422 && typeof detail === 'string', '缺少已审核原件时应返回具体原因')
    await page.getByText(detail, { exact: true }).waitFor()
    check(await button('启动传导测试').isDisabled(), '登记失败后放行了启动')
  }
  for (const [label, name] of [['实验室',fixture.lab],['接线方案',fixture.topology],['可播放工程',fixture.asset]]) {
    await page.getByRole('textbox', { name: label, exact: true }).click()
    await page.getByRole('option', { name, exact: false }).click()
  }
  await page.getByText(fixture.sha256, { exact: false }).first().waitFor()
  if (fixture.wrongLab) {
    const chooseLab = async name => {
      const checked = page.waitForResponse(r => r.url().endsWith('/conducted/prepare') && r.request().method() === 'POST')
      await page.getByRole('textbox', { name: '实验室', exact: true }).click()
      await page.getByRole('option', { name, exact: true }).click()
      return (await checked).json()
    }
    const wrong = await chooseLab(fixture.wrongLab)
    check(!wrong.ready && wrong.reasons.some(message => message.includes('电缆')), '错接没有定位到电缆')
    await page.getByText(wrong.reasons.find(message => message.includes('电缆')), { exact: true }).waitFor()
    check((await chooseLab(fixture.lab)).ready, '改回正确接线后仍不能准备')
  }
  if (fixture.rejectFirstPlayback) {
    const saved = page.waitForResponse(r => r.url().endsWith('/conducted/executions') && r.request().method() === 'POST')
    await button('保存准备记录').click()
    const rejected = await (await saved).json()
    const refusal = page.waitForResponse(r => r.url().endsWith(rejected.execution_id + '/control'))
    await button('启动传导测试').click()
    check((await refusal).status() === 409, '驱动拒绝后服务端仍报成功')
    await page.getByText(new RegExp('执行编号 ' + rejected.execution_id + '.*执行失败')).waitFor()
    await button('重新准备一次执行').click()
  }
  const created = page.waitForResponse(r => r.url().endsWith('/conducted/executions') && r.request().method() === 'POST')
  await button('保存准备记录').click()
  const createResponse = await created
  check(createResponse.status() === 201, '准备记录未保存')
  const record = await createResponse.json()
  const snapshot = record.config.conducted
  check(record.mode === 'conducted' && snapshot.asset.sha256 === fixture.sha256 && snapshot.asset.mock_only, '记录的运行方式或数据摘要错误')
  check(snapshot.port_mapping.length === 8 && snapshot.asset.links.length === 8, '记录缺少八路映射或文件')
  const root = '/api/v1/road-test/executions/' + record.execution_id
  const started = page.waitForResponse(r => r.url().endsWith(root + '/control'))
  await button('启动传导测试').click()
  const startResponse = await started
  check(startResponse.ok(), '启动失败 ' + await startResponse.text())
  await page.reload()
  await openScenario()
  await page.getByText(new RegExp('执行编号 ' + record.execution_id)).waitFor()
  await button('查看报告').waitFor({ timeout: 90000 })
  await button('查看报告').click()
  const response = await page.request.get(root + '/report')
  const report = await response.json()
  check(report.overall_result === 'undetermined' && report.pass_rate === null, '模拟数据影响正式结论')
  check(report.observations.length > 0 && report.observations.every(o => ['simulated', 'unverified'].includes(o.provenance)), '模拟样本来源标错或丢失')
  await page.keyboard.press('Escape')
  const archived = page.waitForResponse(r => r.url().endsWith(root + '/archive-report'))
  await button('归档报告').click()
  const archiveResponse = await archived
  check(archiveResponse.ok(), '归档失败 ' + await archiveResponse.text())
  const archive = await archiveResponse.json()
  await page.getByText('归档报告编号 ' + archive.id).waitFor()
  check(archive.status === 'completed', '归档文件尚未生成')
  const link = page.getByRole('link', { name: '下载归档报告' })
  check(await link.getAttribute('href') === '/api/v1/reports/' + archive.id + '/download', '下载链接没有指向本次归档')
  const download = page.waitForEvent('download')
  await link.click()
  check(!(await (await download).failure()), '浏览器下载归档失败')
  const pdf = await page.request.get('/api/v1/reports/' + archive.id + '/download')
  check(pdf.ok() && (await pdf.body()).subarray(0, 5).toString() === '%PDF-', '归档无法下载为 PDF')
  await button('重新准备一次执行').click()
  const retried = page.waitForResponse(r => r.url().endsWith('/conducted/executions') && r.request().method() === 'POST')
  await button('保存准备记录').click()
  const retry = await (await retried).json()
  check(retry.execution_id !== record.execution_id, '新执行覆盖了已归档的记录')
  await button('启动传导测试').click()
  await page.getByText(new RegExp('执行编号 ' + retry.execution_id + '.*运行中')).waitFor()
  await button('停止本次执行').click()
  await page.getByText(new RegExp('执行编号 ' + retry.execution_id + '.*已停止')).waitFor()
  const stopped = await page.request.get('/api/v1/road-test/executions/' + retry.execution_id + '/report')
  check((await stopped.json()).overall_result === 'incomplete', '中途停止被判成已测完')
  return { execution: record.execution_id, archive: archive.id, samples: report.observations.length, verdict: report.overall_result }
}
