// playwright-cli --session pc04a4e run-code --filename；输入 localStorage 的本片manifest与URL stage。
// 仅DOM/真实鼠标/真实HTTP；不访问React内部，不替换API响应。
async page => {
  const manifest = await page.evaluate(()=>JSON.parse(localStorage.getItem('pc04a4e.manifest')));
  if(!manifest?.all_category_and_lab_bindings_mock)throw Error('缺少已核Mock manifest');
  const origin = new URL(page.url()).origin, stage = new URL(page.url()).searchParams.get('stage')||'inventory';
  const lab=manifest.labs[stage==='reimport'?1:0], api=origin+'/api/v1', exchanges=[],checks=[],attempt=Date.now();
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(m+': '+JSON.stringify(a)+' != '+JSON.stringify(b))};
  const check=(v,m)=>{if(!v)throw Error(m)};
  const request=async(method,path,data,status=200)=>{const r=await page.request[method](api+path,data?{data}:{});const body=await r.json();exchanges.push({origin:'编程真实HTTP',method,path,request:data,status:r.status(),response:body});eq(r.status(),status,path);return body};
  const endpoint=id=>`/switch-topologies/${id}?lab_profile_id=${lab.lab_id}`;
  let graphId=stage==='caict'?lab.source_topology_id:stage.startsWith('legacy')?lab.legacy_topology_id:lab.display_topology_id;
  const read=()=>request('get',endpoint(graphId));
  const shot=async(name)=>{const path=`output/playwright/pc04a4e-${stage}-${attempt}-${name}.png`;await page.screenshot({path,fullPage:true,animations:'disabled'});return path};
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
  const selectSwitch=async(category)=>{await page.getByRole('textbox',{name:'射频开关设备',exact:true}).click();await page.getByRole('option').filter({hasText:category}).click()};
  const reload=async()=>{await page.reload();await enter();await selectSwitch(stage==='caict'?'PC04A4eCAICT源图':stage.startsWith('legacy')?'PC04A4e历史参考图':'射频开关');};
  const drawer=page.getByRole('dialog',{name:'器件属性',exact:true});
  const choose=async id=>{await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});const input=page.getByRole('textbox',{name:'器件列表',exact:true});await input.fill(id);await page.getByRole('listbox',{name:'器件列表',exact:true}).locator(`[role="option"][value="${id}"]`).click();await drawer.waitFor()};
  const close=async()=>{await drawer.getByRole('banner').getByRole('button').click();await drawer.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const apply=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await drawer.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'})};
  const save=async(status=200)=>{const waiting=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graphId}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await waiting;const body=await r.json();exchanges.push({origin:'DOM保存',method:'PATCH',url:r.url(),request:r.request().postDataJSON(),status:r.status(),response:body});eq(r.status(),status,'DOM保存');if(status===200)await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();return read()};
  const modal=page.getByRole('dialog',{name:'转换旧配置',exact:true});
  const openConversion=()=>page.getByRole('button',{name:'转换旧配置',exact:true}).click();
  const selectConversion=async(kind,id)=>{await modal.getByRole('textbox',{name:kind==='node'?'转换器件':'转换连线',exact:true}).fill(id);await page.getByRole('option').filter({hasText:new RegExp(`^${id} ·`)}).click()};
  const preview=async()=>{const waiting=page.waitForResponse(r=>r.url().includes('/conversion-preview'));await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();const r=await waiting;const body=await r.json();exchanges.push({origin:'DOM转换预览',request:r.request().postDataJSON(),status:r.status(),response:body});eq(r.status(),200,'预览');await modal.getByTestId('conversion-preview').waitFor();return body};
  const confirm=async(status=200)=>{const waiting=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graphId}`));await modal.getByRole('button',{name:'确认转换并保存',exact:true}).click();const r=await waiting;exchanges.push({origin:'DOM转换确认',request:r.request().postDataJSON(),status:r.status(),response:await r.json()});eq(r.status(),status,'转换确认');if(status===200)await modal.waitFor({state:'hidden'});};
  const cancelConversion=async()=>{await modal.getByRole('button',{name:'取消转换',exact:true}).click();await modal.waitFor({state:'hidden'});await page.locator('.mantine-Modal-overlay').waitFor({state:'hidden'})};
  try {
    eq((await request('get','/instruments/hal/status')).mode,'mock','HAL必须Mock');
    await page.goto(origin+'/?stage='+stage);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.lab_id);await reload();
    const initial=await read();await page.getByText(initial.name,{exact:true}).waitFor();
    if(stage==='inventory'||stage.startsWith('nominal-')) {
      const fields={amplifier:['gain_db','PA标称增益','dB'],pad:['attenuation_db','标称衰减','dB'],combiner:['loss_db','标称插损','dB'],probe:['gain_dbi','标称天线增益','dBi'],antenna:['gain_dbi','标称天线增益','dBi'],reference_antenna:['gain_dbi','标称天线增益','dBi']};
      const targets=stage==='inventory'?initial.nodes:initial.nodes.filter(n=>n.type===stage.slice(8));
      for(const n of targets) {
        await choose(n.id);
        const before=await read();
        if(stage==='inventory') {
          const dom=await drawer.innerText();check(dom.includes(n.id),'打开对象错误');
          if(['cable','receive_cable'].includes(n.type))check(dom.includes('损耗仅在相邻连线编辑'),'线缆双算提示缺失');
          if(n.type==='air_path')check(dom.includes('虚拟参考端点'),'空气物理口混淆');
          if(n.type==='bse_port')check(dom.includes('物理连接器只读'),'BSE逻辑物理未分开');
          if(n.params.port_directions?.P1==='unknown')check((await page.getByRole('textbox',{name:'端口角色 P1',exact:true}).inputValue()).includes('非双向能力'),'unknown文案错误');
          await page.getByLabel('器件名称',{exact:true}).fill(n.label+' E08');await apply();const after=await save();eq(after.nodes.find(x=>x.id===n.id).params,n.params,'只改名污染声明');
          await reload();await choose(n.id);eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),n.label+' E08','重载名称');checks.push({id:'E08',type:n.type,node_id:n.id,before,after,dom:await drawer.innerText(),screenshot:await shot(n.id)});await close();
        } else {
          await close();const [key,label,unit]=fields[n.type];
          for(const value of [0,3.25,null]) {
            await choose(n.id);const input=page.getByLabel(`${label} (${unit})`,{exact:true});
            if(value===0&&['pad','combiner'].includes(n.type)){await input.fill('-1');check(await page.getByRole('button',{name:'应用器件修改',exact:true}).isDisabled(),'负衰减可应用');}
            await input.fill('1');await input.fill(value===null?'':String(value));
            await page.getByLabel(label+'来源说明',{exact:true}).fill('隔离验收输入，非实测');
            await page.getByLabel(label+'适用起始频率 (MHz)',{exact:true}).fill('2700');await page.getByLabel(label+'适用结束频率 (MHz)',{exact:true}).fill('2500');check(await page.getByRole('button',{name:'应用器件修改',exact:true}).isDisabled(),'非法频段可应用');
            await page.getByLabel(label+'适用起始频率 (MHz)',{exact:true}).fill('2500');await page.getByLabel(label+'适用结束频率 (MHz)',{exact:true}).fill('2700');await apply();const after=await save();
            eq(after.nodes.find(x=>x.id===n.id).params[key],value,'标称值');await reload();await choose(n.id);eq(await input.inputValue(),value===null?'':String(value),'标称重载');
            checks.push({id:'E07',type:n.type,node_id:n.id,key,value,after,dom:await drawer.innerText(),screenshot:await shot(n.id+'-'+value)});await close();
          }
        }
      }
    } else if(stage==='caict') {
      eq(graphId,lab.caict_display_topology_id,'原CAICT源/展示不同');const edge=initial.connections.find(e=>e.pa_gain_db!==null&&e.pa_gain_db!==undefined);check(edge,'无旧PA边');
      const locate=async()=>{await page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true}).fill(edge.id);await page.getByRole('option').filter({hasText:edge.id}).click();await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor()};
      for(const value of [0,14.5,null]){await locate();await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).fill('1');await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).fill(value===null?'':String(value));await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('E10隔离声明，非实测');await shot('pa-'+value);await page.getByRole('button',{name:'应用修改',exact:true}).click();const after=await save();eq(after.connections.find(e=>e.id===edge.id).pa_gain_db,value,'原PA未保存');eq(after.nodes,initial.nodes,'PA改了节点');await reload();checks.push({id:'E10-原PA',source_topology_id:graphId,display_topology_id:graphId,request_topology_id:graphId,edge_id:edge.id,value,after});}
    } else if(stage==='conversion'||stage==='owner') {
      const changes=stage==='conversion'?[['ce','channel_emulator'],['bse_port','communication_tester'],['sa_port','signal_analyzer']]:[['wire-out','wire-in'],['wire-out','__remove__']];
      for(const [id,target] of changes){const before=await read();await openConversion();await selectConversion(stage==='conversion'?'node':'edge',id);
        if(stage==='conversion'){await modal.getByRole('textbox',{name:'显式目标类型',exact:true}).click();await page.getByRole('option',{name:target,exact:true}).click();if(id==='ce')await modal.getByLabel('显式CE身份 ce_port',{exact:true}).fill('B1.1');}
        else {await modal.getByRole('textbox',{name:'同一物理线缆量值owner原边',exact:true}).click();await page.getByRole('option').filter({hasText:target==='__remove__'?'显式解组':/^wire-in ·/}).click();await modal.getByRole('checkbox').check();}
        const p=await preview();eq(await read(),before,'预览写库');const dom=await modal.innerText();await shot(id+'-'+target);await cancelConversion();eq(await read(),before,'取消写库');
        await openConversion();await selectConversion(stage==='conversion'?'node':'edge',id);
        if(stage==='conversion'){await modal.getByRole('textbox',{name:'显式目标类型',exact:true}).click();await page.getByRole('option',{name:target,exact:true}).click();if(id==='ce')await modal.getByLabel('显式CE身份 ce_port',{exact:true}).fill('B1.1');}
        else {await modal.getByRole('textbox',{name:'同一物理线缆量值owner原边',exact:true}).click();await page.getByRole('option').filter({hasText:target==='__remove__'?'显式解组':/^wire-in ·/}).click();await modal.getByRole('checkbox').check();}
        await preview();await confirm();await reload();const after=await read();checks.push({id:stage==='conversion'?'E10-转换':'E11-owner',before,preview:p,after,dom});
        if(stage==='owner'){
          const paths=await request('get',`/switch-topologies/${graphId}/paths/mimo_ota?lab_profile_id=${lab.lab_id}`);eq(paths.find(p=>p.path_id==='ce_to_probe').total_loss_db,target==='wire-in'?2:4,'通用owner消费');
          const formal=await request('get',`/lab-profiles/${lab.lab_id}/rf-chains`);checks.push({id:'E11-通用与正式末边',target,paths,formal});
        }
        if(stage==='owner'&&target==='wire-in'){
          await openConversion();await selectConversion('edge','wire-out');check(await modal.getByLabel('显式标称损耗 cable_loss_db',{exact:true}).isDisabled(),'alias非只读');await modal.getByRole('button',{name:'定位owner原边',exact:true}).click();await page.waitForFunction(()=>[...document.querySelectorAll('input')].some(i=>i.value.startsWith('wire-in ·')));check((await modal.getByRole('textbox',{name:'转换连线',exact:true}).inputValue()).startsWith('wire-in ·'),'owner定位错误');checks.push({id:'E11-alias只读定位',dom:await modal.innerText(),screenshot:await shot('alias-owner')});await cancelConversion();
        }
      }
    } else if(stage==='zero') {
      for(const value of [0,null,2]){await openConversion();await selectConversion('edge','wire-in');await modal.getByLabel('显式标称损耗 cable_loss_db',{exact:true}).fill(value===null?'null':String(value));const p=await preview();await confirm();await reload();const after=await read();eq(after.connections.find(e=>e.id==='wire-in').cable_loss_db,value,'未知零混淆');const paths=await request('get',`/switch-topologies/${graphId}/paths/mimo_ota?lab_profile_id=${lab.lab_id}`);checks.push({id:'E11-未知零',value,preview:p,after,paths,dom:await page.locator('body').innerText(),screenshot:await shot('value-'+value)});}
    } else if(stage==='lifecycle') {
      await choose('wire');await page.getByLabel('器件名称',{exact:true}).fill('取消不能泄漏');await close();await choose('wire');eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),initial.nodes.find(n=>n.id==='wire').label,'取消泄漏');
      await page.getByLabel('器件名称',{exact:true}).fill('E12已应用未保存');await apply();eq(await read(),initial,'应用写服务器');
      await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:manifest.labs[1].name}).click();eq(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')),lab.lab_id,'dirty跨Lab');
      await page.context().setOffline(true);try{await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByTestId('topology-save-stage').filter({hasText:'拓扑保存失败；草稿未保存'}).waitFor();checks.push({id:'E12-离线',dom:await page.locator('body').innerText(),screenshot:await shot('offline')});}finally{await page.context().setOffline(false)}
      eq(await read(),initial,'离线写服务器');await choose('wire');eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),'E12已应用未保存','离线丢草稿');await close();
      const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:700,downloadThroughput:-1,uploadThroughput:-1});
      const saving=save();await page.getByRole('button',{name:'保存拓扑',exact:true}).waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('input[aria-label="器件列表"]')?.disabled);check(await page.getByRole('button',{name:'添加器件',exact:true}).isDisabled(),'pending未锁');checks.push({id:'E13-save-pending',dom:await page.locator('body').innerText(),screenshot:await shot('pending')});await saving;await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await cdp.detach();await reload();
      const before=await read();await page.getByRole('button',{name:'Fit View',exact:true}).click();await page.waitForTimeout(500);const n=page.locator('.react-flow__node[data-id="wire"]'),box=await n.boundingBox();check(box,'无节点');await page.mouse.move(box.x+box.width/2,box.y+15);await page.mouse.down();await page.mouse.move(box.x+box.width/2+90,box.y+75,{steps:20});await page.mouse.up();const after=await save();check(JSON.stringify(after.nodes.find(n=>n.id==='wire').position)!==JSON.stringify(before.nodes.find(n=>n.id==='wire').position),'真实鼠标坐标未变');await reload();eq((await read()).nodes.find(n=>n.id==='wire').position,after.nodes.find(n=>n.id==='wire').position,'坐标重载');checks.push({id:'E09-真实拖动',before,after,dom:await page.locator('body').innerText(),screenshot:await shot('drag-reload')});
    } else if(stage==='pairs') {
      const selectPair=async(label,value)=>{await page.getByRole('textbox',{name:label,exact:true}).click();await page.getByRole('option').filter({hasText:new RegExp('^'+value+' ·')}).click()};
      for(const id of ['amplifier','pad','combiner']){
        await choose(id);await page.getByRole('button',{name:'声明无内部贯通',exact:true}).click();await apply();let after=await save();eq(after.nodes.find(n=>n.id===id).params.internal_paths,[],'空白名单');
        await choose(id);await page.getByRole('button',{name:'添加内部通路',exact:true}).click();await selectPair('内部输入口 1','IN');await selectPair('内部输出口 1','OUT');await shot(id+'-pair');await apply();after=await save();eq(after.nodes.find(n=>n.id===id).params.internal_paths,[{from_port:'IN',to_port:'OUT'}],'pair保存');await reload();await choose(id);eq(await page.getByRole('textbox',{name:'内部输入口 1',exact:true}).inputValue(),'IN · 输入','pair重载');checks.push({id:'E09-pair',node_id:id,after,dom:await drawer.innerText()});await close();
      }
      await choose('wire');await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('OUT');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();check(await drawer.isVisible(),'删除引用端口没有拒绝');checks.push({id:'E09-引用删除拒绝',dom:await page.locator('body').innerText(),screenshot:await shot('referenced-reject')});await close();
      const before=await read(),bad=structuredClone(before.nodes);bad.find(n=>n.id==='wire').params.port_directions={IN:'output',OUT:'input'};await request('patch',endpoint(graphId),{nodes:bad},422);eq(await read(),before,'错误方向写库');
      // 原画布真实鼠标从未引用pad输出接到未引用combiner输入；不调用内部处理器。
      await page.getByRole('button',{name:'Fit View',exact:true}).click();await page.waitForTimeout(700);
      const source=page.locator('.react-flow__node[data-id="pad"] .react-flow__handle.source[data-handleid="OUT"]');
      const target=page.locator('.react-flow__node[data-id="combiner"] .react-flow__handle.target[data-handleid="IN"]');
      const a=await source.boundingBox(),b=await target.boundingBox();check(a&&b,'方向handle缺失');await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:25});await page.mouse.up();
      await page.waitForFunction(count=>document.querySelectorAll('.react-flow__edge').length>count,before.operating_modes[0].active_connections.length);
      const after=await save();check(after.connections.length===before.connections.length+1,'真实连线没保存');checks.push({id:'E09-真实鼠标连线',before,after,screenshot:await shot('connected')});
    } else if(stage==='catalog') {
      const before=await request('get','/instruments/catalog');await choose('ce');await page.getByRole('textbox',{name:'仪器目录关联',exact:true}).click();await page.getByRole('option').filter({hasText:'信道仿真器'}).click();await apply();const after=await save();await reload();eq(await request('get','/instruments/catalog'),before,'目录关联改了驱动/连接能力');checks.push({id:'E08-目录仅引用',after,catalog:before,screenshot:await shot('association')});
    } else if(stage==='pair-routes') {
      for(const kind of ['amplifier','pad','combiner']){
        const ce=structuredClone(initial.nodes.find(n=>n.id==='ce')),probe=structuredClone(initial.nodes.find(n=>n.id==='probe'));
        delete probe.params.rf_path_selection;
        const mid={id:'mid',type:kind,label:'E09解析'+kind,position:{x:380,y:150},params:{ports:['IN','OUT'],port_directions:{IN:'input',OUT:'output'},internal_paths:[],visible_modes:['mimo_ota']}};
        const created=await request('post','/switch-topologies',{name:'E09独立解析图'+kind,lab_profile_id:lab.lab_id,switch_category_id:initial.switch_category_id,nodes:[ce,mid,probe],connections:[{id:'a',source:'ce',source_pin:'OUT',target:'mid',target_pin:'IN',cable_loss_db:0},{id:'b',source:'mid',source_pin:'OUT',target:'probe',target_pin:'IN',cable_loss_db:0}],operating_modes:[{id:'mimo_ota',name:'MIMO OTA 测试',active_connections:['a','b']}]},201);
        graphId=created.id;await reload();await page.getByText(created.name,{exact:true}).waitFor();eq(await request('get',`/switch-topologies/${graphId}/paths/mimo_ota?lab_profile_id=${lab.lab_id}`),[],'空pair自动全通');
        await choose('mid');await page.getByRole('button',{name:'添加内部通路',exact:true}).click();for(const [label,value] of [['内部输入口 1','IN'],['内部输出口 1','OUT']]){await page.getByRole('textbox',{name:label,exact:true}).click();await page.getByRole('option').filter({hasText:new RegExp('^'+value+' ·')}).click();}await apply();const after=await save();const paths=await request('get',`/switch-topologies/${graphId}/paths/mimo_ota?lab_profile_id=${lab.lab_id}`);eq(paths.length,1,'合法pair不可解析');eq(paths[0].total_loss_db,0,'pair叠加损耗');await reload();checks.push({id:'E09-pair保存与解析贯通',kind,created,after,paths,screenshot:await shot(kind)});
      }
    } else if(stage==='retry') {
      await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:'衰减器',exact:true}).click();await page.getByRole('button',{name:'添加器件',exact:true}).click();const id=(await drawer.locator('p').first().innerText()).trim();await close();
      await save(422);check(!(await read()).nodes.some(n=>n.id===id),'422写库');await choose(id);await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('A, B');await apply();const after=await save();eq(after.nodes.find(n=>n.id===id).params.ports,['A','B'],'422重试丢草稿');await reload();checks.push({id:'E12-422修正重试',node_id:id,after,screenshot:await shot('retry')});
      for(const profile of [manifest.labs[1],manifest.labs[0]]){await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:profile.name}).click();await page.getByText('PC04A4e图'+profile.name.slice(-1),{exact:true}).waitFor();checks.push({id:'E13-清洁切Lab',lab_id:profile.lab_id,dom:await page.locator('body').innerText()});}
      await selectSwitch('PC04A4e第二开关');await page.getByText('PC04A4e第二开关图甲',{exact:true}).waitFor();await selectSwitch('射频开关');await page.getByText(after.name,{exact:true}).waitFor();checks.push({id:'E13-切开关',dom:await page.locator('body').innerText(),screenshot:await shot('switch-roundtrip')});
    } else if(stage==='races') {
      await openConversion();await selectConversion('node','sa_port');await modal.getByLabel('显式端口方向 port_directions（JSON对象）',{exact:true}).fill('{"IN":"input","OUT":"output"}');
      const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:900,downloadThroughput:-1,uploadThroughput:-1});
      const late=page.waitForResponse(r=>r.url().includes('/conversion-preview'));await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();
      await modal.getByLabel('显式端口方向 port_directions（JSON对象）',{exact:true}).fill('{"IN":"unknown","OUT":"output"}');await late;eq(await modal.getByTestId('conversion-preview').count(),0,'迟到响应覆盖新输入');check(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),'迟到可确认');checks.push({id:'E13-preview在途改输入',dom:await modal.innerText(),screenshot:await shot('late-preview')});
      await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await cdp.detach();await preview();
      const before=await read(),changed=structuredClone(before.nodes);changed.find(n=>n.id==='pad').label='并发写入保留';await request('patch',endpoint(graphId),{nodes:changed});await confirm(409);await modal.getByTestId('conversion-error').filter({hasText:'输入已保留'}).waitFor();checks.push({id:'E13-digest409',dom:await modal.innerText(),screenshot:await shot('409')});await preview();await confirm();await reload();eq((await read()).nodes.find(n=>n.id==='pad').label,'并发写入保留','409覆盖并发');
      await openConversion();await selectConversion('node','sa_port');await modal.getByLabel('显式端口方向 port_directions（JSON对象）',{exact:true}).fill('{"IN":"input","OUT":"output"}');
      const switchCdp=await page.context().newCDPSession(page);await switchCdp.send('Network.enable');await switchCdp.send('Network.emulateNetworkConditions',{offline:false,latency:1500,downloadThroughput:-1,uploadThroughput:-1});
      const lateSwitch=page.waitForResponse(r=>r.url().includes('/conversion-preview'));await modal.getByRole('button',{name:'预览转换差异',exact:true}).click();await cancelConversion();await selectSwitch('PC04A4e第二开关');
      const lateResponse=await lateSwitch;exchanges.push({origin:'DOM在途取消后真实切换开关',request:lateResponse.request().postDataJSON(),status:lateResponse.status(),response:await lateResponse.json()});
      await switchCdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});await switchCdp.detach();await page.getByText('PC04A4e第二开关图甲',{exact:true}).waitFor();await openConversion();eq(await modal.getByTestId('conversion-preview').count(),0,'换图保留转换会话');check(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),'换图可确认旧会话');checks.push({id:'E13-换图迟到响应会话失效',dom:await modal.innerText(),screenshot:await shot('context-invalidated')});await cancelConversion();
    } else if(stage==='reimport'||stage==='replace-protected') {
      const before=await read();
      const waiting=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/import/from-template'));await page.getByRole('button',{name:'重导入默认拓扑',exact:true}).click();const r=await waiting,body=await r.json();exchanges.push({origin:'DOM重导入',url:r.url(),status:r.status(),response:body});eq(r.status(),stage==='reimport'?200:409,'重导入状态');
      if(stage==='replace-protected')eq(await read(),before,'引用replace改了历史图');else {await page.getByText(body.name,{exact:true}).waitFor();await openConversion();eq(await modal.getByTestId('conversion-preview').count(),0,'重导入残留预览');check(await modal.getByRole('button',{name:'确认转换并保存',exact:true}).isDisabled(),'新图可确认旧预览');await cancelConversion();}
      checks.push({id:'E13-'+stage,before,body,dom:await page.locator('body').innerText(),screenshot:await shot('result')});
    } else if(stage==='collection') {
      const panel=page.getByTestId('route-calibration-panel'),root=`/lab-profiles/${lab.lab_id}/fixed-route-acquisitions`;
      await save();await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
      await panel.getByRole('textbox',{name:'完整校准通路',exact:true}).click();await page.getByRole('option').filter({hasText:'wire-out'}).first().click();await panel.getByTestId('selected-calibration-path').waitFor();
      for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','E14隔离软件参考件'],['接收线缆损耗','2'],['接收线缆记录来源','隔离非实测声明']])await panel.getByLabel(label,{exact:false}).fill(value);
      const old=await request('get',root),records=[];
      for(let round=0;round<2;round++){
        await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();
        const waiting=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/fixed-route-acquisitions'));await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();const response=await waiting,run=await response.json();eq(response.status(),202,'采集启动');exchanges.push({origin:'DOM单路启动',request:response.request().postDataJSON(),status:response.status(),response:run});eq(run.status,'running','未观察running');
        check(await page.getByRole('button',{name:'添加器件',exact:true}).isDisabled(),'运行未锁');
        await page.context().setOffline(true);try{await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();await panel.getByText('采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。',{exact:true}).waitFor();check(await page.getByRole('button',{name:'添加器件',exact:true}).isDisabled(),'取消未知提前解锁');checks.push({id:'E14-取消未知',round,run,dom:await page.locator('body').innerText(),screenshot:await shot('cancel-unknown-'+round)});}finally{await page.context().setOffline(false)}
        await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
        await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled,{timeout:25000});
        const record=await request('get',root+'/'+run.run_id);eq(record.formal_eligible,false,'Mock正式资格');eq(record.result.net_loss_db,null,'Mock量值');eq(record.result.samples,[],'Mock样本');
        const preview=await request('get',root+'/'+run.run_id+'/application-preview');eq(preview.eligibility.eligible_for_adoption,false,'Mock采用');records.push(record);
        await request('post',`/lab-profiles/${lab.lab_id}/route-calibration-applications`,{acquisition_run_id:record.run_id,route_digest:record.result.request.route_digest,expected_current_application_id:null,idempotency_key:crypto.randomUUID(),confirmed:true,adoption_valid_until:'2099-01-01T00:00:00Z'},422);
        const diagnostic=await request('get','/diagnostic-runs/'+run.run_id);checks.push({id:'E14-诊断原件',round,diagnostic});
        await choose('wire');await page.getByLabel('器件名称',{exact:true}).fill('E14轮次'+round);await apply();await save();await panel.getByTestId('selected-calibration-path').waitFor();
        checks.push({id:'E14-终态恢复编辑保存',round,record,preview,dom:await page.locator('body').innerText(),screenshot:await shot('terminal-'+round)});
      }
      check(records[0].run_id!==records[1].run_id,'重入复用run');eq((await request('get',root)).length,old.length+2,'采集次数');
      await panel.getByRole('button',{name:'查看记录',exact:true}).last().click();checks.push({id:'E15-采集历史查看',dom:await panel.innerText(),screenshot:await shot('history')});
    } else if(stage==='batch') {
      const panel=page.getByTestId('route-batch-panel'),root=`/lab-profiles/${lab.lab_id}/route-calibration-batches`,jobs=[];
      await panel.locator('.mantine-MultiSelect-root').click();await page.getByRole('option').filter({hasText:'wire-out'}).click();await page.keyboard.press('Escape');
      for(const [label,value] of [['批量频点（MHz，逗号分隔）','2595'],['批量请求功率（dBm，不作实测值）','-30'],['每项采样数（2–10）','2'],['参考天线／位置 wire-out @2595','E14隔离参考'],['接收线损（dB） wire-out @2595','2'],['接收线依据 wire-out @2595','隔离非实测声明']])await panel.getByLabel(label,{exact:true}).fill(value);
      for(let round=0;round<2;round++){
        await panel.getByRole('checkbox',{name:'已核对清单的固定接线条件',exact:true}).check();await panel.getByRole('checkbox',{name:'已确认请求功率及现场安全条件',exact:true}).check();
        let waiting=page.waitForResponse(r=>r.url().includes('/route-calibration-batches/preview'));await panel.getByRole('button',{name:'预览完整批清单',exact:true}).click();let r=await waiting;eq(r.status(),200,'批预览');exchanges.push({origin:'DOM批预览',request:r.request().postDataJSON(),response:await r.json()});
        waiting=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/route-calibration-batches'));await panel.getByRole('button',{name:'明确开始此批校准',exact:true}).click();r=await waiting;const run=await r.json();eq(r.status(),202,'批启动');jobs.push(run);exchanges.push({origin:'DOM批启动',request:r.request().postDataJSON(),response:run});check(await page.getByRole('button',{name:'添加器件',exact:true}).isDisabled(),'批未锁');
        const manual=panel.getByTestId('batch-manual');await manual.waitFor();const pending=await request('get',root+'/'+run.job_id);check(pending.items.some(i=>i.status!=='simulated'),'批越过人工步骤');
        await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill('E14隔离参考');await manual.getByRole('checkbox',{name:'确认仅对应当前项和当前人工步骤',exact:true}).check();await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click();
        await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='添加器件')?.disabled,{timeout:25000});const completed=await request('get',root+'/'+run.job_id);eq(completed.status,'completed','批未完成');check(completed.items.every(i=>i.status==='simulated'),'批伪实测');checks.push({id:'E14-批两轮人工继续',round,pending,completed,dom:await panel.innerText(),screenshot:await shot('round-'+round)});
      }
      check(jobs[0].job_id!==jobs[1].job_id,'批重入复用job');
    } else if(stage==='legacy-metadata') {
      const edge=initial.connections.find(e=>e.id==='pa-reference-edge');
      await page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true}).fill(edge.id);await page.getByRole('option').filter({hasText:edge.id}).click();
      const dialog=page.getByRole('dialog',{name:'连线参数编辑',exact:true});await dialog.waitFor();check((await dialog.innerText()).includes('旧值格式未核实'),'旧字符串未提示');
      await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('E07仅metadata，保留旧字符串/缺键');await page.getByRole('button',{name:'应用修改',exact:true}).click();const after=await save();await reload();checks.push({id:'E07-metadata-only旧字符串及缺键',before:initial,after,screenshot:await shot('metadata-only')});
    } else if(stage==='legacy') {
      const root=`/lab-profiles/${lab.lab_id}`;
      initial.name+=' E15盘点';await request('patch',endpoint(graphId),{name:initial.name});await reload();
      const baseline=await request('get',root+'/calibration-scope');
      await openConversion();await selectConversion('edge','rx-analyzer');await modal.getByRole('textbox',{name:'同一物理线缆量值owner原边',exact:true}).click();await page.getByRole('option').filter({hasText:/^reference-rx ·/}).click();await modal.getByRole('checkbox').check();await preview();await confirm();
      const compared=await request('post',root+'/calibration-scope/compare',{baseline});check(compared.requires_review,'参考owner未触发scope复核');
      await page.getByRole('tab',{name:'总览',exact:true}).click();const card=page.getByTestId('calibration-scope');await card.getByRole('button',{name:'保留配置快照',exact:true}).click();const waiting=page.waitForResponse(r=>r.url().includes('/calibration-scope/compare'));await card.getByRole('button',{name:'比较配置变化',exact:true}).click();const response=await waiting;eq(response.status(),200,'scope GUI比较');exchanges.push({origin:'DOM scope比较',request:response.request().postDataJSON(),response:await response.json()});checks.push({id:'E15-scope',baseline,compared,dom:await card.innerText(),screenshot:await shot('scope')});
      await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await selectSwitch('PC04A4e历史参考图');await page.getByText(initial.name,{exact:true}).waitFor();
      const before=await request('get',root+'/fixed-route-acquisitions');await request('get',root+`/route-calibration-paths?topology_id=${graphId}&operating_mode=mimo_ota`,undefined,422);
      await request('post',root+'/fixed-route-acquisitions',{topology_id:graphId,chain_id:'wire-out',configuration_digest:compared.current.digest,frequency_mhz:2595,requested_power_dbm:-30,reference_antenna:'E15隔离参考',receive_cable_loss_db:2,receive_cable_source:'隔离声明',fixed_route_confirmed:true,safety_confirmed:true,sample_count:2},422);
      eq(await request('get',root+'/fixed-route-acquisitions'),before,'非法参考新增采集');checks.push({id:'E15-盘点非采集资格',dom:await page.getByTestId('route-calibration-panel').innerText(),screenshot:await shot('strict-reject')});
    } else throw Error('尚未实现阶段 '+stage);
    return {stage,status:'GREEN',graph_id:graphId,checks,exchanges,boundary:'仅本阶段所列分支，未列分支不视为通过'};
  }catch(error){return {stage,status:'FAILED',error:String(error.stack||error),graph_id:graphId,checks,exchanges,dom:await page.locator('body').innerText(),screenshot:await shot('failure')};}
}
