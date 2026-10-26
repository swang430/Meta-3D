// playwright-cli run-code --filename: 真实HTTP，不mock API。
async page=>{
  const origin=new URL(page.url()).origin, api=`${origin}/api/v1`,stage=new URL(page.url()).searchParams.get('portStage');
  page.setDefaultTimeout(12000);
  await page.setViewportSize({width:1800,height:1100});
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许全Mock');
  const lab=(await read('/lab-profiles')).find(l=>l.name==='PC04A4b端口甲');
  if(!lab)throw new Error('缺少专用fixture');
  const graph=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
  if(!graph.nodes.some(n=>n.id==='amplifier'&&n.params.ports.includes('in')))throw new Error('缺少端口样本');
  await page.goto(origin);
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await page.locator('.react-flow').first().waitFor();
  if(stage==='legacy-source-input'||stage==='legacy-target-output'){
    const edge=graph.connections.find(e=>e.id===stage);if(!edge)throw new Error('缺少专用历史方向冲突fixture');
    const before=JSON.stringify(graph),source=graph.nodes.find(n=>n.id===edge.source),target=graph.nodes.find(n=>n.id===edge.target);
    await page.locator(`.react-flow__node[data-id="${edge.source}"] .react-flow__handle[data-handleid="P"]`).waitFor();
    await page.locator(`.react-flow__node[data-id="${edge.target}"] .react-flow__handle[data-handleid="P"]`).waitFor();
    await page.getByRole('button',{name:'Fit View',exact:true}).click();
    const path=page.locator(`.react-flow__edge[data-id="${stage}"] .react-flow__edge-path, .topology-readonly-edge[data-id="${stage}"] .react-flow__edge-path`);
    const available=await path.count();
    await page.screenshot({path:`output/playwright/pc04a4b-${stage}-${available?'green':'red'}.png`,fullPage:true,animations:'disabled'});
    // 先确认原节点/同ID可见handle加载；RED只可发生在旧边path缺失。
    await path.waitFor({state:'attached'});
    await page.getByText(/旧接线不合法或端口未声明/).first().waitFor();
    const settle=()=>page.waitForFunction(()=>new Promise(resolve=>{let same=0,last='';const tick=()=>{const now=document.querySelector('.react-flow__viewport')?.getAttribute('style');same=now===last?same+1:0;last=now;if(same>5)resolve(true);else requestAnimationFrame(tick)};tick()}));
    const verifyAnchors=async()=>{
      await settle();
      const ends=await path.evaluate(p=>{const m=p.getScreenCTM(),point=length=>{const v=p.getPointAtLength(length);return{x:m.a*v.x+m.c*v.y+m.e,y:m.b*v.x+m.d*v.y+m.f}};return[point(0),point(p.getTotalLength())]});
      for(const [index,node] of [source,target].entries()){
        const kind=node.params.port_directions.P==='input'?'target':'source';
        const handles=page.locator(`.react-flow__node[data-id="${node.id}"] .react-flow__handle[data-handleid="P"]`);
        if(await handles.count()!==1)throw new Error('旧几何增加了同ID handle');
        const box=await handles.boundingBox(),x=kind==='target'?box.x:box.x+box.width,y=box.y+box.height/2;
        if(Math.hypot(ends[index].x-x,ends[index].y-y)>3)throw new Error(`只读边未对齐可见端点：${JSON.stringify({ends,index,box})}`);
      }
      return ends;
    };
    const originalAnchors=await verifyAnchors();
    await page.getByRole('button',{name:'Zoom In',exact:true}).click();await verifyAnchors();
    // 全图缩放后下排历史样本可能在裁剪区外；用真实画布平移带入视口再拖节点。
    const frame=await page.locator('.react-flow').first().boundingBox(),currentBox=await page.locator(`.react-flow__node[data-id="${edge.source}"]`).boundingBox();
    const dy=Math.max(-frame.height/2,Math.min(frame.height/2,frame.y+frame.height/2-currentBox.y-currentBox.height/2));
    const panY=frame.y+(dy<0?frame.height-25:25);
    const oldViewport=await page.locator('.react-flow__viewport').getAttribute('style');
    await page.mouse.move(frame.x+60,panY);await page.mouse.down();await page.mouse.move(frame.x+60,panY+dy,{steps:12});await page.mouse.up();
    if(Math.abs(dy)>1)await page.waitForFunction(old=>document.querySelector('.react-flow__viewport')?.getAttribute('style')!==old,oldViewport);
    await verifyAnchors();
    const nodeBox=await page.locator(`.react-flow__node[data-id="${edge.source}"]`).boundingBox(),oldPath=await path.getAttribute('d');
    await page.mouse.move(nodeBox.x+nodeBox.width/2,nodeBox.y+15);await page.mouse.down();await page.mouse.move(nodeBox.x+nodeBox.width/2+50,nodeBox.y+40,{steps:12});await page.mouse.up();
    await page.waitForFunction(({id,old})=>document.querySelector(`.topology-readonly-edge[data-id="${id}"] .react-flow__edge-path`)?.getAttribute('d')!==old,{id:stage,old:oldPath});
    const movedAnchors=await verifyAnchors();
    const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
    if(JSON.stringify(await read(endpoint))!==before)throw new Error('只读渲染改写了存储图');
    const middle=await path.evaluate(p=>{const v=p.getPointAtLength(p.getTotalLength()/2),m=p.getScreenCTM();return{x:m.a*v.x+m.c*v.y+m.e,y:m.b*v.x+m.d*v.y+m.f}});
    await page.mouse.click(middle.x,middle.y);await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor();
    await page.getByText(stage,{exact:true}).waitFor();
    await page.getByRole('button',{name:'取消',exact:true}).click();
    await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});
    const normalMiddle=await page.locator('.react-flow__edge[data-id="fixed-h"] .react-flow__edge-path').evaluate(p=>{const v=p.getPointAtLength(p.getTotalLength()/2),m=p.getScreenCTM();return{x:m.a*v.x+m.c*v.y+m.e,y:m.b*v.x+m.d*v.y+m.f}});
    await page.mouse.click(normalMiddle.x,normalMiddle.y);
    await page.getByRole('dialog',{name:'连线参数编辑',exact:true}).waitFor();await page.getByText('fixed-h',{exact:true}).waitFor();
    await page.screenshot({path:`output/playwright/pc04a4b-${stage}-geometry-green.png`,fullPage:true,animations:'disabled'});
    return {stage,source,target,edge,path:await path.getAttribute('d'),originalAnchors,movedAnchors,readOnly:true,unchangedGet:true,normalEdgeSelectable:true};
  }
  await page.getByRole('textbox',{name:'器件列表',exact:true}).fill('amplifier');
  await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').click();
  const drawer=page.getByRole('dialog',{name:'器件属性',exact:true});
  await drawer.waitFor();
  await page.getByLabel('器件名称',{exact:true}).waitFor();
  const dom=await drawer.innerText();
  const implemented=await page.getByRole('textbox',{name:'端口角色 in',exact:true}).count();
  await page.screenshot({path:`output/playwright/pc04a4b-${implemented?'green':'red'}-port-drawer.png`,fullPage:true,animations:'disabled'});
  console.log(JSON.stringify({stage:'真实GET、页面及原器件抽屉已加载',labId:lab.id,topologyId:graph.id,dom}));
  await page.getByRole('textbox',{name:'端口角色 in',exact:true}).waitFor({state:'visible'});
  console.log('GREEN: 按原端口ID定位的端口角色下拉可见');
  if(stage!=='targeted')return {stage:'控件可见GREEN',labId:lab.id,topologyId:graph.id,dom};
  const endpoint=`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`,checks=[],writes=[];
  const eq=(a,b,message)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw new Error(`${message}: ${JSON.stringify(a)}`)};
  const dialog=()=>page.getByRole('dialog',{name:'器件属性',exact:true});
  const close=async()=>{await dialog().getByRole('banner').getByRole('button').click();await dialog().waitFor({state:'hidden'})};
  const choose=async id=>{await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});const list=page.getByRole('textbox',{name:'器件列表',exact:true});await list.fill(id);await page.getByRole('listbox',{name:'器件列表',exact:true}).getByRole('option').click();await dialog().waitFor()};
  const role=async(id,value,prefix='端口角色')=>{await page.getByRole('textbox',{name:`${prefix} ${id}`,exact:true}).click();await page.getByRole('option',{name:value,exact:true}).click()};
  const apply=async()=>{await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await dialog().waitFor({state:'hidden'})};
  const save=async(expected=200)=>{const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const response=await pending;const body=await response.json();writes.push({request:response.request().postDataJSON(),status:response.status(),body});eq(response.status(),expected,'保存状态错误');await page.getByTestId('topology-save-stage').filter({hasText:expected===200?'拓扑已保存到服务器':'拓扑保存失败；草稿未保存'}).waitFor();return body};
  // 取消只保留已应用草稿；打开与角色改回原值不补unknown map。
  const before=await read(endpoint);
  await role('in','输出');await close();await choose('amplifier');
  eq(await page.getByRole('textbox',{name:'端口角色 in',exact:true}).inputValue(),'方向未声明，非双向能力','取消泄漏角色');
  await role('in','输出');await role('in','方向未声明，非双向能力');
  await page.getByRole('button',{name:'恢复原端口声明',exact:true}).click();await apply();
  const untouched=await save();eq(untouched.nodes.find(n=>n.id==='amplifier').params,before.nodes.find(n=>n.id==='amplifier').params,'恢复注入方向map');
  await choose('amplifier');await role('in','输出');await apply();
  const handle=page.locator('.react-flow__node[data-id="amplifier"]');
  eq(await handle.locator('.react-flow__handle.source[data-handleid="in"]').count(),1,'输出source丢失');
  eq(await handle.locator('.react-flow__handle.target[data-handleid="in"]').count(),0,'隐藏旧handle共存');
  const saved=await save();eq(saved.nodes.find(n=>n.id==='amplifier').params.port_directions,{in:'output'},'角色不落库');
  eq(saved.connections,before.connections,'角色编辑改了边');checks.push('打开/取消/恢复/应用、同ID单向绘制、PATCH和扩展参数保形');
  // BSE专用角色是唯一运行语义；通用unknown不能盖过DL/UL。
  await choose('communication_tester');
  eq(await page.getByRole('textbox',{name:'BSE角色 RF5',exact:true}).inputValue(),'下行 dl','RF5未从原port_roles读取');
  await role('RF5','上行 ul','BSE角色');await apply();
  const bse=page.locator('.react-flow__node[data-id="communication_tester"]');
  eq(await bse.locator('.react-flow__handle.target[data-handleid="RF5"]').count(),1,'BSE UL没有target');
  eq(await bse.locator('.react-flow__handle.source[data-handleid="RF5"]').count(),0,'BSE UL残留source');
  const bseSaved=await save();eq(bseSaved.nodes.find(n=>n.id==='communication_tester').params.port_roles,{RF5:'ul'},'BSE写入另一个map');checks.push('BSE dl→ul真实保存，未知DL1不按名字推导');
  // 全模式引用：固定边虽非当前选中的模式也不能删除端口或反接。
  await page.getByRole('button',{name:'校准接线',exact:true}).click();
  await choose('ce_port');await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('in');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await dialog().waitFor();
  await page.getByText(/端口仍有连线 fixed-v/).waitFor();await close();
  eq((await read(endpoint)).connections,bseSaved.connections,'拒绝端口移除改变服务器');checks.push('仍被引用端口移除在应用前拒绝，原图保持');
  // 新节点没确认端口触发真实422；失败保留草稿，填完后重试。
  await page.getByRole('button',{name:'添加器件',exact:true}).click();
  const newId=(await dialog().locator('p').first().innerText()).trim();await close();
  const rejected=await save(422);if(!JSON.stringify(rejected).includes(newId))throw new Error('422没有节点定位');
  await choose(newId);await page.getByRole('textbox',{name:'声明端口',exact:true}).fill('A, B');await apply();
  const retry=await save();eq(retry.nodes.find(n=>n.id===newId).params.ports,['A','B'],'422丢草稿/重试错误');checks.push('真实422节点定位、草稿保留及更正后重试');
  await choose('amplifier');await role('out','双向声明');await apply();
  const other=(await read('/lab-profiles')).find(l=>l.name==='PC04A4b端口乙');
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();
  eq(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')),lab.id,'dirty跨Lab未拒绝');
  await page.context().setOffline(true);
  try{await page.getByRole('button',{name:'保存拓扑',exact:true}).click();await page.getByTestId('topology-save-stage').filter({hasText:'拓扑保存失败；草稿未保存'}).waitFor()}finally{await page.context().setOffline(false)}
  await choose('amplifier');eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),'双向声明','网络失败丢草稿');await close();await save();
  await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await choose('amplifier');
  eq(await page.getByRole('textbox',{name:'端口角色 out',exact:true}).inputValue(),'双向声明','重载未恢复');
  checks.push('离线失败不解丢草稿、在线重试真实保存和重载恢复');
  await page.screenshot({path:'output/playwright/pc04a4b-targeted-green.png',fullPage:true,animations:'disabled'});
  await close();await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:other.name}).click();
  const otherGraph=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
  await page.getByText(otherGraph.name,{exact:true}).waitFor();
  eq(await page.locator('.react-flow__node[data-id="amplifier"]').count(),0,'清洁切Lab泄漏节点');
  checks.push('dirty切Lab拒绝、清洁切Lab清除抽屉及声明意图');
  return {checks,writes,after:await read(endpoint)};
}
