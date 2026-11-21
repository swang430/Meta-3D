// 在仅注册离线工作台接口的隔离实例运行；库中已有 RT-IMT-2030.smu。
// 验证实际按钮、保存请求、刷新后的同一资产；不操作生产库或仪器。
;async (page) => {
  const assets = async () => {
    const result = await page.request.get('/api/v1/channel-assets')
    if (!result.ok()) throw Error('读取隔离资产库失败')
    return result.json()
  }
  const original = await assets()
  const a = original.find(row => row.name === 'RT-IMT-2030')
  if (!a || a.payload.rt_scene) throw Error('需要尚未列为场景的原始验收记录')
  await page.getByText('信道工作台', {exact:true}).first().click()
  const tab = name => page.locator('label').filter({hasText:new RegExp('^'+name+'$')}).click()
  await tab('厂商文件')
  const saved = page.waitForResponse(r => r.url().endsWith('/channel-assets/'+a.id) && r.request().method()==='PUT')
  await page.getByRole('row').filter({hasText:a.name}).getByRole('button',{name:'列为 RT 场景'}).click()
  const r = await saved
  if (!r.ok() || r.request().postDataJSON().rt_scene !== true) throw Error('未保存原资产的 RT 场景分类')
  await tab('RT 动态')
  await page.getByRole('row').filter({hasText:a.associated_file_path}).waitFor()
  const after = await assets()
  const same = after.find(row => row.id===a.id)
  if (after.length!==original.length || same?.payload.rt_scene!==true || same.canonical_name!==a.canonical_name)
    throw Error('场景没有引用原始记录或意外改变了规范名')
}
