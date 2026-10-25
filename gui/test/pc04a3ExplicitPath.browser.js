// Task2定点真实交互；完整19类矩阵由后续验收补齐，不伪造draft或响应。
async page=>{
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,checks=[];
  page.setDefaultTimeout(12000);
  await page.setViewportSize({width:1800,height:1100});
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许全Mock');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04自动采集甲');
  const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
  const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  // 每次重试只经真实API重置本专属测试库甲图，不改页面内draft或拦截响应。
  const other=(await read('/lab-profiles')).find(l=>l.name==='PC04自动采集乙');
  const baseline=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
  const reset=await page.request.patch(`${api}${endpoint}`,{data:{nodes:baseline.nodes,connections:baseline.connections,operating_modes:baseline.operating_modes}});
  if(!reset.ok())throw new Error(await reset.text());
  const enter=async()=>{await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor()};
  await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();await enter();
  const choose=async id=>{await page.getByRole('textbox',{name:'器件列表',exact:true}).fill(id);await page.getByRole('option').filter({hasText:id}).click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor()};
  const closeNode=async()=>{await page.getByRole('dialog',{name:'器件属性',exact:true}).getByRole('banner').getByRole('button').click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor({state:'hidden'})};
  const clickCurve=async id=>{
    await page.getByRole('button',{name:'Fit View',exact:true}).click();
    await page.evaluate(()=>new Promise(resolve=>{let previous='',stable=0;const frame=()=>{const current=document.querySelector('.react-flow__viewport')?.getAttribute('style');stable=current===previous?stable+1:0;previous=current;if(stable>=5)resolve(true);else requestAnimationFrame(frame)};requestAnimationFrame(frame)}));
    const located=await page.waitForFunction(id=>{
      const el=document.querySelector(`.react-flow__edge[data-id="${id}"] .react-flow__edge-interaction`);if(!el)return null;
      const m=el.getScreenCTM();for(const f of [.2,.3,.1,.4,.6,.7,.8,.9]){const p=el.getPointAtLength(el.getTotalLength()*f),x=m.a*p.x+m.c*p.y+m.e,y=m.b*p.x+m.d*p.y+m.f;
        if(document.elementFromPoint(x,y)?.closest('.react-flow__edge')===el.closest('.react-flow__edge'))return{x,y}}return null;
    },id);const p=await located.jsonValue();await page.mouse.click(p.x,p.y);
  };
  const save=async()=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await pending;if(!r.ok())throw new Error(await r.text());await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor()};
  await choose('ce1');await page.getByLabel('声明端口',{exact:true}).fill('out, alt');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await save();
  await clickCurve('fixed-v');await page.getByRole('textbox',{name:'源端口',exact:true}).click();await page.getByRole('option',{name:'alt',exact:true}).click();
  await page.getByRole('button',{name:'应用修改',exact:true}).click();await page.getByText(/显式路径引用连线 fixed-v/).last().waitFor();
  if(await page.getByRole('textbox',{name:'源端口',exact:true}).inputValue()!=='alt')throw new Error('拒绝后输入未保留');
  await page.getByRole('button',{name:'删除连线',exact:true}).click();await page.getByText(/显式路径引用连线 fixed-v/).last().waitFor();
  await page.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
  const intact=await read(endpoint);if(intact.connections.find(e=>e.id==='fixed-v')?.source_pin!=='out'||!intact.nodes.some(n=>n.id==='ce1'))throw new Error('引用拒绝后服务器改变');
  checks.push('被引用边改pin/删除明确拒绝；抽屉输入/旧草稿与服务器保持');
  await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:'线缆',exact:true}).click();
  await page.getByRole('button',{name:'添加器件',exact:true}).click();await page.getByLabel('器件名称',{exact:true}).fill('PC04A3双端线缆');
  if(await page.getByLabel('声明端口',{exact:true}).inputValue()!=='A, B')throw new Error('A/B建议缺失');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  const cableNode=page.locator('.react-flow__node').filter({has:page.getByText('PC04A3双端线缆',{exact:true})});await cableNode.waitFor();
  const cableId=await cableNode.getAttribute('data-id');
  const box=await cableNode.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+18);await page.mouse.down();await page.mouse.move(box.x+box.width/2-220,box.y+18+100,{steps:12});await page.mouse.up();
  await page.getByRole('button',{name:'Fit View',exact:true}).click();
  await page.evaluate(()=>new Promise(resolve=>{let previous='',stable=0;const frame=()=>{const current=document.querySelector('.react-flow__viewport')?.getAttribute('style');stable=current===previous?stable+1:0;previous=current;if(stable>=5)resolve(true);else requestAnimationFrame(frame)};requestAnimationFrame(frame)}));
  const connect=async(source,pin,target,tpin)=>{
    const count=await page.locator('.react-flow__edge').count();
    const a=await page.locator(`.react-flow__node[data-id="${source}"] .react-flow__handle.source[data-handleid="${pin}"]`).boundingBox();
    const b=await page.locator(`.react-flow__node[data-id="${target}"] .react-flow__handle.target[data-handleid="${tpin}"]`).boundingBox();
    if(!a||!b)throw new Error('已声明物理端口不可拖线');await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:20});await page.mouse.up();
    await page.waitForFunction(count=>document.querySelectorAll('.react-flow__edge').length>count,count);
  };
  await connect('ce1','out',cableId,'A');await connect(cableId,'B','probe1','in');await save();
  let saved=await read(endpoint);const first=saved.connections.find(e=>e.source==='ce1'&&e.target===cableId),last=saved.connections.find(e=>e.source===cableId&&e.target==='probe1');
  if(!first||!last)throw new Error('两条真实替代边未保存');
  if(first.calibrated_loss_db!=null||last.calibrated_loss_db!=null)throw new Error('新边继承旧校准');
  await clickCurve(last.id);await page.getByLabel('标称电缆损耗 (dB)',{exact:true}).fill('2');await page.getByRole('button',{name:'应用修改',exact:true}).click();
  await choose('probe1');const pathInput=page.getByRole('textbox',{name:'显式RF路径：按CE→探头顺序选择连线',exact:true});await pathInput.press('Backspace');
  for(const id of [first.id,last.id]){await pathInput.press('ArrowDown');await page.getByRole('option').filter({hasText:id}).click()}
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await clickCurve('fixed-v');await page.getByRole('button',{name:'删除连线',exact:true}).click();await save();
  saved=await read(endpoint);const cable=saved.nodes.find(n=>n.id===cableId),incident=saved.connections.filter(e=>e.source===cableId||e.target===cableId);
  if(JSON.stringify(cable?.params.ports)!=='["A","B"]')throw new Error('双端声明未真实保存');
  if(incident.length!==2||incident.reduce((sum,e)=>sum+(e.cable_loss_db??0),0)!==2)throw new Error('物理线缆损耗未保持单一归属');
  if(saved.connections.some(e=>e.id==='fixed-v'))throw new Error('旧边仍存在');
  if(JSON.stringify(saved.nodes.find(n=>n.id==='probe1').params.rf_path_selection.connection_ids)!==JSON.stringify([first.id,last.id]))throw new Error('替代声明未持久化');
  const routes=await read(`/lab-profiles/${lab.id}/route-calibration-paths?topology_id=${graph.id}&operating_mode=mimo_ota`);
  if(!routes.some(r=>r.chain_id===last.id&&r.connection_ids.includes(first.id)))throw new Error('服务器未返回新路径');
  await page.reload();await enter();await page.locator(`.react-flow__node[data-id="${cableId}"]`).waitFor();
  checks.push('添加A/B线缆→真实拖两边→显式重新声明→删除旧边→PATCH/GET/reload，损耗2而非4且不复制校准');
  await page.screenshot({path:'output/playwright/pc04a3/task2-explicit-path.png',fullPage:true});
  const result={checks,labId:lab.id,topologyId:graph.id,cableId,connectionIds:[first.id,last.id],boundary:'定点交互，非19类完整矩阵/非现场'};
  await page.evaluate(result=>{window.__pc04a3Task2Result=result},result);console.log(JSON.stringify(result));return result;
}
