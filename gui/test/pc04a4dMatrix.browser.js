// Task4新增交叉矩阵；真实HTTP/CDP延迟/鼠标，不替换响应。
async page => {
  const recovery = await page.context().newCDPSession(page);
  await recovery.send('Network.enable');
  await recovery.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await recovery.detach();
  const origin = new URL(page.url()).origin, matrixStage=new URL(page.url()).searchParams.get('matrixStage'), exchanges = [], checks = [];
  const request = async (method, path, data) => {
    const response = await page.request[method](`${origin}/api/v1${path}`, data ? {data} : {});
    const body = await response.json();
    exchanges.push({method, path, request: data, status: response.status(), response: body});
    if (!response.ok()) throw Error(JSON.stringify(body));
    return body;
  };
  const assert = (condition, message) => {if (!condition) throw Error(message)};
  const labs = await request('get', '/lab-profiles');
  const lab = labs.find(row => row.name === 'PC04A4d转换甲');
  const graphs = (await request('get', `/switch-topologies?lab_profile_id=${lab.id}`)).items;
  const first = graphs.find(row => row.name === 'PC04A4d图甲');
  const second = graphs.find(row => row.name === 'PC04A4d第二开关图甲');
  assert(first && second && first.switch_category_id !== second.switch_category_id, '需要真实第二开关');
  const endpoint = graph => `/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const before = await request('get', endpoint(first));
  if(matrixStage==='api') {
    const source=graphs.find(row=>row.name.includes('CAICT'));
    assert(source,'CAICT原import源图缺失');
    const sourceBefore=await request('get',endpoint(source));
    const edit={connections:[{connection_id:source.connections[0].id,cable_loss_db:null}]};
    const preview=await request('post',`/switch-topologies/${source.id}/conversion-preview?lab_profile_id=${lab.id}`,edit);
    assert(JSON.stringify(sourceBefore)===JSON.stringify(await request('get',endpoint(source))),'CAICT预览写入');
    const saved=await request('patch',endpoint(source),{conversion:{source_digest:preview.source_digest,changes:preview.changes}});
    assert(saved.id===source.id && saved.connections.length===source.connections.length,'CAICT静默全模板转换');
    checks.push({id:'D01',sourceId:source.id,before:sourceBefore,preview,after:saved});
    for(const [id,target,extra] of [['ce','channel_emulator',{ce_port:'B1.1'}],['bse','communication_tester',{}],['sa','signal_analyzer',{}]]){
      const current=await request('get',endpoint(first));
      const p=await request('post',`/switch-topologies/${first.id}/conversion-preview?lab_profile_id=${lab.id}`,{nodes:[{node_id:id,target_type:target,...extra}]});
      const result=await request('patch',endpoint(first),{conversion:{source_digest:p.source_digest,changes:p.changes}});
      assert(result.nodes.find(n=>n.id===id).type===target,'等价类型未转换');
      if(id==='bse')assert(JSON.stringify(result.nodes.find(n=>n.id===id).params.port_roles)===JSON.stringify(current.nodes.find(n=>n.id===id).params.port_roles),'BSE角色被覆盖');
      checks.push({id:'D02',nodeId:id,before:current,preview:p,after:result});
    }
    for(const loss of [null,0,2.5]){
      const p=await request('post',`/switch-topologies/${first.id}/conversion-preview?lab_profile_id=${lab.id}`,{connections:[{connection_id:'wire-in',cable_loss_db:loss}]});
      await request('patch',endpoint(first),{conversion:{source_digest:p.source_digest,changes:p.changes}});
      const matrix=await request('get',`/switch-topologies/${first.id}/calibration-matrix/mimo_ota?lab_profile_id=${lab.id}`);
      checks.push({id:'D03',loss,matrix});
    }
    // 恢复本图标称，后续GUI lifecycle使用同一明确输入。
    const p=await request('post',`/switch-topologies/${first.id}/conversion-preview?lab_profile_id=${lab.id}`,{connections:[{connection_id:'wire-in',cable_loss_db:2}]});
    await request('patch',endpoint(first),{conversion:{source_digest:p.source_digest,changes:p.changes}});
    await page.screenshot({path:'output/playwright/pc04a4d-task4-api-matrix.png',fullPage:true});
    return {stage:'GREEN',checks,exchanges,boundary:'浏览器真实HTTP；其它子条件见本片TestClient运行证据，不冒称全由DOM点击完成'};
  }
  await page.goto(origin,{waitUntil:'domcontentloaded',timeout:60000});
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), lab.id);
  await page.reload(); await page.setViewportSize({width:1800,height:1100});
  await page.getByRole('tab', {name:'实验室配置',exact:true}).click();
  await page.getByRole('tab', {name:'射频拓扑',exact:true}).click();
  await page.getByRole('textbox',{name:'射频开关设备',exact:true}).click();
  await page.getByRole('option').filter({hasText:'射频开关',hasNotText:'第二'}).click();
  await page.getByText(first.name,{exact:true}).waitFor();
  if(matrixStage==='batch') {
    const panel=page.getByTestId('route-batch-panel');await panel.waitFor();
    await panel.locator('.mantine-MultiSelect-root').click();
    await page.getByRole('option').filter({hasText:'wire-out'}).click();await page.keyboard.press('Escape');
    for(const [label,value] of [['批量频点（MHz，逗号分隔）','2595'],['批量请求功率（dBm，不作实测值）','-30'],['每项采样数（2–10）','2'],
      ['参考天线／位置 wire-out @2595','Task4隔离参考'],['接收线损（dB） wire-out @2595','2'],['接收线依据 wire-out @2595','Task4非实测声明']])
      await panel.getByLabel(label,{exact:true}).fill(value);
    await panel.getByRole('checkbox',{name:'已核对清单的固定接线条件',exact:true}).check();
    await panel.getByRole('checkbox',{name:'已确认请求功率及现场安全条件',exact:true}).check();
    const p=page.waitForResponse(r=>r.url().includes('/route-calibration-batches/preview'));
    await panel.getByRole('button',{name:'预览完整批清单',exact:true}).click();const preview=await p;
    exchanges.push({request:preview.request().postDataJSON(),status:preview.status(),response:await preview.json()});
    assert(preview.status()===200,'批预览失败');
    const start=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/route-calibration-batches'));
    await panel.getByRole('button',{name:'明确开始此批校准',exact:true}).click();const response=await start;
    const run=await response.json();exchanges.push({request:response.request().postDataJSON(),status:response.status(),response:run});assert(response.status()===202,'批启动失败');
    assert(await page.getByRole('button',{name:'转换旧配置',exact:true}).isDisabled(),'批运行转换未锁');
    checks.push({id:'D08-D09-batch-running',run,dom:await page.locator('body').innerText()});
    await page.screenshot({path:'output/playwright/pc04a4d-task4-batch-running.png',fullPage:true});
    const manual=panel.getByTestId('batch-manual');await manual.waitFor();
    await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill('Task4隔离参考');
    await manual.getByRole('checkbox',{name:'确认仅对应当前项和当前人工步骤',exact:true}).check();
    await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click();
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='转换旧配置')?.disabled);
    const completed=await request('get',`/lab-profiles/${lab.id}/route-calibration-batches/${run.job_id}`);
    assert(completed.status==='completed'&&completed.items.every(item=>item.status==='simulated'),'完整Mock批未完成');
    checks.push({id:'D09-batch-completed',completed,dom:await page.locator('body').innerText()});
    await panel.getByRole('button',{name:'预览完整批清单',exact:true}).click();
    const startAgain=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/route-calibration-batches'));
    await panel.getByRole('button',{name:'明确开始此批校准',exact:true}).click();const secondResponse=await startAgain;
    const secondRun=await secondResponse.json();assert(secondResponse.status()===202,'第二批未启动');
    await page.context().setOffline(true);
    try{await panel.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).click();
      assert(await page.getByRole('button',{name:'转换旧配置',exact:true}).isDisabled(),'批取消未确认提前解锁');
      checks.push({id:'D08-batch-cancel-unconfirmed',dom:await page.locator('body').innerText()});
    }finally{await page.context().setOffline(false)}
    await panel.getByRole('button',{name:'读取批历史／恢复活动批',exact:true}).click();
    const cancel=await page.request.post(`${origin}/api/v1/lab-profiles/${lab.id}/route-calibration-batches/${secondRun.job_id}/cancel`);
    exchanges.push({status:cancel.status(),response:await cancel.json()});
    await panel.getByRole('button',{name:'读取批历史／恢复活动批',exact:true}).click();
    assert(await page.getByRole('button',{name:'转换旧配置',exact:true}).isDisabled(),'取消未知不应解除全局锁');
    return {stage:'GREEN',checks,exchanges,boundary:'全Mock不证明真实停发；完整completed仅结束软件锁，cancelled释放未知仍锁定'};
  }
  const modal = page.getByRole('dialog',{name:'转换旧配置',exact:true});
  await page.getByRole('button',{name:'转换旧配置',exact:true}).click();
  await modal.getByRole('textbox',{name:'转换器件',exact:true}).click();
  await page.getByRole('option').filter({hasText:/^sa ·/}).click();
  await modal.getByRole('textbox',{name:'显式端口方向 port_directions（JSON对象）',exact:true}).fill('{"IN":"unknown"}');
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:900,downloadThroughput:-1,uploadThroughput:-1});
  const late = page.waitForResponse(r => r.url().includes('/conversion-preview'));
  await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();
  // 遮罩下触发真实Select的生产onChange；随后另做真实鼠标选择第二开关。
  await page.getByRole('textbox',{name:'射频开关设备',exact:true}).evaluate((input, id) => {
    let fiber = input[Object.keys(input).find(key => key.startsWith('__reactFiber'))];
    while (fiber && !(fiber.memoizedProps?.label === '射频开关设备' &&
      Array.isArray(fiber.memoizedProps?.data) && fiber.memoizedProps.data.some(row=>row.value===id) &&
      fiber.memoizedProps?.onChange)) fiber = fiber.return;
    if (!fiber) throw Error('找不到原Select事件');
    fiber.memoizedProps.onChange(id);
  }, second.switch_category_id);
  await modal.waitFor({state:'hidden'}); const response = await late;
  exchanges.push({method:'POST',url:response.url(),request:response.request().postDataJSON(),status:response.status(),response:await response.json()});
  await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1}); await cdp.detach();
  await page.getByText(second.name,{exact:true}).waitFor();
  await page.getByRole('button',{name:'转换旧配置',exact:true}).click();
  assert(await modal.getByTestId('conversion-preview').count() === 0,'第二图迟到响应复活');
  assert(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),'第二图可确认旧预览');
  checks.push({id:'D07-selectedSwitch-pending',first:first.id,second:second.id,dom:await page.locator('body').innerText()});
  await page.screenshot({path:'output/playwright/pc04a4d-task4-second-pending.png',fullPage:true});
  await modal.getByRole('button',{name:'取消转换',exact:true}).click();
  await page.locator('.mantine-Modal-overlay').waitFor({state:'hidden'});
  const select = page.getByRole('textbox',{name:'射频开关设备',exact:true});
  await select.click(); await page.getByRole('option').filter({hasText:'射频开关',hasNotText:'第二'}).click();
  await page.getByText(first.name,{exact:true}).waitFor();
  await select.click(); await page.getByRole('option',{name:'PC04A4d第二射频开关',exact:true}).click();
  await page.getByText(second.name,{exact:true}).waitFor();
  checks.push({id:'D07-selectedSwitch-real-selection',dom:await page.locator('body').innerText()});
  // D12原画布真实鼠标移动，显式应用并保存，随后HTTP重载确认坐标和名称。
  await page.getByRole('button',{name:'Fit View',exact:true}).click();
  await page.waitForFunction(()=>{
    const transform=document.querySelector('.react-flow__viewport')?.getAttribute('style');
    window.__task4Viewport=window.__task4Viewport||{transform:null,count:0};
    const previous=window.__task4Viewport;
    previous.count=previous.transform===transform?previous.count+1:0;previous.transform=transform;
    return previous.count>25;
  },{},{polling:'raf'});
  const node = page.locator('.react-flow__node[data-id="cable"]');
  const box = await node.boundingBox(); assert(box,'节点不可见');
  const beforeStyle=await node.getAttribute('style');
  await page.mouse.move(box.x+box.width/2,box.y+15);
  await page.mouse.down(); await page.mouse.move(box.x+box.width/2+70,box.y+60,{steps:20}); await page.mouse.up();
  await page.waitForFunction(before=>document.querySelector('.react-flow__node[data-id="cable"]')?.getAttribute('style')!==before,beforeStyle);
  await node.dblclick();
  await page.getByLabel('器件名称',{exact:true}).fill('Task4鼠标应用线缆');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  const savedResponse = page.waitForResponse(r => r.request().method()==='PATCH' && r.url().includes(second.id));
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
  const saved = await savedResponse; assert(saved.status()===200,'鼠标保存失败');
  exchanges.push({method:'PATCH',url:saved.url(),request:saved.request().postDataJSON(),status:saved.status(),response:await saved.json()});
  const after = await request('get',endpoint(second));
  const oldNode = second.nodes.find(row=>row.id==='cable'), newNode=after.nodes.find(row=>row.id==='cable');
  assert(newNode.label==='Task4鼠标应用线缆','名称未保存');
  assert(JSON.stringify(oldNode.position)!==JSON.stringify(newNode.position),'真实鼠标坐标未保存');
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await page.getByRole('textbox',{name:'射频开关设备',exact:true}).click();
  await page.getByRole('option',{name:'PC04A4d第二射频开关',exact:true}).click();
  await page.getByText('Task4鼠标应用线缆',{exact:true}).waitFor();
  checks.push({id:'D12-real-mouse-apply-save-reload',oldNode,newNode,dom:await page.locator('body').innerText()});
  await page.screenshot({path:'output/playwright/pc04a4d-task4-real-mouse.png',fullPage:true});
  await page.locator('.react-flow__edge[data-id="wire-in"] .react-flow__edge-interaction').click({force:true});
  await page.getByRole('button',{name:'删除连线',exact:true}).click();
  assert(await page.locator('.react-flow__edge[data-id="wire-in"]').count()===1,'删除仍被完整路径引用的连线成功');
  checks.push({id:'D12-delete-reference-rejected',dom:await page.locator('body').innerText()});
  assert(JSON.stringify(before)===JSON.stringify(await request('get',endpoint(first))),'第一图被跨对象写入');
  return {stage:'GREEN',labId:lab.id,firstId:first.id,secondId:second.id,checks,exchanges};
}
