// playwright-cli run-code --filename；真实HTTP，不替换API响应。
async page=>{
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,stage=new URL(page.url()).searchParams.get('internalStage'),run=new URL(page.url()).searchParams.get('internalRun')||'initial';
  page.setDefaultTimeout(12000);
  await page.setViewportSize({width:1800,height:1100});
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅全Mock');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04A4c内部通路甲');
  const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
  await page.goto(origin);
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await page.getByRole('textbox',{name:'器件列表',exact:true}).fill('pa');
  await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').filter({hasText:/^pa ·/}).click();
  const drawer=page.getByRole('dialog',{name:'器件属性',exact:true});
  await drawer.waitFor();await page.getByRole('textbox',{name:'器件名称',exact:true}).waitFor();
  await page.getByRole('textbox',{name:'端口角色 IN',exact:true}).waitFor();
  const dom=await drawer.innerText(),implemented=await page.getByRole('button',{name:'添加内部通路',exact:true}).count();
  await page.screenshot({path:`output/playwright/pc04a4c-${implemented?`green-${run}-${stage||'controls'}`:'red'}-drawer.png`,fullPage:true,animations:'disabled'});
  console.log(JSON.stringify({stage:'原4a/4b抽屉已加载',lab,graph,dom}));
  await page.getByText('内部通路',{exact:true}).waitFor();
  await page.getByRole('button',{name:'添加内部通路',exact:true}).waitFor();
  if(!stage)return {stage:'GREEN',lab,dom};
  const checks=[],exchanges=[],endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const eq=(a,b,message)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(`${message}: ${JSON.stringify(a)}`)};
  const close=async()=>{await drawer.getByRole('banner').getByRole('button').click();await drawer.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const choose=async id=>{await page.getByRole('textbox',{name:'器件列表',exact:true}).fill(id);await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').filter({hasText:new RegExp(`^${id} ·`)}).click();await drawer.waitFor()};
  const apply=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await drawer.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const pair=async(from,to,index=1)=>{for(const [label,value] of [[`内部输入口 ${index}`,from],[`内部输出口 ${index}`,to]]){await page.getByRole('textbox',{name:label,exact:true}).click();await page.getByRole('option').filter({hasText:new RegExp(`^${value} ·`)}).click()}};
  const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));
    await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;exchanges.push({request:r.request().postDataJSON(),status:r.status(),response:await r.json()});eq(r.status(),200,'保存失败');
    await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();return read(endpoint)};
  const shot=async name=>{await page.screenshot({path:`output/playwright/pc04a4c-${run}-${name}.png`,fullPage:true,animations:'disabled'});checks.push({name,dom:await page.locator('body').innerText()})};
  const other=(await read('/lab-profiles')).find(l=>l.name==='PC04A4c内部通路乙');
  const mode=async name=>{await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name,exact:true}).click()};
  await close();
  if(stage==='lifecycle'){
    const before=await read(endpoint),legacy=before.nodes.find(n=>n.id==='legacy-pa');
    if(Object.hasOwn(legacy.params,'internal_paths'))throw Error('首次生命周期须缺键旧PA');
    await choose('legacy-pa');await page.getByRole('button',{name:'添加内部通路',exact:true}).click();await pair('IN','OUT');await close();
    await choose('legacy-pa');await page.getByText('旧版未声明（缺键），不自动补齐',{exact:true}).waitFor();
    await page.getByRole('button',{name:'添加内部通路',exact:true}).click();await pair('IN','OUT');await page.getByRole('button',{name:'恢复原内部声明',exact:true}).click();
    await apply();const restored=await save();eq(restored.nodes.find(n=>n.id==='legacy-pa').params,legacy.params,'取消/恢复补了声明');checks.push('未改/取消/恢复保留缺键、0与opaque');
    await choose('legacy-pa');await page.getByRole('button',{name:'添加内部通路',exact:true}).click();await pair('IN','OUT');await apply();
    await choose('legacy-pa');await page.getByRole('button',{name:'声明无内部贯通',exact:true}).click();await close();
    await choose('legacy-pa');eq(await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).inputValue(),'IN · 方向未声明，非双向能力','第二次取消覆盖已应用草稿');await close();
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();eq(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')),lab.id,'dirty跨Lab未保护');
    await page.context().setOffline(true);try{await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByTestId('topology-save-stage').filter({hasText:'拓扑保存失败；草稿未保存'}).waitFor()}finally{await page.context().setOffline(false)}
    eq(await read(endpoint),restored,'离线写入服务器');
    await choose('legacy-pa');await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).waitFor();await shot('offline-draft-preserved');await close();
    await page.evaluate(()=>{window.__pc04Saving=[];window.__pc04Observer=new MutationObserver(()=>{const save=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='保存拓扑');if(save?.disabled)window.__pc04Saving.push({save:true,inputs:['器件列表','新增器件类型','操作模式'].every(k=>document.querySelector(`input[aria-label="${k}"]`)?.disabled),draggable:document.querySelectorAll('.react-flow__node.draggable').length,connectable:document.querySelectorAll('.react-flow__handle.connectablestart,.react-flow__handle.connectableend').length})});window.__pc04Observer.observe(document.body,{subtree:true,childList:true,attributes:true})});
    const saved=await save(),samples=await page.evaluate(()=>{window.__pc04Observer.disconnect();return window.__pc04Saving});
    if(!samples.some(v=>v.inputs&&!v.draggable&&!v.connectable))throw Error('未捕获真实pending锁');
    eq(saved.nodes.find(n=>n.id==='legacy-pa').params.internal_paths,[{from_port:'IN',to_port:'OUT'}],'在线重试丢草稿');
    eq(saved.connections,before.connections,'内部pair创建了外边');checks.push({pendingSamples:samples});
    await choose('pa');await page.getByRole('button',{name:'声明无内部贯通',exact:true}).click();await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
    await page.getByText(/探头 probe 连线 n1\/n2.*pa.*IN.*OUT/).waitFor();await shot('clear-selected-rejected');await close();
    await mode('校准接线');await choose('pa');await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('OUT');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
    await page.getByText(/所有模式关联连线 n1、n2；显式路径探头 probe/).waitFor();await shot('hidden-port-reference-rejected');await close();
    eq(await read(endpoint),saved,'UI拒绝改了服务器');
    const invalid=structuredClone(saved.nodes);invalid.find(n=>n.id==='pa').params.internal_paths=[{from_port:'OUT',to_port:'IN'}];
    const rejected=await page.request.patch(`${api}${endpoint}`,{data:{nodes:invalid}}),body=await rejected.json();eq(rejected.status(),422,'错误pair未422');
    exchanges.push({request:{nodes:invalid},status:422,response:body});eq(await read(endpoint),saved,'422非原子');
    await mode('MIMO OTA 测试');
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();
    await page.getByText('PC04A4c图乙',{exact:true}).waitFor();await choose('legacy-pa');await page.getByText('旧版未声明（缺键），不自动补齐',{exact:true}).waitFor();await close();
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:lab.name}).click();
    await page.getByText('PC04A4c图甲',{exact:true}).waitFor();await choose('legacy-pa');await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).waitFor();await shot('lab-roundtrip');await close();
    await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
    await choose('legacy-pa');await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).waitFor();await shot('reload-restored');await close();
    checks.push('真实取消/应用再取消、离线重试、422原子、全模式引用、模式切换、A→B→A和重载GET一致');
  }else if(stage==='collection'){
    const panel=page.getByTestId('route-calibration-panel'),historyUrl=`/lab-profiles/${lab.id}/fixed-route-acquisitions`,oldHistory=await read(historyUrl);
    const field=panel.getByRole('textbox',{name:'完整校准通路',exact:true});await field.click();await page.getByRole('option').filter({hasText:'n4'}).first().click();await panel.getByTestId('selected-calibration-path').waitFor();
    for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','Task3内部通路软件验证参考件'],['接收线缆损耗','2'],['接收线缆记录来源','隔离非实测声明']])await panel.getByLabel(label,{exact:false}).fill(value);
    const lock=async label=>{const value=await page.evaluate(()=>({inputs:['器件列表','新增器件类型','操作模式'].every(k=>document.querySelector(`input[aria-label="${k}"]`)?.disabled),buttons:['添加器件','保存拓扑'].every(k=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===k)?.disabled),draggable:document.querySelectorAll('.react-flow__node.draggable').length,connectable:document.querySelectorAll('.react-flow__handle.connectablestart,.react-flow__handle.connectableend').length,dialogs:document.querySelectorAll('[role="dialog"]').length}));
      if(!value.inputs||!value.buttons||value.draggable||value.connectable||value.dialogs)throw Error(`${label}未冻结：${JSON.stringify(value)}`);checks.push({label,value})};
    const start=async()=>{await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();
      const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/fixed-route-acquisitions'));await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();const r=await response,body=await r.json();eq(r.status(),202,'启动失败');eq(body.status,'running','非真实running');exchanges.push({request:r.request().postDataJSON(),status:r.status(),response:body});return body};
    const first=await start();await lock('真实running');await page.context().setOffline(true);
    try{await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();await panel.getByText('采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。',{exact:true}).waitFor();await lock('离线取消未知');await shot('unknown-cancel-locked')}finally{await page.context().setOffline(false)}
    await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
    const firstRecord=await read(`${historyUrl}/${first.run_id}`);checks.push({firstRecord});
    // 只有原服务器安全终态能够释放。若Mock取消没有确认，准确返回边界，不伪造清理。
    try{await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled,{timeout:10000})}
    catch{await lock('恢复后仍未确认终态');await shot('unconfirmed-lock-retained');return {stage,checks,exchanges,boundary:'服务器未给安全终态，未解锁/未启动第二次',history:await read(historyUrl)}}
    await choose('pa');await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).isEnabled().then(v=>eq(v,true,'终态未恢复编辑'));await close();
    // 安全终态后真正再编辑、保存、重读服务器路线，而非复用第一次摘要。
    await choose('combiner');await page.getByRole('button',{name:'添加内部通路',exact:true}).click();await pair('IN2','OUT',2);await apply();
    const edited=await save();eq(edited.nodes.find(n=>n.id==='combiner').params.internal_paths,[{from_port:'IN1',to_port:'OUT'},{from_port:'IN2',to_port:'OUT'}],'第二轮前编辑未保存');
    await panel.getByTestId('selected-calibration-path').waitFor();
    const second=await start();await lock('第二次running');
    if(exchanges.filter(x=>x.status===202)[0].request.route_digest===exchanges.filter(x=>x.status===202)[1].request.route_digest)throw Error('第二次重用了旧路线摘要');
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled,{timeout:15000});
    const secondRecord=await read(`${historyUrl}/${second.run_id}`);eq((await read(historyUrl)).length,oldHistory.length+2,'重放或双启动');
    for(const record of [await read(`${historyUrl}/${first.run_id}`),secondRecord]){eq(record.formal_eligible,false,'Mock授资格');eq(record.result.net_loss_db,null,'Mock造损耗');eq(record.result.samples,[],'Mock造样本')}
    checks.push({secondRecord});await choose('pa');await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).waitFor();await shot('second-terminal-editable');await close();
  }
  return {stage,checks,exchanges,after:await read(endpoint)};
}
