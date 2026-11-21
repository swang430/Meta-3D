// 在已启动的工作台页面运行，替换工程接口以检查切换和重试行为。
;async (page) => {
  const check = (value, message) => {
    if (!value) throw Error(message)
  }
  let uploads = 0
  let rejectBuild = false
  const builds = []
  await page.route('**/mpdb-projects/**', async (route) => {
    if (route.request().url().endsWith('/import')) {
      check(
        route.request().postDataBuffer().includes('name="file"'),
        '缺少文件字段',
      )
      uploads++
      return route.fulfill({ json: { source_id: 'batch-' + uploads, clustering:'matched',
        timing:{frame_ids:[0,1],distances_m:[2],source_times_s:null,time_source:null} } })
    }
    builds.push(route.request().postDataJSON())
    if (rejectBuild)
      return route.fulfill({ status: 422, json: { detail: '样本不足' } })
    return route.fulfill({
      json: { download_url: '/example.zip', asc_count: 8 },
    })
  })
  await page.getByText('信道工作台', { exact: true }).first().click()
  const pane = page
    .getByRole('heading', { name: '从 MPDB 创建信道工程' })
    .locator('xpath=../..')
  const build = pane.getByRole('button', { name: '生成信道工程' })
  const speed = pane.getByLabel('操作员假定的恒定速度（m/s）')
  const download = pane.getByRole('link', { name: '下载工程' })
  const select = (name) =>
    pane
      .locator('input[type=file]')
      .first()
      .setInputFiles({
        name,
        mimeType: 'application/zip',
        buffer: Buffer.from('fixture'),
      })
  const mode = (label) =>
    pane.locator('label').filter({ hasText: label }).click()
  await select('first.zip')
  check(!(await speed.isVisible()), '传导模式显示了播放参数')
  await build.click()
  await download.waitFor()
  check(
    Object.keys(builds[0]).join() === 'mode' && builds[0].mode === 'conducted',
    '传导请求包含播放参数',
  )
  await mode('空口（OTA）')
  await pane.getByLabel('播放时间的依据').click()
  await page.getByRole('option',{name:'假定恒速，由各段位移推算时长'}).click()
  await speed.fill('7')
  await pane.getByLabel('输出更新率（Hz）').fill('100')
  rejectBuild = true
  await build.click()
  await pane.getByText('生成工程失败：样本不足').waitFor()
  rejectBuild = false
  await build.click()
  await download.waitFor()
  check(
    uploads === 1 && builds.at(-1).speed_m_s === 7,
    '重复上传或播放参数错误',
  )
  const review = page.getByText('查看或核验已有工程', { exact: true })
  const history = review.locator('..')
  check(!(await history.getByText('选择工程目录').isVisible()), '已有工程默认展开')
  await review.click()
  await history.getByText('选择工程目录').waitFor()
  check(!(await history.getByText('从原始文件导入轨迹').count()), '计算工具混入工程复查')
  await page.getByText('核验聚簇结果', { exact: true }).first().click()
  await page.getByRole('heading', { name: '聚簇结果核验' }).waitFor()
  await review.click()
  check(
    (await download.isVisible()) && (await speed.inputValue()) === '7',
    '切换入口丢失工程',
  )
  await mode('传导')
  await download.waitFor()
  check(!(await speed.isVisible()), '传导显示了空口播放参数')
  await select('second.zip')
  check(!(await download.isVisible()), '传导结果串批')
  await mode('空口（OTA）')
  check(!(await download.isVisible()), '空口结果串批')
}
