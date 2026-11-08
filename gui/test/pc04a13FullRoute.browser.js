// 在真实浏览器与隔离API运行，不拦截响应，不连接用户实验室。
export async function prepareModelBatch(page, {base, labId, chainIds}) {
  const response = await page.request.get(`${base}/api/v1/lab-profiles`)
  const rows = await response.json()
  const lab = (Array.isArray(rows)?rows:rows.items).find(row=>row.id===labId)
  if (!response.ok() || lab?.name !== 'PC13完整模拟隔离实验室') throw Error('不是本片隔离实验室')
  const panel = page.getByTestId('route-batch-panel')
  await panel.locator('.mantine-MultiSelect-input').click()
  for (const id of chainIds) await page.getByRole('option').filter({hasText:` · ${id}`}).click()
  await page.keyboard.press('Escape')
  await panel.getByLabel('批量频点（MHz，逗号分隔）', {exact:true}).fill('3500')
  await panel.getByLabel('批量请求功率（dBm，不作实测值）', {exact:true}).fill('-30')
  await panel.getByLabel('每项采样数（2–10）', {exact:true}).fill('5')
  await panel.getByLabel('按完整链路模型模拟（非实测）', {exact:true}).check()
  for (const id of chainIds) await panel.getByLabel(`参考天线／位置 ${id} @3500`, {exact:true}).fill('合成SGH 静区中心')
  await panel.getByLabel('已核对清单的固定接线条件', {exact:true}).check()
  await panel.getByLabel('已确认请求功率及现场安全条件', {exact:true}).check()
  await panel.getByRole('button', {name:'预览完整批清单',exact:true}).click()
  await panel.getByText(`服务器完整清单：${chainIds.length}项`, {exact:true}).waitFor()
  const started = page.waitForResponse(r=>r.url().endsWith('/route-calibration-batches')&&r.request().method()==='POST')
  await panel.getByRole('button', {name:'明确开始此批校准',exact:true}).click()
  const result = await started
  if (result.status() !== 202) throw Error(await result.text())
  return result.json()
}

// 分段执行，避免浏览器工具调用超时；每次人工确认仍由真实页面按钮提交。
export async function advanceModelBatch(page, {base, labId, jobId, steps=4}) {
  const url = `${base}/api/v1/lab-profiles/${labId}/route-calibration-batches/${jobId}`
  for (let index=0; index<steps; index++) {
    const reply = await page.request.get(url)
    if (!reply.ok()) throw Error(await reply.text())
    const row = await reply.json()
    if (row.status==='completed') return {status:row.status,count:row.items.length}
    if (row.status==='running') {await page.waitForTimeout(1000);continue}
    if (row.status!=='waiting_manual') throw Error(JSON.stringify({status:row.status,error:row.error}))
    await page.waitForFunction(id=>{
      const text=document.querySelector('[data-testid="batch-active-detail"] pre')?.textContent
      return text && JSON.parse(text).transition_id===id
    },row.transition_id,{timeout:30000})
    const manual=page.getByTestId('batch-manual')
    await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill(row.items[row.current_index].request.reference_antenna)
    await manual.getByLabel('确认仅对应当前项和当前人工步骤',{exact:true}).check()
    const response=page.waitForResponse(r=>r.url().endsWith('/continue')&&r.request().method()==='POST')
    await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click()
    const continued=await response
    if (!continued.ok()) throw Error(await continued.text())
  }
  const row=await(await page.request.get(url)).json()
  return {status:row.status,index:row.current_index,simulated:row.items.filter(i=>i.status==='simulated').length}
}

export async function verifyModelBatch(page, {base,labId,jobId,expectedNetLosses}) {
  const root=`${base}/api/v1/lab-profiles/${labId}`
  const row=await(await page.request.get(`${root}/route-calibration-batches/${jobId}`)).json()
  if (row.status!=='completed'||!row.finalization_committed||row.items.length!==32||row.f64_control_released!==null) throw Error('批次未完整结束或伪造实物释放证明')
  const records=[]
  for (const item of row.items) {
    const response=await page.request.get(`${root}/fixed-route-acquisitions/${item.run_id}`)
    if (!response.ok()) throw Error(await response.text())
    const record=await response.json(), result=record.result, cable=result.receive_cable_calibration
    if (item.status!=='simulated'||result.status!=='simulated'||result.formal_eligible!==false||result.cleanup_confirmed!==null||result.simulation_input_source!=='model_synthetic') throw Error('模拟边界错误')
    if (result.samples.length!==5||result.request.frequency_mhz!==3500||!result.exchanges.length||result.exchanges.some(e=>e.simulated!==true)) throw Error('样本或控制记录不完整')
    if (!cable?.run_id||cable.lab_profile_id!==labId||cable.simulated!==true||cable.frequency_mhz!==3500) throw Error('线缆记录身份错误')
    const expected=expectedNetLosses[result.request.chain_id]
    if (!Number.isFinite(expected)||Math.abs(result.net_loss_db-expected)>1e-9) throw Error('模型计算不符')
    for (const sample of result.samples) {
      const net=(sample.source_before_dbm+sample.source_after_dbm)/2-sample.received_dbm-cable.loss_db
      if (Math.abs(net-expected)>1e-9) throw Error('线缆未单次去嵌')
    }
    records.push(record)
  }
  return {job:row,records}
}
