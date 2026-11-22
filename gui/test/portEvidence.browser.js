// 在端口分析面板运行，验证按需请求、参数边界、异常定位及原始报告下载。
export async function checkPortEvidence(page) {
  let requests = 0
  const report = { status: 'warning', message: '成员核对发现差异。',
    summary: ['已核对成员，再比较时延。'], warnings: [{frame: 1, tx: 2, rx: 0, cluster: 7}],
    frames: [{frame: 1}], parameters: {points: 257} }
  await page.route('**/mpdb-projects/port-evidence', route => {
    requests++
    const data = route.request().postDataBuffer().toString()
    if (data.includes('name="amplitude_floor"') || !data.includes('name="archive"'))
      throw Error('可选参数或原始文件传递错误')
    return route.fulfill({json: report})
  })
  const pane = page.locator('form').filter({hasText: '开始只读分析'})
  await pane.locator('[name=archive]').setInputFiles({name:'原始.zip', mimeType:'application/zip', buffer: Buffer.from('fixture')})
  for (const [name, invalid, valid] of [
    ['bandwidth_mhz', ['0','10001'], '10000'],
    ['points', ['1','4','259'], '257'],
    ['amplitude_floor', ['0','-1'], ''],
  ]) {
    const field = pane.locator('[name=' + name + ']')
    for (const value of invalid) {
      await field.fill(value)
      if (await field.evaluate(el => el.checkValidity())) throw Error(name + ' 放行无效值')
    }
    await field.fill(valid)
  }
  if (requests) throw Error('选择参数触发了计算')
  await pane.getByRole('button', {name:'开始只读分析'}).click()
  await pane.getByText('发现异常', {exact:true}).waitFor()
  await pane.getByText(report.summary[0]).waitFor()
  await pane.getByText('异常位置：帧 1，发射端口 2，接收端口 0，簇 7').waitFor()
  const link = pane.getByRole('link', {name:'下载完整分析结果'})
  const file = await link.evaluate(async el => (await fetch(el.href)).json())
  if (requests !== 1 || JSON.stringify(file) !== JSON.stringify(report)) throw Error('下载内容有误')
  await pane.locator('[name=points]').fill('3')
  if (await link.count()) throw Error('修改参数后仍显示旧结果')
}
