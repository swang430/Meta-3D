// 真实浏览器与隔离API；不截断网络，不访问用户实验室。
export async function assertNoLegacySelector(page) {
  await page.getByRole('textbox', {name:'器件列表', exact:true}).waitFor();
  if (await page.getByRole('textbox', {name:'含旧PA标称的连线', exact:true}).count()) {
    throw Error('旧PA专用下拉框仍存在');
  }
}

export async function seedOrdinaryEditing(page, {base, labId, sourceId}) {
  if (base !== 'http://127.0.0.1:18513') throw Error('仅允许隔离服务');
  const labs = await (await page.request.get(`${base}/api/v1/lab-profiles`)).json();
  if (!labs.some(lab=>lab.id===labId&&lab.name==='PC13完整模拟隔离实验室')) throw Error('隔离实验室不匹配');
  const source = await (await page.request.get(`${base}/api/v1/switch-topologies/${sourceId}?lab_profile_id=${labId}`)).json();
  const rows = [];
  for (const legacy of [false,true]) {
    const nodes = [
      {id:'ce',type:'ce_port',label:'模拟输出',position:{x:40,y:100},params:{ports:['out'],port_directions:{out:'output'},ce_port:'B1'}},
      {id:'probe',type:'probe',label:'测试探头',position:{x:540,y:100},params:{ports:['in'],port_directions:{in:'input'},probe_id:0,polarization:'V',rf_path_selection:{connection_ids:['test-edge'],switch_mappings:[]}}},
    ];
    const connections = [{id:'test-edge',source:'ce',source_pin:'out',target:'probe',target_pin:'in',modes:['mimo_ota'],cable_loss_db:1.25,...(legacy?{pa_gain_db:12}: {})}];
    const response = await page.request.post(`${base}/api/v1/switch-topologies`,{data:{
      lab_profile_id:labId,switch_category_id:source.switch_category_id,
      name:`PC12隔离${legacy?'有旧值':'无旧值'}-${Date.now()}`,is_active:false,is_default:false,
      nodes,connections,operating_modes:[{id:'mimo_ota',name:'测试接线',active_connections:['test-edge']}],
    }});
    if(response.status()!==201) throw Error(await response.text());
    rows.push({legacy,graph:await response.json()});
  }
  return rows;
}

export async function verifyOrdinaryEditing(page, {base,labId,graph,legacy}) {
  const eq=(a,b,label)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(label)};
  const endpoint=`${base}/api/v1/switch-topologies/${graph.id}?lab_profile_id=${labId}`;
  const get=async()=>{const r=await page.request.get(endpoint);if(!r.ok())throw Error(await r.text());return r.json()};
  const enter=async()=>{
    await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
    await page.getByRole('option').filter({hasText:'PC13完整模拟隔离实验室'}).click();
    await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  };
  const choose=async()=>{
    await page.reload();
    await enter();
    const library=page.getByRole('textbox',{name:'拓扑库（仅编辑选择）',exact:true});
    await page.getByRole('textbox',{name:'器件列表',exact:true}).waitFor();
    await library.click();await library.fill(graph.name);await page.getByRole('option').filter({hasText:graph.name}).click();
    await page.getByText(graph.name,{exact:true}).waitFor();
  };
  await choose();await assertNoLegacySelector(page);
  // 读取SVG仅用于确定实际鼠标点击位置，不调用React内部状态或拦截响应。
  await page.locator('.react-flow__edge[data-id="test-edge"] .react-flow__edge-interaction').scrollIntoViewIfNeeded();
  const point=await page.locator('.react-flow__edge[data-id="test-edge"] .react-flow__edge-interaction').evaluate(path=>{
    const m=path.getScreenCTM();
    for(const fraction of [.2,.3,.4,.6,.7,.8]){
      const p=path.getPointAtLength(path.getTotalLength()*fraction),q=new DOMPoint(p.x,p.y).matrixTransform(m);
      if(document.elementFromPoint(q.x,q.y)?.closest('.react-flow__edge')===path.closest('.react-flow__edge'))return{x:q.x,y:q.y};
    }
    return null;
  });
  if(!point)throw Error('普通连线不可点击');
  await page.mouse.click(point.x,point.y);
  const dialog=page.getByRole('dialog',{name:'连线参数编辑',exact:true});await dialog.waitFor();
  await page.getByLabel('标称电缆损耗 (dB)',{exact:true}).fill('1.75');
  await page.getByRole('button',{name:'应用修改',exact:true}).click();await dialog.waitFor({state:'hidden'});
  const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const savedResponse=await pending;
  if(!savedResponse.ok())throw Error(await savedResponse.text());
  await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();
  const saved=await get();eq(saved.nodes,graph.nodes,'普通边编辑改动节点');eq(saved.operating_modes,graph.operating_modes,'普通边编辑改动模式');
  eq(saved.connections[0].cable_loss_db,1.75,'损耗未保存');
  eq(saved.connections[0].pa_gain_db,graph.connections[0].pa_gain_db,'旧值或缺键被改写');
  await choose();await assertNoLegacySelector(page);
  const reloaded=await get();eq(reloaded.connections,saved.connections,'重载与保存不一致');
  await page.getByRole('button',{name:'保存修订历史',exact:true}).click();
  const history=page.getByRole('dialog',{name:'保存修订历史',exact:true});await history.waitFor();
  await history.getByRole('button',{name:/^r1 · create/}).click();
  await history.getByRole('button',{name:'预览恢复差异',exact:true}).click();
  await page.getByTestId('topology-restore-preview').waitFor();
  await history.getByRole('checkbox',{name:'确认将此历史声明恢复为新的保存修订',exact:true}).check();
  const restoredResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes(`/switch-topologies/${graph.id}/restore`));
  await page.getByTestId('topology-restore-confirm').click();const rr=await restoredResponse;if(!rr.ok())throw Error(await rr.text());
  await history.waitFor({state:'hidden'});const restored=await get();
  eq(restored.connections[0].cable_loss_db,1.25,'历史恢复未生效');eq(restored.connections[0].pa_gain_db,graph.connections[0].pa_gain_db,'恢复改写旧值或缺键');
  eq(restored.nodes,graph.nodes,'恢复改写节点');eq(restored.operating_modes,graph.operating_modes,'恢复改写模式');
  if(restored.revision<=saved.revision)throw Error('恢复未生成新修订');
  await assertNoLegacySelector(page);
  return {legacy,id:graph.id,savedRevision:saved.revision,restoredRevision:restored.revision,oldValue:restored.connections[0].pa_gain_db??null};
}
