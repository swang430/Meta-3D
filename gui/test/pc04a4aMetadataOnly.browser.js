// 真实UI→PATCH→GET；仅供tests.pc04a4a_browser_fixture的新库，全HAL Mock。
async page=>{
  // 只通过现有模式/显示控件与真实画布点击；未归属模式的历史边不得补归属。
  function connectionModes(graph,id){
    return graph.operating_modes.filter(m=>(m.active_connections?.length?m.active_connections:graph.connections.filter(c=>c.modes?.includes(m.id)).map(c=>c.id)).includes(id));
  }
  async function showAuxiliary(){
    const expand=page.getByRole('button',{name:'展开辅助区',exact:true});
    if(await expand.isVisible())await expand.click();
  }
  async function openCanvasConnection(graph,id){
    await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});
    const modes=connectionModes(graph,id);
    if(!modes.length)throw new Error(`连线${id}未纳入任何模式；只能核对原值保形，不能自动补归属`);
    await showAuxiliary();
    const select=page.getByRole('textbox',{name:'操作模式',exact:true});
    const currentMode=await select.inputValue(),mode=modes.find(m=>m.name===currentMode)||modes[0];
    if(await select.inputValue()!==mode.name){await select.click();await page.getByRole('option',{name:mode.name,exact:true}).click()}
    await page.getByRole('button',{name:'定位全图',exact:true}).click();
    const point=await(await page.waitForFunction(id=>{
      const group=Array.from(document.querySelectorAll('.react-flow__edge,.topology-readonly-edge')).find(e=>e.getAttribute('data-id')===id);
      const path=group?.querySelector('.react-flow__edge-interaction')??group?.querySelector('path');
      const matrix=path?.getScreenCTM();if(!matrix)return null;
      for(const f of [.2,.3,.4,.6,.7,.8]){const p=path.getPointAtLength(path.getTotalLength()*f),x=matrix.a*p.x+matrix.c*p.y+matrix.e,y=matrix.b*p.x+matrix.d*p.y+matrix.f;
        if(document.elementFromPoint(x,y)?.closest('.react-flow__edge,.topology-readonly-edge')===group)return{x,y}}
      return null;
    },id)).jsonValue();
    await page.mouse.click(point.x,point.y);
    await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).getByText(id,{exact:true}).waitFor();
    return mode;
  }

  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,red=new URL(page.url()).searchParams.has('red');
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  const eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(`${m}: ${JSON.stringify(a)} !== ${JSON.stringify(b)}`)};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('只许专用Mock环境');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04A4a标称甲');if(!lab)throw new Error('缺fixture');
  const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0],endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const checks=[],exchanges=[];
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor();await showAuxiliary()};
  const reload=async()=>{await page.reload();await enter()};
  await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await reload();
  const nodeDialog=()=>page.getByRole('dialog',{name:'器件属性',exact:true});
  const choose=async id=>{await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});const list=page.getByRole('textbox',{name:'器件列表',exact:true});await list.click();await list.fill(id);await page.locator(`[role="option"][value="${id}"]`).click();await nodeDialog().waitFor()};
  const close=async()=>{await nodeDialog().getByRole('banner').getByRole('button').click();await nodeDialog().waitFor({state:'hidden'})};
  const apply=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await nodeDialog().waitFor({state:'hidden'})};
  const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;exchanges.push({status:r.status(),request:r.request().postDataJSON(),response:await r.json()});if(!r.ok())throw new Error(JSON.stringify(exchanges.at(-1)));await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();return read(endpoint)};
  const absent=(object,key,where)=>{if(Object.hasOwn(object,key))throw new Error(`${where} metadata-only补入数值键 ${key}=${JSON.stringify(object[key])}`)};
  const cases=[['pa','gain_db','PA标称增益','dB'],['matrix-pad','attenuation_db','标称衰减','dB'],['matrix-combiner','loss_db','标称插损','dB'],['probe1','gain_dbi','标称天线增益','dBi'],['matrix-antenna','gain_dbi','标称天线增益','dBi'],['ref','gain_dbi','标称天线增益','dBi']];
  for(const [id,key,label,unit] of red?cases.slice(0,1):cases){
    absent(graph.nodes.find(n=>n.id===id).params,key,`${id}fixture`);
    // 参考天线仅在校准模式显示；器件列表不能绕过模式可见性。
    if(id==='ref'){await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:'校准接线',exact:true}).click()}
    await choose(id);await page.getByLabel(`${label}来源说明`,{exact:true}).fill(`F1-${id}来源，非实测`);await apply();let stored=await save();
    absent(exchanges.at(-1).request.nodes.find(n=>n.id===id).params,key,`${id}PATCH`);absent(stored.nodes.find(n=>n.id===id).params,key,`${id}GET来源`);
    await reload();await choose(id);eq(await page.getByLabel(`${label} (${unit})`,{exact:true}).inputValue(),'','缺值重载');
    await page.getByLabel(`${label}适用起始频率 (MHz)`,{exact:true}).fill('2500');await page.getByLabel(`${label}适用结束频率 (MHz)`,{exact:true}).fill('2700');await apply();stored=await save();absent(stored.nodes.find(n=>n.id===id).params,key,`${id}GET频段`);
    await reload();await choose(id);eq(await page.getByLabel(`${label}适用结束频率 (MHz)`,{exact:true}).inputValue(),'2700','频段重载');await close();checks.push(`${id}:来源/频段PATCH GET reload均缺键`);
  }
  // 稀疏参考PA边通过真实曲线路径打开，不人为注入PA键以便定位。
  const edgeOpen=async()=>{
    await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:'校准接线',exact:true}).click();await page.getByRole('button',{name:'Fit View',exact:true}).click();
    const point=await(await page.waitForFunction(()=>{const el=document.querySelector('.react-flow__edge[data-id="reference-sparse"] .react-flow__edge-interaction');if(!el)return null;const m=el.getScreenCTM();for(const f of [.2,.3,.4,.6,.7,.8]){const p=el.getPointAtLength(el.getTotalLength()*f),x=m.a*p.x+m.c*p.y+m.e,y=m.b*p.x+m.d*p.y+m.f;if(document.elementFromPoint(x,y)?.closest('.react-flow__edge')===el.closest('.react-flow__edge'))return{x,y}}return null})).jsonValue();
    await page.mouse.click(point.x,point.y);await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).getByText('reference-sparse',{exact:true}).waitFor();
  };
  await edgeOpen();await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('参考边来源');await page.getByLabel('旧PA标称增益适用起始频率 (MHz)',{exact:true}).fill('2500');await page.getByLabel('旧PA标称增益适用结束频率 (MHz)',{exact:true}).fill('2700');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});let stored=await save();absent(stored.connections.find(e=>e.id==='reference-sparse'),'pa_gain_db','参考边GET');await reload();checks.push('参考PA边来源/频段不补数值键');
  await edgeOpen();await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).fill('1');await page.getByLabel('旧PA标称增益 (dB)',{exact:true}).fill('');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});stored=await save();eq(stored.connections.find(e=>e.id==='reference-sparse').pa_gain_db,null,'参考PA明确清空');await reload();checks.push('参考PA明确输入再清空仍存null');
  const unassigned=graph.connections.find(e=>e.id==='legacy-bad-pa'),sampleId='legacy-bad-pa-visible-sample';
  eq(connectionModes(graph,unassigned.id),[],'原历史边不应被初始化到模式');
  eq(stored.connections.find(e=>e.id===unassigned.id),unassigned,'无关保存改了未归属历史边的原值/缺键');
  eq(stored.operating_modes,graph.operating_modes,'无关保存改了模式');
  const sample=graph.connections.find(e=>e.id===sampleId);if(!sample||sample.pa_gain_db!=='12')throw new Error('缺少独立初始化且已归属模式的字符串PA样本');
  await openCanvasConnection(graph,sampleId);await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('旧原值只改说明');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});stored=await save();eq(stored.connections.find(e=>e.id===sampleId).pa_gain_db,'12','同形样本只改说明被重写');eq(stored.connections.find(e=>e.id===unassigned.id),unassigned,'编辑样本改了原未归属历史边');eq(stored.operating_modes,graph.operating_modes,'编辑样本改了模式');await reload();const reloadedLegacy=await read(endpoint);eq(reloadedLegacy.connections.find(e=>e.id===sampleId).pa_gain_db,'12','样本重载改了字符串');eq(reloadedLegacy.connections.find(e=>e.id===unassigned.id),unassigned,'重载改了未归属原件');eq(reloadedLegacy.operating_modes,graph.operating_modes,'重载改了模式');checks.push('未归属原件无关保存/重载原值缺键与模式不变；已归属同形样本metadata-only仍保留原字符串');
  // 取消局部说明不泄漏；真实离线失败不丢缺键草稿，恢复后重试仍保形。
  await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:'MIMO OTA 测试',exact:true}).click();
  await choose('pa');await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('不应保存');await close();await choose('pa');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'F1-pa来源，非实测','取消泄漏');
  await page.getByLabel('PA标称增益来源说明',{exact:true}).fill('失败重试保留来源');await apply();
  await page.context().setOffline(true);await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByText(/保存失败/).last().waitFor();await page.context().setOffline(false);
  await choose('pa');eq(await page.getByLabel('PA标称增益来源说明',{exact:true}).inputValue(),'失败重试保留来源','失败丢草稿');await close();stored=await save();absent(stored.nodes.find(n=>n.id==='pa').params,'gain_db','失败重试GET');checks.push('取消无泄漏；离线失败保留说明与缺键，重试成功');
  // 显式数值事件仍声明number/null；包括从缺键空框输入再清空。
  await reload();await choose('pa');await page.getByLabel('PA标称增益 (dB)',{exact:true}).fill('0');await apply();stored=await save();eq(stored.nodes.find(n=>n.id==='pa').params.gain_db,0,'明确0');await reload();await choose('pa');await page.getByLabel('PA标称增益 (dB)',{exact:true}).fill('');await apply();stored=await save();eq(stored.nodes.find(n=>n.id==='pa').params.gain_db,null,'明确清空');await reload();checks.push('明确0仍number，明确清空仍null');
  await page.screenshot({path:'output/playwright/pc04a4a-final-fix/final.png',fullPage:true,animations:'disabled'});
  const result={checks,exchanges,baseline:graph,final:await read(endpoint)};await page.evaluate(value=>window.__pc04a4aMetadataOnlyResult=value,result);return result;
}
