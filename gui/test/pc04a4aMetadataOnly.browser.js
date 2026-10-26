// 真实UI→PATCH→GET；仅供tests.pc04a4a_browser_fixture的新库，全HAL Mock。
async page=>{
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,red=new URL(page.url()).searchParams.has('red');
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  const eq=(a,b,m)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(`${m}: ${JSON.stringify(a)} !== ${JSON.stringify(b)}`)};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('只许专用Mock环境');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04A4a标称甲');if(!lab)throw new Error('缺fixture');
  const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0],endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  const checks=[],exchanges=[];
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
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
  const legacy=page.getByRole('textbox',{name:'含旧PA标称的连线',exact:true});await legacy.fill('legacy-bad-pa');await page.locator('[role="option"][value="legacy-bad-pa"]').click();await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor();await page.getByLabel('旧PA标称增益来源说明',{exact:true}).fill('旧原值只改说明');await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});stored=await save();eq(stored.connections.find(e=>e.id==='legacy-bad-pa').pa_gain_db,'12','旧坏PA只改说明被重写');await reload();checks.push('旧坏PA metadata-only仍保留原字符串，不隐式清空');
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
