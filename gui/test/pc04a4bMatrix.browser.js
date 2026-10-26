// 本片隔离真实HTTP综合验证；不route/mock响应，不接硬件。
async page=>{
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,stage=new URL(page.url()).searchParams.get('matrix')||'B01';
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const exchanges=[],checks=[],eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(`${m}: ${JSON.stringify(a)}`)};
  const request=async(method,path,body,expected=200)=>{const r=await page.request[method](`${api}${path}`,body===undefined?{}:{data:body}),value=await r.json();
    exchanges.push({method,path,body,status:r.status(),response:value});eq(r.status(),expected,`${method} ${path}`);return value};
  const read=path=>request('get',path),copy=v=>JSON.parse(JSON.stringify(v));
  eq((await read('/instruments/hal/status')).mode,'mock','非隔离Mock');
  const labs=await read('/lab-profiles'),lab=labs.find(l=>l.name==='PC04A4b端口甲'),other=labs.find(l=>l.name==='PC04A4b端口乙');
  if(!lab||!other)throw Error('缺少专用fixture');
  const listed=(await read(`/switch-topologies?lab_profile_id=${lab.id}&limit=100`)).items;
  let graph=listed.find(g=>g.nodes.some(n=>n.id==='ce_port'));
  // 组合POST保留全部行；编辑器按最新行显示，故用真实POST建立本fixture图的新副本再续验。
  if(listed[0].name.startsWith('矩阵')){const body={...copy(graph),lab_profile_id:lab.id};delete body.id;delete body.chamber_id;
    body.nodes=body.nodes.filter(n=>!n.id.startsWith('legacy-'));body.connections=body.connections.filter(e=>!e.id.startsWith('legacy-'));
    body.operating_modes=body.operating_modes.map(m=>({...m,active_connections:m.active_connections.filter(id=>!id.startsWith('legacy-'))}));
    graph=await request('post','/switch-topologies',body,201)}
  const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const paths=()=>read(`/lab-profiles/${lab.id}/route-calibration-paths?topology_id=${graph.id}&operating_mode=mimo_ota`);
  const enter=async(labId=lab.id)=>{await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),labId);await page.reload();
    await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
  const drawer=()=>page.getByRole('dialog',{name:'器件属性',exact:true});
  const close=async()=>{await drawer().getByRole('banner').getByRole('button').click();await drawer().waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const choose=async id=>{const input=page.getByRole('textbox',{name:'器件列表',exact:true});await input.fill(id);await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').filter({hasText:id}).first().click();await drawer().waitFor()};
  const apply=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await drawer().waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const role=async(id,value,prefix='端口角色')=>{await page.getByRole('textbox',{name:`${prefix} ${id}`,exact:true}).click();await page.getByRole('option',{name:value,exact:true}).click()};
  const save=async(expected=200)=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));
    await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending,body=await r.json();exchanges.push({method:'UI PATCH',request:r.request().postDataJSON(),status:r.status(),response:body});eq(r.status(),expected,'UI保存');
    await page.getByTestId('topology-save-stage').filter({hasText:expected===200?'拓扑已保存到服务器':'拓扑保存失败；草稿未保存'}).waitFor();if(expected===200)graph=await read(endpoint);return body};
  const shot=async suffix=>{await page.screenshot({path:`output/playwright/pc04a4b-task3-${stage}-${suffix}.png`,fullPage:true,animations:'disabled'});checks.push({suffix,dom:await page.locator('body').innerText()})};
  const mode=async name=>{await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name,exact:true}).click()};
  await enter();
  if(stage==='B01'){
    const types=[['channel_emulator','信道仿真器'],['communication_tester','基站仿真器'],['emcenter','射频开关及功放'],['probe','测试探头'],['reference_antenna','校准参考天线'],['signal_analyzer','校准分析仪'],['vna','矢量网络分析仪'],['pad','衰减器'],['amplifier','功放'],['combiner','合路器'],['cable','线缆'],['receive_cable','校准接收线缆'],['air_path','校准空气传播段'],['termination','负载']];
    for(const [kind,label] of types){
      await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:label,exact:true}).click();await page.getByRole('button',{name:'添加器件',exact:true}).click();
      const id=(await drawer().locator('p').first().innerText()).trim();
      await page.getByText('端口数量未声明/旧版示意',{exact:false}).first().waitFor();await close();
      await save(422);eq((await read(endpoint)).nodes.some(n=>n.id===id),false,'未声明新节点写入');
      await choose(id);await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('A, B');await apply();await save();
      eq(graph.nodes.find(n=>n.id===id).params.ports,['A','B'],'明确端口未写入');
      await choose(id);const text=await drawer().innerText();if(!text.includes(kind==='air_path'?'已声明虚拟参考端点 2':kind==='communication_tester'?'已声明逻辑端口 2':'已声明端口 2'))throw Error('数量/来源标签错误');
      checks.push({kind,id,text});await close();
    }
    await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
    await shot('reload');
  }else if(stage==='B02-B04'){
    // 四态同ID几何；普通不连线节点不会改变任何RF路径。
    for(const [value,label,source,target] of [['input','输入',0,1],['output','输出',1,0],['bidirectional','双向声明',1,1],['unknown','方向未声明，非双向能力',1,1]]){
      await choose('amplifier');await role('in',label);await apply();
      const node=page.locator('.react-flow__node[data-id="amplifier"]');eq(await node.locator('.source[data-handleid="in"]').count(),source,'source数量');eq(await node.locator('.target[data-handleid="in"]').count(),target,'target数量');
      await save();eq(graph.nodes.find(n=>n.id==='amplifier').params.port_directions.in,value,'四态落库');checks.push({value,source,target,text:await node.innerText()});
    }
    await choose('communication_tester');eq(await page.getByRole('textbox',{name:'BSE角色 RF5',exact:true}).inputValue(),'下行 dl','RF5不是dl');eq(await page.getByRole('textbox',{name:'BSE角色 UL1',exact:true}).inputValue(),'上行 ul','UL1不是ul');
    eq(await page.getByRole('textbox',{name:'BSE角色 DL1',exact:true}).inputValue(),'未声明','按名字猜DL1');await close();
    const before=copy(graph),nodes=copy(graph.nodes);nodes.find(n=>n.id==='communication_tester').params.port_directions={RF5:'input'};
    await request('patch',endpoint,{nodes},422);eq(await read(endpoint),before,'BSE冲突有副作用');
    // 16种组合均真实写边界，抽屉/拖线共用契约另有GUI行为回归。
    const allowed=[[false,false,false,false],[true,false,true,true],[true,false,true,true],[true,false,true,true]],directions=['input','output','bidirectional','unknown'];
    for(let i=0;i<4;i++)for(let j=0;j<4;j++){
      const a={id:'combo-a',type:'pad',label:'同角色多ID源',position:{x:100,y:100},params:{ports:['P','Q'],port_directions:{P:directions[i],Q:directions[i]}}},b={id:'combo-b',type:'pad',label:'同角色多ID目标',position:{x:700,y:100},params:{ports:['P','Q'],port_directions:{P:directions[j],Q:directions[j]}}};
      const body={...copy(before),lab_profile_id:lab.id,name:`矩阵${i}${j}`,is_default:false,nodes:[a,b],connections:[{id:'combo',source:a.id,source_pin:'P',target:b.id,target_pin:'Q'}],operating_modes:[{id:'mimo_ota',name:'矩阵',active_connections:['combo']}]};delete body.id;delete body.chamber_id;
      const result=await request('post',`/switch-topologies?lab_profile_id=${lab.id}`,body,allowed[i][j]?201:422);checks.push({source:directions[i],target:directions[j],accepted:allowed[i][j],id:result.id});
    }
    await shot('four-state-bse');
  }else if(stage==='B05-B06'){
    const caict=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0],url=`/switch-topologies/${caict.id}?lab_profile_id=${other.id}`;
    await enter(other.id);const old=caict.nodes.find(n=>!Object.hasOwn(n.params,'ports')&&n.type==='pad')||caict.nodes.find(n=>!Object.hasOwn(n.params,'ports'));
    if(!old)throw Error('旧CAICT缺失ports样本不存在');
    await choose(old.id);const defaults=await page.getByRole('textbox',{name:'声明端口',exact:true}).inputValue();await page.getByLabel('器件名称',{exact:true}).fill(`${old.label}·仅改名`);await apply();
    const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${caict.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const response=await pending;eq(response.status(),200,'CAICT改名');exchanges.push({request:response.request().postDataJSON(),response:await response.json()});
    let saved=await read(url);eq(saved.nodes.find(n=>n.id===old.id).params,old.params,'旧缺失变显式');eq(saved.connections,caict.connections,'改名改边');
    await choose(old.id);eq(await page.getByRole('textbox',{name:'声明端口',exact:true}).inputValue(),defaults,'显示建议漂移');await page.getByRole('button',{name:'应用端口声明',exact:true}).click();await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByText(/端口仍有连线|未列入显式声明/).last().waitFor();eq(await read(url),saved,'旧图声明拒绝污染服务器');await shot('caict-missing-ports-rejected');await close();
    const declared=caict.nodes.find(n=>Array.isArray(n.params.ports));await choose(declared.id);await apply();
    const p=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${caict.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await p;exchanges.push({request:r.request().postDataJSON(),response:await r.json()});eq(r.status(),200,'已有合法ports未改应用');saved=await read(url);eq(saved.nodes.find(n=>n.id===declared.id).params,declared.params,'已有声明被改写');
    const nodesBeforePA=copy(saved.nodes),edge=saved.connections.find(e=>e.pa_gain_db===20);if(!edge)throw Error('CAICT缺旧PA20边');const list=page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true});await list.fill(edge.id);await page.getByRole('option').filter({hasText:edge.id}).click();await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('Task3仅补来源，非实测');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor({state:'hidden'});
    const pendingPA=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${caict.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const pa=await pendingPA;eq(pa.status(),200,'旧PA来源保存');exchanges.push({request:pa.request().postDataJSON(),response:await pa.json()});saved=await read(url);eq(saved.nodes,nodesBeforePA,'PA来源改节点');for(const prior of caict.connections){const now=saved.connections.find(e=>e.id===prior.id);if(prior.id===edge.id){eq(now.pa_gain_db,prior.pa_gain_db,'PA来源改数值')}else eq(now,prior,'PA来源改别边')}
    await enter(other.id);await choose(old.id);await shot('caict-rename-reload');await close();checks.push({old,declared,defaults,saved});
  }else if(stage==='legacy-position'){
    const caict=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0],url=`/switch-topologies/${caict.id}?lab_profile_id=${other.id}`;
    const old=caict.nodes.find(n=>!Object.hasOwn(n.params,'ports')),nodes=copy(caict.nodes),moved=nodes.find(n=>n.id===old.id);moved.position={x:(old.position?.x??0)+30,y:(old.position?.y??0)+20};
    const saved=await request('patch',url,{nodes}),stored=await read(url);eq(stored.nodes,nodes,'旧图位置未保存');eq(stored.connections,caict.connections,'仅位置改了边');eq(stored.operating_modes,caict.operating_modes,'仅位置改了模式');eq(stored.nodes.find(n=>n.id===old.id).params,old.params,'仅位置补旧声明');
    await enter(other.id);await choose(old.id);await shot('caict-position-reload');await close();checks.push({old,moved,saved});
  }else if(stage==='legacy-default'){
    const node=graph.nodes.find(n=>n.id==='legacy-default-pad');if(!node||Object.hasOwn(node.params,'ports'))throw Error('缺专用无边历史缺声明样本');
    await choose(node.id);const defaults=await page.getByRole('textbox',{name:'声明端口',exact:true}).inputValue();eq(defaults,'in, out','旧显示默认');
    await page.getByRole('button',{name:'应用端口声明',exact:true}).click();await apply();await save();const stored=graph.nodes.find(n=>n.id===node.id);eq(stored.params.ports,['in','out'],'恰好相同显式意图丢失');eq(stored.params.opaque,node.params.opaque,'旧opaque丢失');if(Object.hasOwn(stored.params,'port_directions'))throw Error('注入unknown map');
    await enter();await choose(node.id);eq(await page.getByRole('textbox',{name:'声明端口',exact:true}).inputValue(),defaults,'重载不同');await shot('same-default-explicit-reload');await close();checks.push({node,defaults,stored});
  }else if(stage==='B07'){
    const original=copy(graph),nodes=copy(graph.nodes);if(!nodes.find(n=>n.id==='ce_port').params.ports.includes('NEW'))nodes.find(n=>n.id==='ce_port').params.ports.push('NEW');
    const replacement={id:'replacement-v',source:'ce_port',source_pin:'NEW',target:'probe',target_pin:'in',cable_loss_db:0};
    // 添加替代边但不纳入正常同时集合，先由探头显式重声明。
    graph=await request('patch',endpoint,{nodes,connections:[...graph.connections.filter(e=>e.id!=='replacement-v'),replacement],operating_modes:graph.operating_modes.map(m=>m.id==='mimo_ota'?{...m,active_connections:[...new Set([...m.active_connections,'replacement-v'])]}:m)});await enter();await choose('probe');
    const select=page.getByRole('textbox',{name:'显式RF路径：按CE→探头顺序选择连线',exact:true});
    await drawer().locator('button[aria-label="Remove fixed-v"]').count();
    // MultiSelect按原UI清空再选，顺序由选择顺序形成。
    await select.press('Backspace');await select.press('ArrowDown');await page.getByRole('option').filter({hasText:'replacement-v'}).click();await page.keyboard.press('Escape');await apply();await save();
    eq(graph.nodes.find(n=>n.id==='probe').params.rf_path_selection.connection_ids,['replacement-v'],'探头未重声明');
    const nextNodes=copy(graph.nodes),nextCE=nextNodes.find(n=>n.id==='ce_port');nextCE.params.ports=['in','NEW'];if(nextCE.params.port_directions)nextCE.params.port_directions=Object.fromEntries(Object.entries(nextCE.params.port_directions).filter(([id])=>id!=='out'));
    const connections=graph.connections.filter(e=>e.id!=='fixed-v'),modes=graph.operating_modes.map(m=>({...m,active_connections:[...new Set(m.active_connections.map(id=>id==='fixed-v'?'replacement-v':id))]}));
    graph=await request('patch',endpoint,{nodes:nextNodes,connections,operating_modes:modes});
    const selected=await paths();eq(selected.find(r=>r.polarization==='V').connection_ids,['replacement-v'],'服务器未重选替代链');
    const invalid=copy(graph.nodes);invalid.find(n=>n.id==='probe').params.rf_path_selection={connection_ids:['missing'],switch_mappings:[]};await request('patch',endpoint,{nodes:invalid},422);eq(await read(endpoint),graph,'错误引用污染');
    await enter();await choose('probe');await shot('rewire-reload');await close();checks.push({original,selected});
  }else if(stage==='B10-B12'){
    const before=copy(graph),priorDirection=before.nodes.find(n=>n.id==='amplifier').params.port_directions?.out??'unknown',labels={input:'输入',output:'输出',bidirectional:'双向声明',unknown:'方向未声明，非双向能力'};
    await choose('amplifier');await role('out',priorDirection==='bidirectional'?'输入':'双向声明');await close();await choose('amplifier');eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),labels[priorDirection],'取消泄漏');
    await role('out','输出');await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('Task3离线仍保留4a来源');await apply();
    await choose('amplifier');await page.getByLabel('器件名称',{exact:true}).fill('取消本次未应用名称');await close();
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();eq(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')),lab.id,'dirty切Lab');
    await page.context().setOffline(true);try{await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByTestId('topology-save-stage').filter({hasText:'拓扑保存失败；草稿未保存'}).waitFor()}finally{await page.context().setOffline(false)}
    await choose('amplifier');eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),'输出','离线丢角色');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'Task3离线仍保留4a来源','离线丢4a意图');eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),before.nodes.find(n=>n.id==='amplifier').label,'未应用取消污染');await close();
    await page.evaluate(()=>{window.__pc04Saving=[];window.__pc04Observer=new MutationObserver(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='保存拓扑');if(button?.disabled)window.__pc04Saving.push({save:button.disabled,inputs:['器件列表','新增器件类型','操作模式'].every(k=>document.querySelector(`input[aria-label="${k}"]`)?.disabled),draggable:document.querySelectorAll('.react-flow__node.draggable').length,connectable:document.querySelectorAll('.react-flow__handle.connectablestart,.react-flow__handle.connectableend').length})});window.__pc04Observer.observe(document.body,{subtree:true,childList:true,attributes:true})});
    await save();const samples=await page.evaluate(()=>{window.__pc04Observer.disconnect();return window.__pc04Saving});if(!samples.some(v=>v.save&&v.inputs&&!v.draggable&&!v.connectable))throw Error('没有捕捉真实保存pending锁');checks.push({samples});
    await page.getByRole('button',{name:'添加器件',exact:true}).click();const id=(await drawer().locator('p').first().innerText()).trim();await close();await save(422);
    await choose(id);await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('A,B');await apply();await save();
    await enter();await choose('amplifier');eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),'输出','重载丢角色');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'Task3离线仍保留4a来源','重载丢4a');await shot('retry-reload');await close();
    await mode('校准接线');await choose('probe');await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('NEW');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();const message=page.getByText(/端口仍有连线/).last();await message.waitFor();const error=await message.innerText();if(!error.includes('fixed-v')||!error.includes('reference-0'))throw Error(`未定位全模式引用：${error}`);checks.push({allReferences:error});await close();await mode('MIMO OTA 测试');
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();const otherGraph=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];await page.getByText(otherGraph.name,{exact:true}).waitFor();eq(await page.locator('.react-flow__node[data-id="amplifier"]').count(),0,'乙泄漏甲');
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:lab.name}).click();await page.getByText(graph.name,{exact:true}).waitFor();await choose('amplifier');eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),'输出','回甲丢声明');await shot('lab-roundtrip');await close();
  }else if(stage==='B08-B13'){
    const historyUrl=`/lab-profiles/${lab.id}/fixed-route-acquisitions`,history=await read(historyUrl),snapshots=history.map(r=>({run_id:r.run_id,result:r.result}));
    if(history.length<2)throw Error('先执行两轮真实采集');
    const beforePaths=await paths(),normal=await read(`/switch-topologies/${graph.id}/paths/mimo_ota?lab_profile_id=${lab.id}`),matrix=await read(`/switch-topologies/${graph.id}/calibration-matrix/mimo_ota?lab_profile_id=${lab.id}`);
    const payload=route=>({chain_id:route.chain_id,topology_id:graph.id,route_digest:route.route_digest,configuration_digest:route.configuration_digest,frequency_mhz:2595,requested_power_dbm:-30,reference_antenna:'软件验证参考件',receive_cable_loss_db:2,receive_cable_source:'隔离声明',fixed_route_confirmed:true,safety_confirmed:true,sample_count:2});
    let previous=beforePaths.find(r=>r.polarization==='V');
    for(const id of ['ce_port','reference_antenna']){
      const inDirection=graph.nodes.find(n=>n.id===id).params.port_directions?.in==='input'?'方向未声明，非双向能力':'输入';
      await choose(id);await role('in',inDirection);await role('out','输出');await apply();
      await page.getByTestId('route-calibration-panel').getByRole('textbox',{name:'完整校准通路',exact:true}).isDisabled().then(v=>eq(v,true,'脏图仍可选旧路径'));
      await save();const current=(await paths()).find(r=>r.polarization==='V');if(current.route_digest===previous.route_digest)throw Error('声明未改变route_digest');
      await request('post',historyUrl,payload(previous),422);previous=current;
      const field=page.getByTestId('route-calibration-panel').getByRole('textbox',{name:'完整校准通路',exact:true});
      await field.click();await page.getByRole('option').filter({hasText:'fixed-h'}).first().click();
      await field.click();await page.getByRole('option').filter({hasText:current.chain_id}).first().click();
      await page.getByTestId('selected-calibration-path').waitFor();checks.push({id,current});
    }
    const lossProjection=rows=>rows.map(({source_node,target_node,...metrics})=>({...metrics,source_node:source_node.id,target_node:target_node.id}));
    eq(lossProjection(await read(`/switch-topologies/${graph.id}/paths/mimo_ota?lab_profile_id=${lab.id}`)),lossProjection(normal),'方向改了损耗路径');eq(await read(`/switch-topologies/${graph.id}/calibration-matrix/mimo_ota?lab_profile_id=${lab.id}`),matrix,'方向改了校准矩阵');
    const after=await read(historyUrl);eq(after.map(r=>({run_id:r.run_id,result:r.result})),snapshots,'方向重写旧冻结记录');
    const run=history[0],reject=await request('post',`/lab-profiles/${lab.id}/route-calibration-applications`,{acquisition_run_id:run.run_id,route_digest:run.result.request.route_digest,expected_current_application_id:null,idempotency_key:crypto.randomUUID(),confirmed:true,adoption_valid_until:'2099-01-01T00:00:00Z'},422);
    checks.push({noFormalPromotion:true,reject});await enter();await shot('digest-reload');
  }else if(stage==='B11'){
    const panel=page.getByTestId('route-calibration-panel'),historyUrl=`/lab-profiles/${lab.id}/fixed-route-acquisitions`,oldHistory=await read(historyUrl);
    const field=panel.getByRole('textbox',{name:'完整校准通路',exact:true});await field.click();await page.getByRole('option').filter({hasText:'fixed-v'}).first().click();await panel.getByTestId('selected-calibration-path').waitFor();
    for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','Task3隔离软件验证参考件'],['接收线缆损耗','2'],['接收线缆记录来源','Task3非实测声明']])await panel.getByLabel(label,{exact:false}).fill(value);
    const lock=()=>page.evaluate(()=>({inputs:['器件列表','新增器件类型','操作模式'].every(k=>document.querySelector(`input[aria-label="${k}"]`)?.disabled),buttons:['添加器件','保存拓扑'].every(k=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===k)?.disabled),draggable:document.querySelectorAll('.react-flow__node.draggable').length,connectable:document.querySelectorAll('.react-flow__handle.connectablestart,.react-flow__handle.connectableend').length,dialogs:document.querySelectorAll('[role="dialog"]').length}));
    const assertLock=async label=>{const value=await lock();if(!value.inputs||!value.buttons||value.draggable||value.connectable||value.dialogs)throw Error(`${label}锁失败${JSON.stringify(value)}`);checks.push({label,value})};
    const start=async()=>{await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/fixed-route-acquisitions'));await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();const r=await response;eq(r.status(),202,'开始采集');const body=await r.json();exchanges.push({request:r.request().postDataJSON(),response:body,status:r.status()});eq(body.status,'running','非真实running');return body};
    const first=await start();await assertLock('服务器真实running');
    await page.context().setOffline(true);
    try{await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();await panel.getByText('采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。',{exact:true}).waitFor();await assertLock('离线取消未确认');await shot('unknown-cancel-locked')}finally{await page.context().setOffline(false)}
    await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled);
    const finished=await read(`${historyUrl}/${first.run_id}`);if(!['simulated','cancelled'].includes(finished.status))throw Error('首轮不是服务器终态');eq(finished.result.net_loss_db,null,'Mock损耗伪造');eq(finished.result.samples,[],'Mock样本伪造');eq(finished.formal_eligible,false,'Mock资格提升');
    await choose('amplifier');eq(await page.getByRole('textbox',{name:'声明端口',exact:true}).isEnabled(),true,'首轮释放未恢复声明');await role('in','方向未声明，非双向能力');await close();
    const second=await start();await assertLock('第二轮真实running');const cancel=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith(`/${second.run_id}/cancel`));await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();const r=await cancel;eq(r.status(),200,'第二轮取消');exchanges.push({cancelResponse:await r.json()});
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled);
    const cancelled=await read(`${historyUrl}/${second.run_id}`);eq(cancelled.status,'cancelled','取消未持久化');await choose('communication_tester');eq(await page.getByRole('textbox',{name:'BSE角色 RF5',exact:true}).isEnabled(),true,'第二轮释放未恢复BSE');await shot('second-release');await close();
    eq((await read(historyUrl)).length,oldHistory.length+2,'多启动任务');checks.push({finished,cancelled});
  }else if(stage==='all-states'){
    let priorMetrics=null,priorMatrix=null;
    const projection=rows=>rows.map(({source_node,target_node,...metrics})=>({...metrics,source_node:source_node.id,target_node:target_node.id}));
    for(const declared of [false,true]){
      const body={...copy(graph),lab_profile_id:lab.id,name:`PC04A4b全通路-${declared?'明确':'unknown'}`};delete body.id;delete body.chamber_id;
      body.nodes=body.nodes.map(n=>({...n,params:{...n.params,port_directions:Object.fromEntries(n.params.ports.map(port=>{
        const role=n.params.port_roles?.[port],source=body.connections.some(e=>e.source===n.id&&(e.source_pin??'out')===port),target=body.connections.some(e=>e.target===n.id&&(e.target_pin??'in')===port);
        return[port,!declared?'unknown':role==='dl'?'output':role==='ul'?'input':source&&target?'bidirectional':source?'output':target?'input':'bidirectional'];
      }))}}));
      const created=await request('post','/switch-topologies',body,201),url=`/switch-topologies/${created.id}?lab_profile_id=${lab.id}`;
      const selections=await read(`/lab-profiles/${lab.id}/route-calibration-paths?topology_id=${created.id}&operating_mode=mimo_ota`),route=selections.find(r=>r.polarization==='V');
      const metrics=projection(await read(`/switch-topologies/${created.id}/paths/mimo_ota?lab_profile_id=${lab.id}`)),matrix=await read(`/switch-topologies/${created.id}/calibration-matrix/mimo_ota?lab_profile_id=${lab.id}`);
      if(priorMetrics){eq(metrics,priorMetrics,'全明确改损耗');eq(matrix,priorMatrix,'全明确改校准矩阵')}priorMetrics=metrics;priorMatrix=matrix;
      const historyUrl=`/lab-profiles/${lab.id}/fixed-route-acquisitions`,payload={chain_id:route.chain_id,topology_id:created.id,route_digest:route.route_digest,configuration_digest:route.configuration_digest,frequency_mhz:2595,requested_power_dbm:-30,reference_antenna:'Task3全态软件验证参考',receive_cable_loss_db:2,receive_cable_source:'非实测',fixed_route_confirmed:true,safety_confirmed:true,sample_count:2};
      const started=await request('post',historyUrl,payload,202);
      let record=started;
      for(let attempt=0;record.status==='running'&&attempt<100;attempt++){
        await page.waitForFunction(stamp=>Date.now()>stamp,Date.now()+150,{polling:50});
        record=await read(`${historyUrl}/${started.run_id}`);
      }
      eq(record.status,'simulated','全态Mock未完成');eq(record.formal_eligible,false,'全态提升资格');eq(record.result.net_loss_db,null,'全态生成损耗');eq(record.result.samples,[],'全态生成实测样本');
      await request('post',`/lab-profiles/${lab.id}/route-calibration-applications`,{acquisition_run_id:record.run_id,route_digest:route.route_digest,expected_current_application_id:null,idempotency_key:crypto.randomUUID(),confirmed:true,adoption_valid_until:'2099-01-01T00:00:00Z'},422);
      await enter();await shot(declared?'all-explicit':'all-unknown');checks.push({declared,route,record,metrics,matrix,stored:await read(url)});
    }
  }else if(stage==='geometry'){
    const kinds=['amplifier','pad','combiner','cable','receive_cable','antenna','probe','reference_antenna','channel_emulator','communication_tester','emcenter','signal_analyzer','vna','termination','air_path','ce_port','bse_port','sa_port','switch_slot'];
    for(const kind of kinds){
      const bse=['communication_tester','bse_port'].includes(kind),pin=bse?'RF5':'P1',sourceParams={ports:[pin,'P2','Q1'],port_directions:{[pin]:'output',P2:'output',Q1:'input'},visible_modes:['calibration']};
      if(bse)sourceParams.port_roles={[pin]:'dl'};
      if(['receive_cable','reference_antenna','signal_analyzer','air_path'].includes(kind))sourceParams.connection_scope='calibration';
      const body={name:`PC04A4b几何-${kind}`,lab_profile_id:lab.id,switch_category_id:graph.switch_category_id,nodes:[{id:'geo-source',type:kind,label:`几何-${kind}`,position:{x:80,y:100},params:sourceParams},{id:'geo-target',type:'pad',label:'几何目标',position:{x:700,y:100},params:{ports:['I1','I2'],port_directions:{I1:'input',I2:'input'},visible_modes:['calibration']}}],connections:[],operating_modes:[{id:'calibration',name:'校准接线',active_connections:[]}]};
      const created=await request('post','/switch-topologies',body,201);await enter();await mode('校准接线');await page.getByRole('button',{name:'Fit View',exact:true}).click();
      await page.waitForFunction(()=>new Promise(resolve=>{let same=0,last='';const tick=()=>{const now=document.querySelector('.react-flow__viewport')?.getAttribute('style');same=now===last?same+1:0;last=now;if(same>5)resolve(true);else requestAnimationFrame(tick)};tick()}));
      const source=page.locator(`.react-flow__node[data-id="geo-source"] .source[data-handleid="${pin}"]`),target=page.locator('.react-flow__node[data-id="geo-target"] .target[data-handleid="I1"]');
      const a=await source.boundingBox(),b=await target.boundingBox();await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:15});await page.mouse.up();
      const edge=page.locator('.react-flow__edge').first();await edge.waitFor({state:'attached'});const id=await edge.getAttribute('data-id'),path=edge.locator('.react-flow__edge-path');
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const ends=await path.evaluate(p=>{const m=p.getScreenCTM(),point=l=>{const q=p.getPointAtLength(l);return{x:m.a*q.x+m.c*q.y+m.e,y:m.b*q.x+m.d*q.y+m.f}};return[point(0),point(p.getTotalLength())]});
      const currentA=await source.boundingBox(),currentB=await target.boundingBox();
      if(Math.hypot(ends[0].x-currentA.x-currentA.width,ends[0].y-currentA.y-currentA.height/2)>3||Math.hypot(ends[1].x-currentB.x,ends[1].y-currentB.y-currentB.height/2)>3)throw Error(`${kind}几何不对齐${JSON.stringify({ends,currentA,currentB})}`);
      if(!await path.getAttribute('marker-end'))throw Error(`${kind}明确合法边缺箭头`);
      const middle=await path.evaluate(p=>{const v=p.getPointAtLength(p.getTotalLength()/2),m=p.getScreenCTM();return{x:m.a*v.x+m.c*v.y+m.e,y:m.b*v.x+m.d*v.y+m.f}});await page.mouse.click(middle.x,middle.y);const dialog=page.getByRole('dialog',{name:'连线参数编辑',exact:true});await dialog.waitFor();
      await page.getByRole('textbox',{name:'源端口',exact:true}).click();const options=await page.getByRole('listbox').getByRole('option').allTextContents();if(!options.some(t=>t.includes(pin))||!options.some(t=>t.includes('P2'))||options.some(t=>t.includes('Q1')))throw Error(`${kind}候选与角色不一致${options}`);await page.keyboard.press('Escape');
      await page.getByRole('textbox',{name:'目标端口',exact:true}).click();const targets=await page.getByRole('listbox').getByRole('option').allTextContents();if(!targets.some(t=>t.includes('I1'))||!targets.some(t=>t.includes('I2')))throw Error('同角色不同名目标被合并');await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'取消',exact:true}).click();await dialog.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});
      const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${created.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const saved=await pending;eq(saved.status(),200,'几何边保存');const final=await read(`/switch-topologies/${created.id}?lab_profile_id=${lab.id}`);eq(final.connections[0].source_pin,pin,'UI前缀污染pin');eq(final.connections[0].target_pin,'I1','目标pin污染');
      exchanges.push({kind,request:saved.request().postDataJSON(),response:await saved.json(),get:final});checks.push({kind,id,ends,options,targets});
      await shot(kind);
    }
  }else if(stage==='B09'){
    const before=await read(endpoint),otherGraph=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
    const bad={name:'非法默认图',switch_category_id:graph.switch_category_id,lab_profile_id:lab.id,is_default:true,nodes:[{id:'noports',type:'pad',label:'未声明',params:{}}],connections:[],operating_modes:[]};await request('post','/switch-topologies',bad,422);
    const n=copy(graph.nodes);n.find(n=>n.id==='ce_port').params.ports=['invalid-only'];await request('patch',endpoint,{nodes:n,name:'不得生效',is_default:true},422);
    await request('patch',`/switch-topologies/${graph.id}?lab_profile_id=${other.id}`,{name:'跨Lab禁止'},409);eq(await read(endpoint),before,'失败污染甲');eq(await read(`/switch-topologies/${otherGraph.id}?lab_profile_id=${other.id}`),otherGraph,'失败污染乙');
    checks.push({atomic:true});await shot('atomic');
  }else throw Error(`未知stage ${stage}`);
  const result={stage,checks,exchanges,final:await read(endpoint)};await page.evaluate(v=>window.__pc04a4bMatrix=v,result);return result;
}
