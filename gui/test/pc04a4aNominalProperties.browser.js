// 独立临时SQLite、全HAL Mock、真实HTTP；同一缺功能RED由原边抽屉产生。
async page=>{
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`;
  const stage=new URL(page.url()).searchParams.get('nominalStage');
  if(stage)return await nominalMatrix(page,stage,origin,api);
  page.setDefaultTimeout(12000);
  await page.setViewportSize({width:1800,height:1100});
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许隔离全Mock环境');
  const labs=await read('/lab-profiles'),lab=labs.find(l=>l.name==='PC04A4a标称乙');
  if(!lab)throw new Error('缺少专用fixture');
  const topology=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
  const endpoint=`/switch-topologies/${topology.id}?lab_profile_id=${lab.id}`;
  const graph=await read(endpoint),edge=graph.connections.find(e=>e.pa_gain_db!==null&&e.pa_gain_db!==undefined);
  if(!edge)throw new Error('真实GET未返回旧PA边');
  await page.goto(origin);
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await page.locator('.react-flow').first().waitFor();
  await page.getByRole('button',{name:'Fit View',exact:true}).click();
  await page.locator(`.react-flow__edge[data-id="${edge.id}"]`).click({force:true});
  await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor();
  // 模板边重叠时实点可能选中相邻边；按抽屉精确ID验证它确实来自真实旧PA图。
  const drawerText=await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).innerText();
  const opened=graph.connections.find(e=>drawerText.split('\n').includes(e.id));
  if(!opened||opened.pa_gain_db===null||opened.pa_gain_db===undefined)throw new Error('实际打开的边不是旧PA');
  await page.evaluate(result=>{window.__pc04a4aBaseline=result},{labId:lab.id,topologyId:topology.id,edge:opened,graph});
  const hasControl=await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).count();
  await page.screenshot({path:`output/playwright/pc04a4a-task3/${hasControl?'implemented':'original'}-edge-drawer.png`,fullPage:true,animations:'disabled'});
  console.log(JSON.stringify({stage:'真实GET及原抽屉已加载',labId:lab.id,topologyId:topology.id,edge,graph}));
  // RED必须止于缺控件，不把API/fixture/原抽屉打开失败当缺功能。
  await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).waitFor({state:'visible'});
  const checks=['真实GET、原画布边点击与标称控件可见'],requests=[];
  const equal=(a,b,message)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(`${message}: ${JSON.stringify(a)}`)};
  const save=async id=>{
    const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${id}`));
    await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
    const r=await pending;requests.push(r.request().postDataJSON());if(!r.ok())throw new Error(await r.text());
    await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();
  };
  const apply=()=>page.getByRole('button',{name:'应用修改',exact:true}).click();
  const locate=async id=>{
    const list=page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true});await list.fill(id);
    await page.getByRole('option').filter({hasText:id}).click();
    await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).getByText(id,{exact:true}).waitFor();
  };
  const gain=page.getByLabel('旧PA标称增益 (dB)',{exact:true});
  await gain.fill('0');
  await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill(' 操作员按铭牌录入，未校准 ');
  await page.getByLabel('旧PA标称增益适用结束频率 (MHz)',{exact:true}).fill('');
  await page.getByLabel('旧PA标称增益适用起始频率 (MHz)',{exact:true}).fill('2500');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='应用修改')?.disabled===true);
  await page.getByLabel('旧PA标称增益适用结束频率 (MHz)',{exact:true}).fill('2700');
  // 原控件真实事件与原Task1声明map，先改后回同显示值仍保留意图。
  await page.getByLabel('标称电缆损耗 (dB)',{exact:true}).fill('0.9');
  await page.getByLabel('标称电缆损耗 (dB)',{exact:true}).fill(String(opened.cable_loss_db));
  await apply();await save(topology.id);
  let stored=await read(endpoint),edited=stored.connections.find(e=>e.id===opened.id);
  equal(edited.pa_gain_db,0,'零未保存');
  equal(edited.nominal_metadata.pa_gain_db,{unit:'dB',source_note:'操作员按铭牌录入，未校准',frequency_range_mhz:[2500,2700]},'元数据未保存');
  equal(requests.at(-1).connection_numeric_declarations,{[opened.id]:['cable_loss_db']},'原数值事件声明未随应用保存');
  equal(stored.nodes,graph.nodes,'元数据保存覆盖了节点或位置');
  equal(stored.operating_modes,graph.operating_modes,'模式被改写');
  for(const row of graph.connections.filter(e=>e.id!==opened.id))equal(stored.connections.find(e=>e.id===row.id),row,'误改另一条边');
  checks.push('PA=0、来源去空白、频段成对；原损耗实际onChange/apply意图；真实PATCH/GET仅修改选中边');
  await locate(opened.id);await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('取消不应泄漏');
  await page.getByRole('button',{name:'取消',exact:true}).click();await locate(opened.id);
  equal(await page.getByLabel('旧PA标称增益来源说明',{exact:true}).inputValue(),'操作员按铭牌录入，未校准','取消浅引用泄漏');
  await page.getByRole('button',{name:'取消',exact:true}).click();
  const hiddenMode=graph.operating_modes.find(m=>!(m.active_connections??[]).includes(opened.id));
  if(hiddenMode){
    await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:hiddenMode.name,exact:true}).click();
    await locate(opened.id);
    equal(await page.getByRole('textbox',{name:'操作模式',exact:true}).inputValue(),hiddenMode.name,'定位擅自切换模式');
    await page.locator(`.react-flow__edge[data-id="${opened.id}"].selected`).waitFor();
    await page.getByText('当前模式隐藏连线（未切换模式）',{exact:false}).waitFor();
    checks.push('PA清单含0；非当前模式按精确边ID打开并高亮，不切换模式');
  }else await locate(opened.id);
  await gain.fill('');await apply();await save(topology.id);
  stored=await read(endpoint);equal(stored.connections.find(e=>e.id===opened.id).pa_gain_db,null,'清空未保存null');
  checks.push('取消未泄漏元数据；PA清空准确保存null');
  const normal=labs.find(l=>l.name==='PC04A4a标称甲');
  const normalGraph=(await read(`/switch-topologies?lab_profile_id=${normal.id}`)).items[0];
  const normalEndpoint=`/switch-topologies/${normalGraph.id}?lab_profile_id=${normal.id}`;
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),normal.id);await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  const chooseNode=async()=>{await page.getByRole('textbox',{name:'器件列表',exact:true}).fill('独立PA');await page.getByRole('option').filter({hasText:'独立PA'}).click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor()};
  await chooseNode();const nodeGain=page.getByLabel('PA标称增益 (dB)',{exact:true});
  equal(await nodeGain.inputValue(),'','新标称空值被填默认数');
  await nodeGain.fill('-');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='应用器件修改')?.disabled===true);
  await nodeGain.fill('0');await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('声明，非实测');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await save(normalGraph.id);
  const normalSaved=await read(normalEndpoint),pa=normalSaved.nodes.find(n=>n.id==='pa');
  equal(pa.params.gain_db,0,'节点零丢失');equal(pa.params.unknown,{keep:1},'扩展参数丢失');
  equal(pa.params.nominal_metadata.gain_db,{unit:'dB',source_note:'声明，非实测',frequency_range_mhz:null},'空频段不是null');
  for(const node of normalGraph.nodes)equal(normalSaved.nodes.find(n=>n.id===node.id).position,node.position,'标称编辑修改了坐标');
  equal(normalSaved.connections,normalGraph.connections,'保存补齐了稀疏边默认键');
  await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await chooseNode();
  equal(await nodeGain.inputValue(),'0','刷新后零未恢复');
  checks.push('节点中间串拒绝、零与空频段保存/GET/刷新恢复，未知参数、坐标及参考边缺键保持');
  await page.screenshot({path:'output/playwright/pc04a4a-task3/targeted-green.png',fullPage:true,animations:'disabled'});
  const result={checks,requests,caict:stored,normal:normalSaved};
  await page.evaluate(result=>{window.__pc04a4aTask2Result=result},result);
  console.log(JSON.stringify(result));

  // Task3使用同一真实API/浏览器入口分阶段归档；不清库、不伪造响应或冻结窗口。
  async function nominalMatrix(page,stage,origin,api){
    page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
    const checks=[],exchanges=[],evidence=[];
    const eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(`${m}: ${JSON.stringify(a)} !== ${JSON.stringify(b)}`)};
    const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
    if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许隔离全Mock');
    const labs=await read('/lab-profiles'),lab=labs.find(l=>l.name==='PC04A4a标称甲'),other=labs.find(l=>l.name==='PC04A4a标称乙');
    const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
    const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
    const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
    const referenceState=stage==='references'?await page.evaluate(()=>window.__pc04a4aReferences):null;
    if(!referenceState){await page.goto(`${origin}/?nominalStage=${stage}`);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await page.reload();await enter();}
    const nodeDialog=()=>page.getByRole('dialog',{name:'器件属性',exact:true});
    const choose=async id=>{await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});const list=page.getByRole('textbox',{name:'器件列表',exact:true});await list.click();await list.fill(id);await page.locator(`[role="option"][value="${id}"]`).click();await nodeDialog().waitFor()};
    const closeNode=async()=>{await nodeDialog().getByRole('banner').getByRole('button').click();await nodeDialog().waitFor({state:'hidden'})};
    const applyNode=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await nodeDialog().waitFor({state:'hidden'})};
    const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;exchanges.push({status:r.status(),request:r.request().postDataJSON(),response:await r.json()});if(!r.ok())throw new Error(JSON.stringify(exchanges.at(-1)));await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();return read(endpoint)};
    const reload=async()=>{await page.reload();await enter()};
    const shot=async suffix=>page.screenshot({path:`output/playwright/pc04a4a-task3/${stage}-${suffix}.png`,fullPage:true,animations:'disabled'});
    if(stage.startsWith('node-')){
      const kind=stage.slice(5),map={pad:['matrix-pad','attenuation_db','标称衰减','dB',[0,3.25,null]],combiner:['matrix-combiner','loss_db','标称插损','dB',[0,1.75,null]],antenna:['matrix-antenna','gain_dbi','标称天线增益','dBi',[3,-2,0,null]],probe:['probe1','gain_dbi','标称天线增益','dBi',[3,-2,0,null]],reference_antenna:['ref','gain_dbi','标称天线增益','dBi',[15,-2,0,null]],amplifier:[null,'gain_db','PA标称增益','dB',[null,0,21.25,-1]]};
      let [id,key,label,unit,values]=map[kind];
      if(!id){await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:'功放',exact:true}).click();await page.getByRole('button',{name:'添加器件',exact:true}).click();await page.getByLabel('器件名称',{exact:true}).fill('PC04A4a新PA');await page.getByLabel('声明端口',{exact:true}).fill('in, out');id=(await nodeDialog().locator('p').first().innerText()).trim();}
      for(let index=0;index<values.length;index++){
        const value=values[index];if(kind!=='amplifier'||index)await choose(id);
        const input=page.getByLabel(`${label} (${unit})`,{exact:true});
        if((kind==='pad'||kind==='combiner')&&index===0){
          await input.fill('-1');if(await page.getByRole('button',{name:'应用器件修改',exact:true}).isEnabled())throw new Error('负衰减未拒绝');
          await input.fill('0');await page.getByLabel(`${label}适用起始频率 (MHz)`,{exact:true}).fill('2700');
          if(await page.getByRole('button',{name:'应用器件修改',exact:true}).isEnabled())throw new Error('半频段未拒绝');
          await page.getByLabel(`${label}适用结束频率 (MHz)`,{exact:true}).fill('2500');
          if(await page.getByRole('button',{name:'应用器件修改',exact:true}).isEnabled())throw new Error('倒序频段未拒绝');
          checks.push('负值、半频段、倒序均禁用应用，局部草稿可继续修正');
        }
        // 空字段必须经真实输入再清空，才能成为明确null声明，而非未编辑缺键。
        await input.fill('1');await input.fill(value===null?'':String(value));
        await page.getByLabel(`${label}来源说明`,{exact:true}).fill(index===0?'   ':'  Task3声明，非实测  ');
        await page.getByLabel(`${label}适用起始频率 (MHz)`,{exact:true}).fill('2500');
        await page.getByLabel(`${label}适用结束频率 (MHz)`,{exact:true}).fill('2700');
        await shot(`${index}-input`);await applyNode();const stored=await save(),node=stored.nodes.find(n=>n.id===id);
        if(!node)throw new Error(`新节点ID未解析：${id}`);eq(node.params[key],value,'数值落库错误');
        eq(node.params.nominal_metadata[key],{unit,source_note:index===0?null:'Task3声明，非实测',frequency_range_mhz:[2500,2700]},'元数据落库错误');
        for(const prior of graph.nodes.filter(n=>n.id!==id))eq(stored.nodes.find(n=>n.id===prior.id),prior,'误改其它节点');
        eq(stored.connections,graph.connections,'误改连接');eq(stored.operating_modes,graph.operating_modes,'误改模式');
        await reload();await choose(id);eq(await input.inputValue(),value===null?'':String(value),'重载未恢复');
        evidence.push({value,stored,dom:await nodeDialog().innerText()});await shot(`${index}-reload`);await closeNode();
      }
      checks.push(`${kind}全部数值/空值、来源trim、单位/频段、PATCH/GET/reload及非目标保持`);
    }else if(stage==='legacy'){
      // 早期本片fixture的0声明样本未写visible_modes，只修正测试样本的显示声明，不清库。
      if(graph.nodes.some(n=>n.id.startsWith('zero-')&&!n.params.visible_modes)){
        const response=await page.request.patch(`${api}${endpoint}`,{data:{nodes:graph.nodes.map(n=>n.id.startsWith('zero-')?{...n,params:{...n.params,visible_modes:['mimo_ota','calibration']}}:n)}});
        if(!response.ok())throw new Error(await response.text());exchanges.push({fixtureVisibilitySetup:await response.json()});await reload();
      }
      for(const kind of ['channel_emulator','emcenter']){
        const absent=page.locator(`.react-flow__node[data-id="matrix-${kind}"]`),zero=page.locator(`.react-flow__node[data-id="zero-${kind}"]`);
        await choose(`matrix-${kind}`);await closeNode();
        if(!(await absent.innerText()).includes('端口数量未声明')||/4.*32|PA ×32/.test(await absent.innerText()))throw new Error('缺数量回退成能力');
        await choose(`zero-${kind}`);await closeNode();
        if(!(await zero.innerText()).includes('输入 0 / 输出 0，未核实'))throw new Error('0数量被回退');
      }
      const bad=graph.connections.find(e=>e.id==='legacy-bad-pa');eq(bad.pa_gain_db,'12','旧坏PAfixture错误');
      await page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true}).fill('legacy-bad-pa');await page.getByRole('option').filter({hasText:'legacy-bad-pa'}).click();
      await page.getByText('旧值格式未核实（原值只读）："12"；未主动编辑时保留原值。',{exact:true}).waitFor();
      await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('仅改来源');
      if(!await page.getByRole('button',{name:'应用修改',exact:true}).isEnabled())throw new Error('metadata-only不应要求重写旧数值');
      await shot('bad-unchanged');await page.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor({state:'hidden'});
      for(const id of ['matrix-cable','matrix-receive_cable']){await choose(id);await page.getByText('损耗仅在相邻连线编辑，不在器件重复计入。',{exact:false}).waitFor();if(await nodeDialog().getByLabel(/标称.*\(dB\)/).count())throw new Error('线缆有第二损耗');await closeNode()}
      const before=await read(endpoint);await choose('matrix-cable');await page.getByLabel('器件名称',{exact:true}).fill('线缆仅改名');await applyNode();
      await page.getByRole('button',{name:'Fit View',exact:true}).click();
      await page.waitForFunction(()=>new Promise(resolve=>{let count=0,last='';const tick=()=>{const now=document.querySelector('.react-flow__viewport')?.getAttribute('style');count=now===last?count+1:0;last=now;if(count>5)resolve(true);else requestAnimationFrame(tick)};tick()}));
      const node=page.locator('.react-flow__node[data-id="matrix-cable"]'),box=await node.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+15);await page.mouse.down();await page.mouse.move(box.x+box.width/2+85,box.y+90,{steps:15});await page.mouse.up();
      const saved=await save(),current=saved.nodes.find(n=>n.id==='matrix-cable');if(JSON.stringify(current.position)===JSON.stringify(before.nodes.find(n=>n.id==='matrix-cable').position))throw new Error('真实拖动没保存');
      eq(current.params,before.nodes.find(n=>n.id==='matrix-cable').params,'拖动注入标称键');eq(saved.connections,before.connections,'改名拖动改了边');eq(saved.operating_modes,before.operating_modes,'改名拖动改了模式');
      await reload();await choose('matrix-cable');eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),'线缆仅改名','改名未恢复');await shot('drag-reload');await closeNode();
      evidence.push({before,saved,afterReload:await read(endpoint)});checks.push('CE/EMCenter缺值与0不推断能力；旧坏PA读取/取消/改名拖动保形；线缆无第二损耗');
      // 同一新库的真实模板旧值，不批量补来源、不写chamber。
      const caict=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0],chamberBefore=await read(`/chambers/${other.chamber_config_id}`);
      await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),other.id);await page.reload();await enter();
      for(const value of [15,3]){const n=caict.nodes.find(n=>n.params?.gain_dbi===value);if(!n)throw new Error(`模板缺${value}`);await choose(n.id);eq(await page.getByLabel('标称天线增益 (dBi)',{exact:true}).inputValue(),String(value),'旧天线值丢失');await page.getByText('旧版标称/来源未声明；非实测',{exact:true}).waitFor();await shot(`template-${value}`);await closeNode()}
      eq(await read(`/chambers/${other.chamber_config_id}`),chamberBefore,'标称保存污染chamber');checks.push('CAICT旧15/3天线仍声明非实测，chamber独立域不变');
    }else if(stage==='recovery'){
      const before=await read(endpoint);await choose('pa');await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('取消不落库');await closeNode();eq(await read(endpoint),before,'取消写入服务器');await choose('pa');if(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue()==='取消不落库')throw new Error('取消污染草稿');
      await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('离线重试来源');await applyNode();
      await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();eq(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')),lab.id,'dirty跨Lab未阻止');
      await page.context().setOffline(true);try{await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByTestId('topology-save-stage').filter({hasText:'拓扑保存失败；草稿未保存'}).waitFor()}finally{await page.context().setOffline(false)}
      await choose('pa');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'离线重试来源','失败丢草稿');await closeNode();const stored=await save();await reload();await choose('pa');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'离线重试来源','重试保存未恢复');await shot('retry-reload');await closeNode();
      const otherEndpoint=`/switch-topologies/${other.id}?lab_profile_id=${other.id}`,otherGraph=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
      const cross=await page.request.patch(`${api}/switch-topologies/${graph.id}?lab_profile_id=${other.id}`,{data:{name:'禁止跨Lab'}});eq(cross.status(),409,'跨Lab写入未409');eq(await read(endpoint),stored,'409污染甲');eq(await read(`/switch-topologies/${otherGraph.id}?lab_profile_id=${other.id}`),otherGraph,'409污染乙');
      await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();await page.getByText(otherGraph.name,{exact:true}).waitFor();if(await page.locator('.react-flow__node[data-id="pa"]').count())throw new Error('清洁跨Lab泄漏节点');
      checks.push('来源取消不改草稿/GET；离线失败保留草稿、重试保存重载；dirty拒绝跨Lab、409双图原子、清洁切乙隔离');evidence.push({before,stored,crossStatus:cross.status(),otherGraph});
    }else if(stage==='collection'){
      const panel=page.getByTestId('route-calibration-panel'),history=`/lab-profiles/${lab.id}/fixed-route-acquisitions`;
      const choosePath=async()=>{const input=panel.getByRole('textbox',{name:'完整校准通路',exact:true});await input.click();await page.getByRole('option').filter({hasText:'fixed-v'}).click()};await choosePath();
      for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','Task3软件验证参考件'],['接收线缆损耗','2'],['接收线缆记录来源','Task3声明']])await panel.getByLabel(label,{exact:false}).fill(value);
      const start=async()=>{await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();const response=page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions')&&r.request().method()==='POST');await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();return response};
      const pending=start();await page.waitForFunction(()=>document.querySelector('input[aria-label="含旧PA标称的连线"]')?.disabled===true);
      const locked=await page.evaluate(()=>({inputs:['含旧PA标称的连线','器件列表','新增器件类型','操作模式'].every(label=>document.querySelector(`input[aria-label="${label}"]`)?.disabled),save:Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='保存拓扑')?.disabled,draggable:document.querySelectorAll('.react-flow__node.draggable').length,dialogs:document.querySelectorAll('[role="dialog"]').length}));
      if(!locked.inputs||!locked.save||locked.draggable||locked.dialogs)throw new Error(`真实pending锁失效${JSON.stringify(locked)}`);await shot('pending');const r=await pending;if(r.status()!==202)throw new Error(await r.text());const first=await r.json();
      await panel.getByText('模拟流程完成（无真实测量）',{exact:true}).first().waitFor();if(!await page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true}).isEnabled())throw new Error('完成后锁未恢复');
      if(await panel.getByRole('button',{name:'确认采用此实测记录',exact:true}).isEnabled())throw new Error('Mock可采用');
      const record=await read(`${history}/${first.run_id}`);if(record.status!=='simulated'||record.result.net_loss_db!==null||record.result.samples.length||record.formal_eligible!==false)throw new Error('模拟混正式');
      const rejected=await page.request.post(`${api}/lab-profiles/${lab.id}/route-calibration-applications`,{data:{acquisition_run_id:first.run_id,route_digest:first.result.request.route_digest,expected_current_application_id:null,idempotency_key:crypto.randomUUID(),confirmed:true,adoption_valid_until:'2099-01-01T00:00:00Z'}});eq(rejected.status(),422,'Mock服务器可采用');
      const second=await(await start()).json();const cancel=page.waitForResponse(r=>r.url().endsWith(`/${second.run_id}/cancel`)&&r.request().method()==='POST');await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();const cancelledResponse=await cancel;if(!cancelledResponse.ok())throw new Error(await cancelledResponse.text());await panel.getByText('已取消',{exact:true}).first().waitFor();const cancelled=await read(`${history}/${second.run_id}`);eq(cancelled.status,'cancelled','取消未落库');
      await choose('pa');if(!await page.getByLabel('PA标称增益 (dB)',{exact:true}).isEnabled()||!await page.getByRole('button',{name:'应用器件修改',exact:true}).isEnabled())throw new Error('取消后新控件未恢复');await shot('cancel-recovered');await closeNode();
      evidence.push({locked,first,record,cancelled,history:await read(history),applications:await read(`/lab-profiles/${lab.id}/route-calibration-applications?topology_id=${graph.id}&chain_id=fixed-v`)});eq(evidence[0].applications,[],'Mock创建采用记录');checks.push('真实pending定位/编辑/保存锁；Mock完成恢复且UI/API拒绝采用；真实POST取消及新控件恢复；全部历史保留');
    }else if(stage==='caict-pa'){
      const caict=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0],chamberBefore=await read(`/chambers/${other.chamber_config_id}`),url=`/switch-topologies/${caict.id}?lab_profile_id=${other.id}`;
      const edge=caict.connections.find(e=>e.pa_gain_db===20);if(!edge)throw new Error('缺少原典型20dB边');
      await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),other.id);await page.reload();await enter();
      for(const value of [0,-1,null]){
        const list=page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true});await list.click();await list.fill(edge.id);await page.locator(`[role="option"][value="${edge.id}"]`).click();
        await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).getByText(edge.id,{exact:true}).waitFor();await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).fill(value===null?'':String(value));await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('   ');await shot(`${value}-input`);await page.getByRole('button',{name:'应用修改',exact:true}).click();
        const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${caict.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const response=await pending;exchanges.push({status:response.status(),request:response.request().postDataJSON(),response:await response.json()});if(!response.ok())throw new Error(JSON.stringify(exchanges.at(-1)));
        const saved=await read(url);eq(saved.connections.find(e=>e.id===edge.id).pa_gain_db,value,'旧PA值未落库');eq(saved.nodes,caict.nodes,'旧PA编辑新增/修改节点');eq(saved.operating_modes,caict.operating_modes,'旧PA改变模式');eq(await read(`/chambers/${other.chamber_config_id}`),chamberBefore,'旧PA污染chamber');
        for(const prior of caict.connections.filter(e=>e.id!==edge.id))eq(saved.connections.find(e=>e.id===prior.id),prior,'旧PA误改其它边');evidence.push({value,saved});await reload();await shot(`${value}-reload`);
      }
      checks.push(`CAICT精确旧20dB边${edge.id}→0→负值→null，每步PATCH/GET/重载；空来源null、不新建PA、不改chamber/其它节点边模式`);
    }else if(stage==='cable-source'){
      await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:'校准接线',exact:true}).click();await page.getByRole('button',{name:'Fit View',exact:true}).click();
      const pointHandle=await page.waitForFunction(()=>{const el=document.querySelector('.react-flow__edge[data-id="reference-sparse"] .react-flow__edge-interaction');if(!el)return null;const m=el.getScreenCTM();for(const f of [.2,.3,.4,.6,.7,.8]){const p=el.getPointAtLength(el.getTotalLength()*f),x=m.a*p.x+m.c*p.y+m.e,y=m.b*p.x+m.d*p.y+m.f;if(document.elementFromPoint(x,y)?.closest('.react-flow__edge')===el.closest('.react-flow__edge'))return{x,y}}return null});
      const point=await pointHandle.jsonValue();await page.mouse.click(point.x,point.y);await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).getByText('reference-sparse',{exact:true}).waitFor();
      await page.getByLabel('标称电缆损耗来源说明',{exact:true}).fill('  Task3线缆来源，非实测  ');await shot('input');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
      // 只观察真实DOM提交窗口，不延迟/拦截请求，也不把结束后的状态冒充保存中。
      await page.evaluate(()=>{window.__nominalSavingSamples=[];window.__nominalSavingObserver=new MutationObserver(()=>{const save=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='保存拓扑');if(save?.disabled)window.__nominalSavingSamples.push({save:true,locate:document.querySelector('input[aria-label="含旧PA标称的连线"]')?.disabled,nodes:document.querySelector('input[aria-label="器件列表"]')?.disabled})});window.__nominalSavingObserver.observe(document.body,{subtree:true,attributes:true,childList:true})});
      const stored=await save();const savingSamples=await page.evaluate(()=>{window.__nominalSavingObserver.disconnect();return window.__nominalSavingSamples});if(!savingSamples.some(s=>s.save&&s.locate&&s.nodes))throw new Error('未观察到真实保存锁');
      const edge=stored.connections.find(e=>e.id==='reference-sparse'),prior=graph.connections.find(e=>e.id==='reference-sparse');
      eq(edge,{...prior,nominal_metadata:{cable_loss_db:{unit:'dB',source_note:'Task3线缆来源，非实测',frequency_range_mhz:null}}},'来源编辑新增第二损耗或改变缺键');
      await reload();evidence.push({stored,savingSamples});checks.push('真实曲线点击参考稀疏边，来源保存不补损耗/PA/默认字段；真实保存期间定位/编辑/保存锁被观察到');await shot('reload');
    }else if(stage==='references'){
      // 原生确认通过CLI dialog-accept处理，分阶段保存上下文，不重写window.confirm。
      if(!referenceState){const before=await read(endpoint);await choose('ce1');await page.getByLabel('器件名称',{exact:true}).fill('删除拒绝仍保留输入');await page.evaluate(before=>{window.__pc04a4aReferences={phase:'reject',before}},before);await page.getByRole('button',{name:'删除器件',exact:true}).click();return {stage,awaiting:'引用节点原生确认'}}
      const before=referenceState.before;
      if(referenceState.phase==='reject'){
        await page.getByText(/显式路径引用连线/).last().waitFor();eq(await page.getByLabel('器件名称',{exact:true}).inputValue(),'删除拒绝仍保留输入','拒绝丢局部输入');eq(await read(endpoint),before,'删除引用节点污染服务器');await shot('rejected');await closeNode();
        await choose('matrix-antenna');await page.evaluate(()=>{window.__pc04a4aReferences.phase='delete'});await page.getByRole('button',{name:'删除器件',exact:true}).click();return {stage,awaiting:'非引用节点原生确认'};
      }
      await nodeDialog().waitFor({state:'hidden'});const saved=await save();if(saved.nodes.some(n=>n.id==='matrix-antenna'))throw new Error('非引用节点未删除');await reload();if(await page.locator('.react-flow__node[data-id="matrix-antenna"]').count())throw new Error('删除重载恢复');await shot('deleted');evidence.push({before,saved});checks.push('显式路径引用删除拒绝、草稿/输入不丢；非引用节点正常删除并GET/reload');
    }else throw new Error(`未知阶段${stage}`);
    const result={stage,checks,exchanges,evidence,baseline:graph,final:await read(endpoint)};await page.evaluate(value=>{window.__pc04a4aTask3Result=value},result);return result;
  }
}
