// 逐类真实画布矩阵；matrixType来自页面URL。最后保留真实删除确认供CLI响应。
async page=>{
  page.setDefaultTimeout(15000);
  await page.setViewportSize({width:1800,height:1200});
  const type=new URL(page.url()).searchParams.get('matrixType'),origin=new URL(page.url()).origin,api=`${origin}/api/v1`;
  const menu={cable:'线缆',receive_cable:'校准接收线缆',pad:'衰减器',amplifier:'功放',combiner:'合路器',termination:'负载',probe:'测试探头',channel_emulator:'信道仿真器',communication_tester:'基站仿真器',emcenter:'射频开关及功放',vna:'矢量网络分析仪',reference_antenna:'校准参考天线',signal_analyzer:'校准分析仪',air_path:'校准空气传播段'};
  if(![...Object.keys(menu),'ce_port','bse_port','switch_slot','antenna','sa_port'].includes(type))throw new Error('未知矩阵类型');
  const passive=['cable','receive_cable','pad','amplifier','combiner','termination','air_path','antenna','sa_port'];
  const calibration=['receive_cable','reference_antenna','signal_analyzer','air_path'].includes(type),mode=calibration?'calibration':'mimo_ota';
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许专属全Mock');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04自动采集甲');
  const topology=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
  const endpoint=`/switch-topologies/${topology.id}?lab_profile_id=${lab.id}`,checks=[];
  const seedNodes=[
    {id:'anchor',type:'pad',label:'矩阵接线目标',position:{x:1400,y:230},params:{ports:['in','other'],visible_modes:['mimo_ota','calibration']}},
    {id:'preserve',type:'pad',label:'保留未知参数',position:{x:10,y:400},params:{ports:['in'],visible_modes:['mimo_ota','calibration'],unknown:{keep:1}}},
  ];
  const historical=!menu[type]||passive.includes(type);
  if(historical)seedNodes.push({id:'historical',type,label:'未声明历史器件',position:{x:100,y:50},params:{visible_modes:[mode],unknown:{keep:7},...(calibration?{connection_scope:'calibration'}:{})}});
  const modes=[{id:'mimo_ota',name:'正常矩阵',active_connections:[]},{id:'calibration',name:'校准矩阵',active_connections:[]},{id:'unrelated',name:'无关模式',active_connections:[]}];
  const setup=await page.request.patch(`${api}${endpoint}`,{data:{nodes:seedNodes,connections:[],operating_modes:modes}});if(!setup.ok())throw new Error(await setup.text());
  await page.goto(`${origin}/?matrixType=${type}`);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await page.reload();
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
  await enter();
  const selectMode=async()=>{const input=page.getByRole('textbox',{name:'操作模式',exact:true});if(await input.inputValue()!==(calibration?'校准矩阵':'正常矩阵')){await input.click();await page.getByRole('option',{name:calibration?'校准矩阵':'正常矩阵',exact:true}).click()}};
  await selectMode();
  const choose=async id=>{const list=page.getByRole('textbox',{name:'器件列表',exact:true});await list.fill(id);await page.getByRole('option').filter({hasText:id}).click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor()};
  const close=async()=>{await page.getByRole('dialog',{name:'器件属性',exact:true}).getByRole('banner').getByRole('button').click();await page.getByRole('dialog').waitFor({state:'hidden'})};
  const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${topology.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;if(!r.ok())throw new Error(await r.text());await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor()};
  const stable=async()=>page.evaluate(()=>new Promise(resolve=>{let previous='',stable=0;const frame=()=>{const current=document.querySelector('.react-flow__viewport')?.getAttribute('style');stable=current===previous?stable+1:0;previous=current;if(stable>=5)resolve(true);else requestAnimationFrame(frame)};requestAnimationFrame(frame)}));
  const fit=async()=>{await page.getByRole('button',{name:'Fit View',exact:true}).click();await stable()};
  if(historical){
    const node=page.locator('.react-flow__node[data-id="historical"]');await node.waitFor();
    if((passive.includes(type)||type==='bse_port')&&await node.locator('.react-flow__handle').count())throw new Error(`${type}无声明却有画布端点`);
    await choose('historical');await close();await save();
    if('ports' in (await read(endpoint)).nodes.find(n=>n.id==='historical').params)throw new Error('仅查看属性自动写入端口');
    checks.push('历史无声明读取/查看不自动写ports；被动或bse无默认handles');
  }
  let id='historical';
  if(menu[type]){
    await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:menu[type],exact:true}).click();await page.getByRole('button',{name:'添加器件',exact:true}).click();
    checks.push('经真实新增菜单创建');
  }else{await choose('historical');checks.push('仅导入类型经器件列表编辑，不扩展新增菜单')}
  const label=`矩阵-${type}`;
  await page.getByLabel('器件名称',{exact:true}).fill(label);await page.getByLabel('声明端口',{exact:true}).fill('A, B');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
  const node=page.locator('.react-flow__node').filter({has:page.getByText(label,{exact:true})});await node.waitFor();id=await node.getAttribute('data-id');
  await fit();const before=await node.boundingBox();await page.mouse.move(before.x+before.width/2,before.y+18);await page.mouse.down();await page.mouse.move(before.x+before.width/2+(menu[type]?-300:65),before.y+18+85,{steps:12});await page.mouse.up();
  const after=await node.boundingBox();if(Math.abs(after.x-before.x)<15&&Math.abs(after.y-before.y)<15)throw new Error('节点拖动未生效');
  await fit();
  const a=await node.locator('.react-flow__handle.source[data-handleid="A"]').boundingBox(),b=await page.locator('.react-flow__node[data-id="anchor"] .react-flow__handle.target[data-handleid="in"]').boundingBox();
  if(!a||!b)throw new Error('声明端口没有形成真实handle');await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:20});await page.mouse.up();await page.locator('.react-flow__edge').waitFor();
  await save();let stored=await read(endpoint),savedNode=stored.nodes.find(n=>n.id===id),edge=stored.connections.find(e=>e.source===id&&e.target==='anchor');
  if(!edge||edge.source_pin!=='A'||edge.target_pin!=='in'||savedNode.label!==label||JSON.stringify(savedNode.params.ports)!=='["A","B"]')throw new Error('新增/属性/拖线未真实保存');
  if(JSON.stringify(stored.nodes.find(n=>n.id==='preserve'))!==JSON.stringify(seedNodes[1]))throw new Error('未知参数/无关节点原位置丢失');
  if(JSON.stringify(stored.operating_modes.find(m=>m.id==='unrelated').active_connections)!=='[]')throw new Error('无关模式被改');
  const savedPosition=savedNode.position;
  await page.reload();await enter();await selectMode();await page.locator(`.react-flow__node[data-id="${id}"]`).waitFor();await fit();
  // 沿既有曲线定位真实点击，不force、不派发事件。
  const found=await page.waitForFunction(id=>{const el=document.querySelector(`.react-flow__edge[data-id="${id}"] .react-flow__edge-interaction`);if(!el)return null;const m=el.getScreenCTM();for(const f of [.2,.3,.1,.4,.6,.7,.8,.9]){const p=el.getPointAtLength(el.getTotalLength()*f),x=m.a*p.x+m.c*p.y+m.e,y=m.b*p.x+m.d*p.y+m.f;if(document.elementFromPoint(x,y)?.closest('.react-flow__edge')===el.closest('.react-flow__edge'))return{x,y}}return null},edge.id);const point=await found.jsonValue();await page.mouse.click(point.x,point.y);
  await page.getByRole('textbox',{name:'源端口',exact:true}).click();await page.getByRole('option',{name:'B',exact:true}).click();await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});await save();
  stored=await read(endpoint);if(stored.connections.find(e=>e.id===edge.id).source_pin!=='B')throw new Error('改pin未持久化');if(JSON.stringify(stored.nodes.find(n=>n.id===id).position)!==JSON.stringify(savedPosition))throw new Error('reload或改pin丢失位置');
  checks.push('名称/端口应用、真实拖动/接线、改pin、保存GET/reload及位置/未知参数/无关模式保持');
  await choose(id);
  await page.screenshot({path:`output/playwright/pc04a3/matrix-${type}.png`,fullPage:true});
  await page.evaluate(value=>{window.__pc04a3MatrixPending=value},{type,id,edgeId:edge.id,endpoint,topologyId:topology.id,labId:lab.id,checks,mode});
  // 真实确认留给紧接的CLI dialog-accept；不改写window.confirm。
  await page.getByRole('button',{name:'删除器件',exact:true}).click();
}
