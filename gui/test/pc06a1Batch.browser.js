// 由真实浏览器会话载入；非Node CLI。真实API响应不拦截、不伪造。
export default async function pc06a1Batch(page, {base='http://127.0.0.1:5188', output='output/pc06a1-task6'}={}) {
  page.setDefaultTimeout(10000)
  const status=await (await page.request.get(`${base}/api/v1/instruments/hal/status`)).json()
  if(status.mode!=='mock'||status.driver_count!==3)throw Error('只允许本片隔离全Mock环境')
  const open=async()=>{
    await page.getByRole('tab',{name:'实验室配置',exact:true}).click()
    await page.getByRole('tab',{name:'射频拓扑',exact:true}).click()
    await page.getByTestId('route-batch-panel').waitFor()
  }
  await page.goto(base);await open()
  const panel=page.getByTestId('route-batch-panel')
  const labs=await(await page.request.get(`${base}/api/v1/lab-profiles`)).json()
  const lab=(Array.isArray(labs)?labs:labs.items).find(l=>l.name==='PC06A1 隔离全Mock验收')
  if(!lab)throw Error('缺少隔离实验室，不运行到用户实验室')
  const root=`${base}/api/v1/lab-profiles/${lab.id}/route-calibration-batches`
  const get=async id=>{
    const r=await page.request.get(`${root}/${id}`);if(!r.ok())throw Error(await r.text());return r.json()
  }
  const waitState=async(id,predicate)=>{
    for(let n=0;n<100;n++){
      const row=await get(id);if(predicate(row))return row
      await page.waitForTimeout(100)
    }
    throw Error(`批未到达预期状态：${JSON.stringify(await get(id))}`)
  }
  const prepare=async()=>{
    await page.waitForFunction(()=>document.querySelector('[data-testid="route-batch-panel"] fieldset')?.disabled===false)
    await panel.locator('.mantine-MultiSelect-root').click()
    for(const chain of ['conn_p0h','conn_p0v'])await page.getByRole('option').filter({hasText:chain}).click()
    await page.keyboard.press('Escape')
    await panel.getByLabel('批量频点（MHz，逗号分隔）',{exact:true}).fill('2595,3500')
    await panel.getByLabel('批量请求功率（dBm，不作实测值）',{exact:true}).fill('-30')
    await panel.getByLabel('每项采样数（2–10）',{exact:true}).fill('2')
    for(const c of ['conn_p0h','conn_p0v'])for(const f of [2595,3500]){
      await panel.getByLabel(`参考天线／位置 ${c} @${f}`,{exact:true}).fill(`REF ${c} 中心`)
      await panel.getByLabel(`接收线损（dB） ${c} @${f}`,{exact:true}).fill('2')
      await panel.getByLabel(`接收线依据 ${c} @${f}`,{exact:true}).fill(`隔离记录 ${f}MHz`)
    }
    await panel.getByRole('checkbox',{name:'已核对清单的固定接线条件',exact:true}).check()
    await panel.getByRole('checkbox',{name:'已确认请求功率及现场安全条件',exact:true}).check()
    await panel.getByRole('button',{name:'预览完整批清单',exact:true}).click()
    await panel.getByText('服务器完整清单：4项',{exact:true}).waitFor()
  }
  const begin=async()=>{
    const response=page.waitForResponse(r=>r.url().endsWith('/route-calibration-batches')&&r.request().method()==='POST')
    await panel.getByRole('button',{name:'明确开始此批校准',exact:true}).click()
    const r=await response;if(r.status()!==202)throw Error(await r.text());return r.json()
  }
  const continueUI=async row=>{
    const manual=panel.getByTestId('batch-manual');await manual.waitFor()
    await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill(row.items[row.current_index].request.reference_antenna)
    await manual.getByRole('checkbox',{name:'确认仅对应当前项和当前人工步骤',exact:true}).check()
    await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click()
  }
  const locked=async()=>{
    for(const name of ['添加器件','保存拓扑'])if(!await page.getByRole('button',{name,exact:true}).isDisabled())throw Error(`${name}错误解锁`)
  }
  // 真实原画布拖动与保存，再刷新取服务端图；不以种子写入代替保存验收。
  await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent==='添加器件')?.disabled)
  await page.locator('.react-flow__node').first().scrollIntoViewIfNeeded()
  const node=await page.locator('.react-flow__node').first().boundingBox()
  if(!node)throw Error('缺少可编辑原图节点')
  await page.mouse.move(node.x+25,node.y+25);await page.mouse.down()
  await page.mouse.move(node.x+65,node.y+45,{steps:8});await page.mouse.up()
  await page.getByTestId('topology-save-stage').filter({hasText:'拓扑草稿未保存'}).waitFor()
  const save=page.waitForResponse(r=>r.url().includes('/switch-topologies/')&&r.request().method()==='PATCH')
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click()
  const saved=await save;if(!saved.ok())throw Error(await saved.text())
  const graph=await saved.json()
  if(graph.nodes.filter(n=>n.params.connection_scope==='calibration').length!==8||graph.connections.length!==10)throw Error('正常/校准段保存不完整')
  await page.reload();await open()
  await prepare()
  await page.screenshot({path:`${output}/four-item-preview.png`,fullPage:true})
  const first=await begin(), id=first.job_id
  let row=await waitState(id,r=>r.status==='waiting_manual')
  if(row.items.length!==4||row.current_index!==0)throw Error('清单或首项身份错误')
  await locked()
  await page.screenshot({path:`${output}/first-manual.png`,fullPage:true})
  await continueUI(row)
  row=await waitState(id,r=>r.status==='waiting_manual'&&r.current_index===2)
  if(row.items.slice(0,2).some(i=>i.status!=='simulated'))throw Error('Mock前两项未真实持久化为simulated')
  await panel.getByText('模拟人工步骤；未确认实物停发或换线安全',{exact:true}).waitFor()
  await page.screenshot({path:`${output}/cross-route-paused.png`,fullPage:true})
  await panel.getByRole('button',{name:'查看本项读数及原采用入口',exact:true}).first().click()
  await page.getByText('外层释放／最终化未确认，当前不可采用。',{exact:false}).first().waitFor().catch(()=>{})
  await page.screenshot({path:`${output}/parent-child-pending.png`,fullPage:true})
  // 只让真实GET失败；不返回任何伪造body，不拦截POST。
  const fail=route=>route.request().method()==='GET'?route.abort('failed'):route.continue()
  await page.route('**/route-calibration-batches**',fail)
  await page.getByRole('tab',{name:'总览',exact:true}).click()
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click()
  await panel.getByRole('button',{name:'读取批历史／恢复活动批',exact:true}).click()
  await panel.getByText('批历史读取失败：',{exact:false}).waitFor()
  await locked()
  await page.screenshot({path:`${output}/failed-read-keeps-lock.png`,fullPage:true})
  await page.unroute('**/route-calibration-batches**',fail)
  await panel.getByRole('button',{name:'读取批历史／恢复活动批',exact:true}).click()
  await panel.getByTestId('batch-manual').waitFor()
  await continueUI(row)
  row=await waitState(id,r=>r.status==='completed'&&r.finalization_committed)
  if(row.f64_control_released!==null||row.items.some(i=>i.status!=='simulated'))throw Error('模拟不能补造真实释放证明')
  await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent==='添加器件')?.disabled)
  await page.screenshot({path:`${output}/completed-mock.png`,fullPage:true})
  for(const item of row.items){
    const r=await page.request.get(`${base}/api/v1/lab-profiles/${lab.id}/fixed-route-acquisitions/${item.run_id}`)
    const child=await r.json()
    if(child.status!=='simulated'||child.result.net_loss_db!==null||child.result.formal_eligible!==false)throw Error('模拟数值进入资格')
    const candidate=await(await page.request.get(`${base}/api/v1/lab-profiles/${lab.id}/fixed-route-acquisitions/${item.run_id}/application-preview`)).json()
    if(candidate.eligibility.eligible_for_adoption)throw Error('模拟采用错误放行')
  }
  await page.reload();await open();await prepare()
  const second=await begin();const beforeCancel=await waitState(second.job_id,r=>r.status==='waiting_manual')
  await continueUI(beforeCancel)
  await waitState(second.job_id,r=>r.status==='waiting_manual'&&r.current_index===2)
  await panel.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).click()
  const cancelled=await waitState(second.job_id,r=>r.status==='cancelled')
  await page.reload();await open()
  const after=await get(second.job_id)
  if(after.status!=='cancelled'||after.items.filter(i=>i.run_id).length!==2)throw Error('取消刷新自动续跑')
  await page.screenshot({path:`${output}/cancelled-refresh.png`,fullPage:true})
  return {hal:status,completed:row,cancelled,checks:['四项真实预览','首次与跨路人工','两项模拟后父子待释放','离页失败GET保持锁','继续真实完成','Mock采用拒绝','取消后刷新不续跑']}
}

