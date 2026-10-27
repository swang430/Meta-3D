// playwright-cli run-code --filename；真实HTTP，无route mock。
async page => {
  const stage = new URL(page.url()).searchParams.get('conversionStage');
  const origin = new URL(page.url()).origin;
  const read = async path => {const r=await page.request.get(`${origin}/api/v1${path}`);if(!r.ok())throw Error(await r.text());return r.json()};
  const lab=(await read('/lab-profiles')).find(l=>l.name===`PC04A4d转换${stage==='reimport'?'乙':'甲'}`);
  const graphs=await read(`/switch-topologies?lab_profile_id=${lab.id}`);
  const graph=graphs.items.find(g=>g.name===`PC04A4d图${stage==='reimport'?'乙':'甲'}`);
  if((await read('/instruments/hal/status')).mode!=='mock')throw Error('必须全Mock');
  await page.goto(origin);
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();
  await page.setViewportSize({width:1800,height:1100});
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await page.getByText(graph.name,{exact:true}).waitFor();
  const count=await page.getByRole('button',{name:'转换旧配置',exact:true}).count();
  const dom=await page.locator('body').innerText();
  await page.screenshot({path:`output/playwright/pc04a4d-${count?'green':'red'}.png`,fullPage:true});
  console.log(JSON.stringify({stage:count?'GREEN':'RED',labId:lab.id,displayTopologyId:graph.id,graphs,dom}));
  if(!count)return {stage:'RED',labId:lab.id,displayTopologyId:graph.id,graphs,dom,reason:'原拓扑编辑器没有转换旧配置入口'};
  const checks=[],exchanges=[];
  const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const eq=(a,b,label)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(`${label}: ${JSON.stringify(a)}`)};
  const modal=page.getByRole('dialog',{name:'转换旧配置',exact:true});
  const choose=async(label,id)=>{await modal.getByRole('textbox',{name:label,exact:true}).click();await page.getByRole('option').filter({hasText:new RegExp(`^${id} ·`)}).click()};
  const field=(label)=>modal.getByRole('textbox',{name:label,exact:true});
  const open=async()=>{await page.getByRole('button',{name:'转换旧配置',exact:true}).click();await modal.waitFor()};
  const close=async()=>{await modal.getByRole('button',{name:'取消转换',exact:true}).click();await modal.waitFor({state:'hidden'});await page.locator('.mantine-Modal-overlay').waitFor({state:'hidden'})};
  const shot=async label=>{checks.push({label,dom:await page.locator('body').innerText()});await page.screenshot({path:`output/playwright/pc04a4d-${label}.png`,fullPage:true})};
  const preview=async()=>{const wait=page.waitForResponse(r=>r.url().includes('/conversion-preview')&&r.request().method()==='POST');await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();const r=await wait;exchanges.push({request:r.request().postDataJSON(),url:r.url(),status:r.status(),response:await r.json()});eq(r.status(),200,'预览失败');await modal.getByTestId('conversion-preview').waitFor()};
  const save=async(status=200)=>{const wait=page.waitForResponse(r=>r.url().includes(`/switch-topologies/${graph.id}`)&&r.request().method()==='PATCH');await modal.getByRole('button',{name:'确认转换并保存',exact:true}).click();const r=await wait;exchanges.push({request:r.request().postDataJSON(),url:r.url(),status:r.status(),response:await r.json()});eq(r.status(),status,'转换保存状态');if(status===200){await modal.waitFor({state:'hidden'});await page.locator('.mantine-Modal-overlay').waitFor({state:'hidden'})}return read(endpoint)};
  if(stage==='display'){
    const before=await read(endpoint);await open();await choose('转换器件','ce');await choose('转换连线','wire-in');
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    const dom=await modal.innerText(),failures=[];
    if(!dom.includes('GET展示值，原保存声明待核'))failures.push('GET节点/边没有声明证据边界');
    if(dom.includes('原保存声明：')||dom.includes('原保存端点/旧损耗/来源：'))failures.push('仍把GET模型标成原保存事实');
    const option=await field('转换连线').inputValue();
    if(!option.includes('GET展示值，原保存声明待核'))failures.push('端点选择标签未标证据边界');
    if(!(await field('转换器件').inputValue()).includes('GET展示值，原保存声明待核'))failures.push('器件选择标签未标证据边界');
    await field('同一物理线缆量值owner原边').click();const ownerOption=await page.getByRole('option').filter({hasText:/^wire-out ·/}).innerText();await field('同一物理线缆量值owner原边').press('Escape');
    if(!ownerOption.includes('GET展示值，原保存声明待核'))failures.push('owner数值选项未标证据边界');
    if(await field('显式源端口 source_pin').inputValue()!==''||await field('显式标称损耗 cable_loss_db').inputValue()!=='')failures.push('GET默认值被自动放入显式编辑');
    await shot(`display-${failures.length?'red':'green'}`);await close();eq(await read(endpoint),before,'只读展示/取消写入');
    return {stage:failures.length?'RED':'GREEN',failures,dom,option,ownerOption,graph:before,exchanges};
  }
  if(stage==='reimport'){
    const before=await read(endpoint);await open();await choose('转换器件','sa');await field('显式端口方向 port_directions（JSON对象）').fill('{"IN":"unknown"}');
    const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:900,downloadThroughput:-1,uploadThroughput:-1});
    const late=page.waitForResponse(r=>r.url().includes('/conversion-preview')&&r.request().method()==='POST');await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();
    const imported=page.waitForResponse(r=>r.url().includes('/import/from-template')&&r.request().method()==='POST');
    // 已打开Modal时用原生产事件处理器触发外层重导入，验证不是仅靠遮罩防护。
    await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='重导入默认拓扑');b[Object.keys(b).find(k=>k.startsWith('__reactProps'))].onClick()});
    await modal.waitFor({state:'hidden'});const r=await imported;const result=await r.json();exchanges.push({status:r.status(),response:result});eq(r.status(),200,'隔离无采用历史图重导入失败');await late;
    await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await cdp.detach();
    await page.getByText(result.name,{exact:true}).waitFor();await open();eq(await modal.getByTestId('conversion-preview').count(),0,'重导入迟到预览残留');eq(await field('转换器件').inputValue(),'','重导入没有清会话');eq(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),true,'新图可确认旧预览');await shot('reimport-session-cleared');await close();return {stage,before,checks,exchanges};
  }
  if(stage==='collection'){
    const panel=page.getByTestId('route-calibration-panel');
    await panel.getByRole('textbox',{name:'完整校准通路',exact:true}).click();await page.getByRole('option').filter({hasText:'wire-out'}).first().click();await panel.getByTestId('selected-calibration-path').waitFor();
    for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','Task3软件验证参考件'],['接收线缆损耗','2'],['接收线缆记录来源','隔离非实测声明']])await panel.getByLabel(label,{exact:false}).fill(value);
    // 保存原可达事件处理器；disabled以外还必须有实时ref门。
    await page.evaluate(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='转换旧配置');window.__pc04ConversionHandler=button[Object.keys(button).find(k=>k.startsWith('__reactProps'))].onClick});
    const assertLocked=async label=>{
      eq(await page.getByRole('button',{name:'转换旧配置',exact:true}).isDisabled(),true,label+'按钮未锁');
      await page.evaluate(()=>window.__pc04ConversionHandler());
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      eq(await modal.count(),0,label+'事件层ref门未挡');await shot(label);
    };
    const start=async()=>{await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();const wait=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/fixed-route-acquisitions'));await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();const r=await wait;const body=await r.json();exchanges.push({request:r.request().postDataJSON(),status:r.status(),response:body});eq(r.status(),202,'采集启动失败');eq(body.status,'running','非真实running');return body};
    const first=await start();await assertLocked('collection-running');
    await page.context().setOffline(true);try{await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();await panel.getByText('采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。',{exact:true}).waitFor();await assertLocked('cancel-unconfirmed')}finally{await page.context().setOffline(false)}
    await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='转换旧配置')?.disabled,{timeout:20000});
    for(let i=0;i<2;i++){
      await open();await choose('转换器件','sa');await field('显式端口方向 port_directions（JSON对象）').fill(JSON.stringify({IN:i?'input':'unknown'}));await preview();await save();await shot(`released-reentry-${i+1}`);
    }
    return {stage,first,checks,exchanges,history:await read(`/lab-profiles/${lab.id}/fixed-route-acquisitions`),boundary:'全Mock仅证明软件生命周期，不证明实物停发'};
  }
  const before=await read(endpoint);
  await open();await choose('转换器件','ce');await field('显式端口清单 ports（JSON数组）').fill('["OUT"]');await close();eq(await read(endpoint),before,'取消写入');
  await open();await choose('转换器件','ce');eq(await field('显式端口清单 ports（JSON数组）').inputValue(),'','取消残留输入');
  await field('显式端口清单 ports（JSON数组）').fill('["OUT"]');
  await field('显式目标类型').click();await page.getByRole('option',{name:'channel_emulator',exact:true}).click();await field('显式CE身份 ce_port').fill('B1.1');
  await page.context().setOffline(true);try{await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();await modal.getByTestId('conversion-error').waitFor();eq(await field('显式CE身份 ce_port').inputValue(),'B1.1','离线丢输入');await shot('offline-preserved')}finally{await page.context().setOffline(false)}
  const raceCdp=await page.context().newCDPSession(page);await raceCdp.send('Network.enable');
  await raceCdp.send('Network.emulateNetworkConditions',{offline:false,latency:900,downloadThroughput:-1,uploadThroughput:-1});
  const outdated=page.waitForResponse(r=>r.url().includes('/conversion-preview')&&r.request().method()==='POST');
  await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();
  await field('显式CE身份 ce_port').fill('B1.2');await field('显式CE身份 ce_port').fill('B1.1');await outdated;
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  eq(await modal.getByTestId('conversion-preview').count(),0,'同context迟到结果复活');
  eq(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),true,'编辑后可确认迟到结果');
  await raceCdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await raceCdp.detach();
  await preview();eq(await read(endpoint),before,'预览写入数据库');
  await page.context().setOffline(true);
  try{await modal.getByRole('button',{name:'确认转换并保存',exact:true}).click();await modal.getByTestId('conversion-error').filter({hasText:'输入已保留'}).waitFor();eq(await field('显式CE身份 ce_port').inputValue(),'B1.1','离线保存丢输入');await shot('offline-save-preserved')}
  finally{await page.context().setOffline(false)}
  eq(await read(endpoint),before,'离线确认写入数据库');await preview();
  await field('显式CE身份 ce_port').fill('B1.2');await field('显式CE身份 ce_port').fill('B1.1');eq(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),true,'改回未失效');await preview();
  const concurrentLabel=`bse并发保留-${Date.now()}`;
  const concurrent=structuredClone(before.nodes);concurrent.find(n=>n.id==='bse').label=concurrentLabel;
  const other=await page.request.patch(`${origin}/api/v1${endpoint}`,{data:{nodes:concurrent}});eq(other.status(),200,'并发写失败');
  await save(409);await modal.getByTestId('conversion-error').filter({hasText:'输入已保留'}).waitFor();eq(await field('显式CE身份 ce_port').inputValue(),'B1.1','409丢输入');await shot('stale409-preserved');
  await preview();
  const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:1000,downloadThroughput:-1,uploadThroughput:-1});
  const savedPromise=save();await page.getByRole('button',{name:'转换旧配置',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='保存拓扑')?.disabled);
  eq(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),true,'pending确认未锁');await shot('save-pending');
  const saved=await savedPromise;await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  eq(saved.id,before.id,'改变原图ID');eq(saved.nodes.find(n=>n.id==='ce').type,'channel_emulator','类型未保存');eq(saved.nodes.find(n=>n.id==='bse').label,concurrentLabel,'覆盖并发输入');
  // 同一物理线缆必须逐组明确确认；alias旧值保留。
  await open();await choose('转换连线','wire-out');await field('同一物理线缆量值owner原边').click();await page.getByRole('option').filter({hasText:/^wire-in ·/}).click();
  await modal.getByRole('checkbox',{name:'这两条边表示同一条物理线缆',exact:false}).check();await preview();await shot('owner-preview');
  const grouped=await save();eq(grouped.connections.find(e=>e.id==='wire-out').loss_owner_connection_id,'wire-in','归属未保存');eq(grouped.connections.find(e=>e.id==='wire-out').cable_loss_db,2,'alias旧值丢失');
  await open();await choose('转换连线','wire-out');eq(await field('显式标称损耗 cable_loss_db').isDisabled(),true,'alias仍可改损耗');await modal.getByRole('button',{name:'定位owner原边',exact:true}).click();await page.waitForFunction(()=>[...document.querySelectorAll('input')].some(el=>el.value.startsWith('wire-in ·')));
  await choose('转换连线','wire-out');await field('同一物理线缆量值owner原边').click();await page.getByRole('option',{name:'显式解组：两侧旧值恢复各自参与',exact:true}).click();await modal.getByRole('checkbox',{name:'这两条边表示同一条物理线缆',exact:false}).check();await preview();await shot('ungroup-preview');
  const ungrouped=await save();eq(Object.hasOwn(ungrouped.connections.find(e=>e.id==='wire-out'),'loss_owner_connection_id'),false,'撤销未删除键');
  // 真实迟到响应：CDP仅延迟网络，不替换API响应。
  await open();await choose('转换器件','sa');await field('显式端口方向 port_directions（JSON对象）').fill('{"IN":"unknown"}');
  await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:1200,downloadThroughput:-1,uploadThroughput:-1});
  const late=page.waitForResponse(r=>r.url().includes('/conversion-preview')&&r.request().method()==='POST');await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();
  await close();await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();const labs=await read('/lab-profiles');const labB=labs.find(l=>l.name==='PC04A4d转换乙');await page.getByRole('option').filter({hasText:labB.name}).click();await late;
  await page.getByText('PC04A4d图乙',{exact:true}).waitFor();await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await open();eq(await modal.getByTestId('conversion-preview').count(),0,'迟到响应污染新Lab');eq(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),true,'新Lab可确认旧预览');await shot('late-lab-isolated');await close();
  await cdp.detach();
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:lab.name}).click();await page.getByText('PC04A4d图甲',{exact:true}).waitFor();
  await page.getByRole('textbox',{name:'器件列表',exact:true}).fill('ce');await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').filter({hasText:/^B1.1 · ce ·/}).click();
  const drawer=page.getByRole('dialog',{name:'器件属性',exact:true});await drawer.getByRole('textbox',{name:'器件名称',exact:true}).fill('B1.1草稿保留');await drawer.getByRole('button',{name:'应用器件修改',exact:true}).click();await drawer.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});
  await open();await modal.getByText('原拓扑草稿未保存；请先原保存，或关闭转换继续草稿。转换不会自动覆盖。',{exact:true}).waitFor();eq(await modal.getByRole('button',{name:'预览转换差异',exact:true}).isDisabled(),true,'dirty可转换');await close();
  await page.getByTestId('topology-save-stage').filter({hasText:'拓扑草稿未保存'}).waitFor();eq(await read(endpoint),ungrouped,'转换取消覆盖服务器');await shot('dirty-cancel-preserved');
  return {stage:'GREEN',labId:lab.id,displayTopologyId:graph.id,checks,exchanges,before,saved,grouped,ungrouped};
}
