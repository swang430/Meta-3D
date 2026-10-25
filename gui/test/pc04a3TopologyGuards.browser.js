// 原生确认分阶段：首次删中间节点(accept)，取消声明(dismiss)，再次取消声明(accept)，最后端口替代流程。
async page=>{
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`;
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许全Mock');
  let ctx=await page.evaluate(()=>window.__pc04a3GuardContext);
  const choose=async id=>{await page.getByRole('textbox',{name:'器件列表',exact:true}).fill(id);await page.getByRole('option').filter({hasText:id}).click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor()};
  const close=async()=>{await page.getByRole('dialog',{name:'器件属性',exact:true}).getByRole('banner').getByRole('button').click();await page.getByRole('dialog').waitFor({state:'hidden'})};
  const stable=async()=>page.evaluate(()=>new Promise(resolve=>{let previous='',stable=0;const frame=()=>{const current=document.querySelector('.react-flow__viewport')?.getAttribute('style');stable=current===previous?stable+1:0;previous=current;if(stable>=5)resolve(true);else requestAnimationFrame(frame)};requestAnimationFrame(frame)}));
  const fit=async()=>{await page.getByRole('button',{name:'Fit View',exact:true}).click();await stable()};
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
  const store=async()=>page.evaluate(ctx=>{window.__pc04a3GuardContext=ctx},ctx);
  const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${ctx.topologyId}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;if(!r.ok())throw new Error(await r.text());await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor()};
  const pathInput=()=>page.getByRole('textbox',{name:'显式RF路径：按CE→探头顺序选择连线',exact:true});
  const clearPath=async()=>{await pathInput().press('Backspace');await pathInput().press('Backspace')};
  const declare=async ids=>{for(const id of ids){await pathInput().press('ArrowDown');await page.getByRole('option').filter({hasText:id}).click()}await page.keyboard.press('Escape');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'})};
  if(!ctx){
    const labs=await read('/lab-profiles'),lab=labs.find(l=>l.name==='PC04自动采集甲'),other=labs.find(l=>l.name==='PC04自动采集乙');
    const topology=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0],baseline=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
    const graph={nodes:baseline.nodes.map(n=>n.id==='probe1'?{...n,position:{x:700,y:60},params:{...n.params,rf_path_selection:{connection_ids:['guard-upper','guard-lower'],switch_mappings:[]}}}:n),
      connections:baseline.connections.filter(e=>e.id!=='fixed-v'),operating_modes:baseline.operating_modes.map(m=>m.id==='mimo_ota'?{...m,active_connections:['guard-upper','guard-lower','fixed-h']}:m)};
    graph.nodes.push({id:'guard-cable',type:'cable',label:'引用中间线缆',position:{x:330,y:60},params:{ports:['A','B'],visible_modes:['mimo_ota'],unknown:{keep:9}}});
    graph.connections.push({id:'guard-upper',source:'ce1',source_pin:'out',target:'guard-cable',target_pin:'A',calibrated_loss_db:0.75,cable_loss_db:0},
      {id:'guard-lower',source:'guard-cable',source_pin:'B',target:'probe1',target_pin:'in',cable_loss_db:2});
    const endpoint=`/switch-topologies/${topology.id}?lab_profile_id=${lab.id}`,setup=await page.request.patch(`${api}${endpoint}`,{data:graph});if(!setup.ok())throw new Error(await setup.text());
    const before=await read(endpoint),oldRoutes=await read(`/lab-profiles/${lab.id}/route-calibration-paths?topology_id=${topology.id}&operating_mode=mimo_ota`);
    await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await page.reload();await enter();
    ctx={stage:'delete-accepted',endpoint,topologyId:topology.id,labId:lab.id,before,checks:[],oldDigest:oldRoutes.find(r=>r.chain_id==='guard-lower').route_digest};
    await choose('guard-cable');await page.getByLabel('器件名称',{exact:true}).fill('拒绝后保留此输入');await store();await page.getByRole('button',{name:'删除器件',exact:true}).click();return;
  }
  if(ctx.stage==='delete-accepted'){
    await page.getByText(/显式路径引用连线 guard-upper、guard-lower/).last().waitFor();
    if(await page.getByLabel('器件名称',{exact:true}).inputValue()!=='拒绝后保留此输入')throw new Error('被引用节点删除拒绝后输入丢失');
    if(JSON.stringify(await read(ctx.endpoint))!==JSON.stringify(ctx.before))throw new Error('被引用节点删除非原子');
    await close();await page.locator('.react-flow__node[data-id="guard-cable"]').waitFor();ctx.checks.push('删除被引用中间节点原生确认后明确拒绝，草稿/输入/服务器均保持');
    await choose('probe1');await clearPath();ctx.stage='cancel-dismissed';await store();await page.getByRole('button',{name:'应用器件修改',exact:true}).click();return;
  }
  if(ctx.stage==='cancel-dismissed'){
    await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor();await page.getByText('保存顺序：未声明，仅服务器唯一链解析',{exact:true}).waitFor();
    if(JSON.stringify((await read(ctx.endpoint)).nodes.find(n=>n.id==='probe1').params.rf_path_selection.connection_ids)!=='["guard-upper","guard-lower"]')throw new Error('取消确认仍改了服务器');
    await close();await choose('probe1');await page.getByText('保存顺序：guard-upper → guard-lower',{exact:true}).waitFor();
    ctx.checks.push('取消显式声明专门确认，选择取消后旧draft及声明不变，重新打开仍为原路径');
    await clearPath();ctx.stage='cancel-accepted';await store();await page.getByRole('button',{name:'应用器件修改',exact:true}).click();return;
  }
  if(ctx.stage==='cancel-accepted'){
    await page.getByRole('dialog').waitFor({state:'hidden'});await save();
    if((await read(ctx.endpoint)).nodes.find(n=>n.id==='probe1').params.rf_path_selection!=null)throw new Error('明确确认后声明未取消');
    ctx.checks.push('明确确认取消声明后真实保存，恢复服务器唯一链语义');
    await choose('probe1');await declare(['guard-upper','guard-lower']);await save();
    await choose('guard-cable');await page.getByLabel('声明端口',{exact:true}).fill('A, B, NEW');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});await fit();
    const a=await page.locator('.react-flow__node[data-id="ce1"] .react-flow__handle.source[data-handleid="out"]').boundingBox(),b=await page.locator('.react-flow__node[data-id="guard-cable"] .react-flow__handle.target[data-handleid="NEW"]').boundingBox();
    await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:20});await page.mouse.up();
    const nextId=await page.waitForFunction(old=>{const ids=[...document.querySelectorAll('.react-flow__edge')].map(e=>e.getAttribute('data-id'));return ids.find(id=>!old.includes(id))},ctx.before.connections.map(e=>e.id));const replacement=await nextId.jsonValue();
    await choose('probe1');await clearPath();await declare([replacement,'guard-lower']);await fit();
    const found=await page.waitForFunction(()=>{const el=document.querySelector('.react-flow__edge[data-id="guard-upper"] .react-flow__edge-interaction');const m=el.getScreenCTM();for(const f of [.2,.3,.1,.4,.6,.7,.8,.9]){const p=el.getPointAtLength(el.getTotalLength()*f),x=m.a*p.x+m.c*p.y+m.e,y=m.b*p.x+m.d*p.y+m.f;if(document.elementFromPoint(x,y)?.closest('.react-flow__edge')===el.closest('.react-flow__edge'))return{x,y}}return null});const point=await found.jsonValue();await page.mouse.click(point.x,point.y);await page.getByRole('button',{name:'删除连线',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
    await choose('guard-cable');await page.getByLabel('声明端口',{exact:true}).fill('B, NEW');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});await save();
    const saved=await read(ctx.endpoint),newEdge=saved.connections.find(e=>e.id===replacement),cable=saved.nodes.find(n=>n.id==='guard-cable');
    if(newEdge.target_pin!=='NEW'||newEdge.calibrated_loss_db!=null||saved.connections.some(e=>e.id==='guard-upper')||JSON.stringify(cable.params.ports)!=='["B","NEW"]'||cable.params.unknown.keep!==9)throw new Error('端口替代流程错误或复制了旧校准');
    const routes=await read(`/lab-profiles/${ctx.labId}/route-calibration-paths?topology_id=${ctx.topologyId}&operating_mode=mimo_ota`),route=routes.find(r=>r.chain_id==='guard-lower');
    if(route.route_digest===ctx.oldDigest||JSON.stringify(route.connection_ids)!==JSON.stringify([replacement,'guard-lower']))throw new Error('未返回新的服务器路径身份');
    const select=page.getByRole('textbox',{name:'完整校准通路',exact:true});await select.click();await page.getByRole('option').filter({hasText:'guard-lower'}).click();
    await page.getByTestId('selected-calibration-path').waitFor();await page.screenshot({path:'output/playwright/pc04a3/guard-port-replacement.png',fullPage:true});
    ctx.checks.push('先加新端口→真实建替代边→重声明→删旧边→删旧端口→保存并选择新服务器路径；未知参数保持，新边不继承旧校准');
    ctx.stage='complete';ctx.replacement=replacement;ctx.newDigest=route.route_digest;await store();return ctx;
  }
  return ctx;
}