// 独立测试进程已脚本化全部transport且禁止外连；不称全Mock或实物资格。
export async function transportBatch(page,{base='http://127.0.0.1:5189',output='output/pc06a1-task6',wrong=false}={}) {
  page.setDefaultTimeout(8000)
  await page.goto(base)
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click()
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click()
  const panel=page.getByTestId('route-batch-panel');await panel.waitFor()
  const hal=await(await page.request.get(`${base}/api/v1/instruments/hal/status`)).json()
  if(hal.mode!=='real'||hal.driver_count!==3)throw Error('未进入明确隔离的真实HAL软件链')
  await panel.locator('.mantine-MultiSelect-root').click()
  for(const c of ['oh','ov'])await page.getByRole('option').filter({hasText:` · ${c}`}).click()
  await page.keyboard.press('Escape')
  await panel.getByLabel('批量频点（MHz，逗号分隔）',{exact:true}).fill('2595')
  await panel.getByLabel('批量请求功率（dBm，不作实测值）',{exact:true}).fill('-30')
  await panel.getByLabel('每项采样数（2–10）',{exact:true}).fill('2')
  for(const c of ['oh','ov']){
    await panel.getByLabel(`参考天线／位置 ${c} @2595`,{exact:true}).fill('REF 中心')
    await panel.getByLabel(`接收线损（dB） ${c} @2595`,{exact:true}).fill('2')
    await panel.getByLabel(`接收线依据 ${c} @2595`,{exact:true}).fill('隔离软件链记录2595MHz')
  }
  for(const name of ['已核对清单的固定接线条件','已确认请求功率及现场安全条件'])await panel.getByRole('checkbox',{name,exact:true}).check()
  await panel.getByRole('button',{name:'预览完整批清单',exact:true}).click()
  await panel.getByText('服务器完整清单：2项',{exact:true}).waitFor()
  await panel.getByLabel('接线声明操作员（自述，非认证身份）',{exact:true}).fill('隔离软件验收操作员')
  await panel.getByLabel('接线核对说明',{exact:true}).fill('仅脚本transport生产链验证，不是实物接线或认证证据')
  await panel.getByRole('button',{name:'确认本范围接线声明并重新预览',exact:true}).click()
  const start=page.waitForResponse(r=>r.url().endsWith('/route-calibration-batches')&&r.request().method()==='POST')
  await panel.getByRole('button',{name:'明确开始此批校准',exact:true}).click()
  const response=await start;if(response.status()!==202)throw Error(await response.text())
  const initial=await response.json()
  const root=`${base}/api/v1/lab-profiles/${initial.lab_id}/route-calibration-batches/${initial.job_id}`
  const manual=panel.getByTestId('batch-manual');await manual.waitFor()
  await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill('REF 中心')
  await manual.getByRole('checkbox',{name:'确认仅对应当前项和当前人工步骤',exact:true}).check()
  await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click()
  let final
  for(let n=0;n<160;n++){
    final=await(await page.request.get(root)).json()
    if(wrong?final.status==='paused_failure':final.status==='completed'&&final.finalization_committed)break
    await page.waitForTimeout(100)
  }
  if(wrong){
    if(final.status!=='paused_failure'||final.items.some(i=>i.run_id))throw Error('错误回读未在采集前拒绝')
    const receipts=final.items[0].switch_receipts
    if(!receipts.some(r=>r.raw==='ERROR 201 NC'&&r.error))throw Error('未保存真实错误receipt')
  }else if(final.status!=='completed'||!final.finalization_committed||final.f64_control_released!==true||final.items.some(i=>i.status!=='completed')){
    throw Error(`隔离真实HAL软件链未完成：${JSON.stringify(final)}`)
  }
  await panel.getByText(wrong?'失败暂停：确认后只跳过失败项，不重测':'共2项 · 实测完成2 · 模拟0 · 失败0；单项完成不等于整套成功。',{exact:true}).first().waitFor()
  await panel.getByTestId(wrong?'batch-active-detail':'batch-history-detail').scrollIntoViewIfNeeded()
  await page.screenshot({path:`${output}/transport-${wrong?'wrong-receipt':'auto-completed'}.png`})
  if(wrong){await panel.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).click()}
  return {isolated_transport_only:true,physical_evidence:false,hal,initial,final}
}
