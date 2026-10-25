// 独立临时SQLite、全HAL Mock、真实API；恢复流程也在Task2默认bootstrap新库回归。
async page=>{
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,checks=[];
  page.setDefaultTimeout(12000);
  await page.setViewportSize({width:1800,height:1100});
  const read=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw new Error(await r.text());return r.json()};
  if((await read('/instruments/hal/status')).mode!=='mock')throw new Error('仅允许独立全Mock环境');
  const labs=await read('/lab-profiles');
  const lab=labs.find(l=>l.name==='PC04自动采集甲')||labs.find(l=>l.name==='PC04A3 Task1');
  if(!lab)throw new Error('请先在独立数据库建立PC04A3 Task1最小fixture');
  const topologies=(await read(`/switch-topologies?lab_profile_id=${lab.id}`)).items;
  let topology=topologies.find(t=>t.name==='PC04A3恢复编辑')||topologies.find(t=>t.chamber_id===lab.chamber_config_id);
  if(!topology)throw new Error('最小拓扑fixture缺失');
  const endpoint=`/switch-topologies/${topology.id}?lab_profile_id=${lab.id}`;
  if(lab.name==='PC04自动采集甲'){
    const other=labs.find(l=>l.name==='PC04自动采集乙');
    const baseline=(await read(`/switch-topologies?lab_profile_id=${other.id}`)).items[0];
    const reset=await page.request.patch(`${api}${endpoint}`,{data:{nodes:baseline.nodes,connections:baseline.connections,operating_modes:baseline.operating_modes}});
    if(!reset.ok())throw new Error(await reset.text());
    topology=await reset.json();
  }
  const stored=()=>read(endpoint);
  const find=(graph,id)=>graph.nodes.find(n=>n.id===id);
  const requireEqual=(got,want,message)=>{if(JSON.stringify(got)!==JSON.stringify(want))throw new Error(`${message}: ${JSON.stringify(got)}`)};
  const enter=async()=>{
    await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
    await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
    await page.locator('.react-flow').first().waitFor();
  };
  await page.goto(origin);
  await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
  await page.reload();await enter();
  const list=page.getByRole('textbox',{name:'器件列表',exact:true});
  await list.waitFor(); // 首次RED：旧版本无任何恢复隐藏器件的入口。
  const choose=async id=>{await list.fill(id);await page.getByRole('option').filter({hasText:id}).click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor()};
  const close=async()=>{await page.getByRole('dialog',{name:'器件属性',exact:true}).getByRole('banner').getByRole('button').click();await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor({state:'hidden'})};
  await choose('hidden-normal');
  requireEqual(await page.getByLabel('声明端口',{exact:true}).inputValue(),'in, out','隐藏器件声明端口未加载');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByText(/至少选择一个有效显示模式/).last().waitFor();
  await page.getByRole('dialog',{name:'器件属性',exact:true}).waitFor();
  requireEqual(find(await stored(),'hidden-normal').params.visible_modes,[],'失败应用改变服务器');
  await page.getByRole('dialog',{name:'器件属性',exact:true}).locator('.mantine-MultiSelect-input').click();
  await page.getByRole('option',{name:'MIMO OTA 测试',exact:true}).click();
  await page.keyboard.press('Escape');
  await close();
  await choose('hidden-normal');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByText(/至少选择一个有效显示模式/).last().waitFor();
  await page.getByRole('dialog',{name:'器件属性',exact:true}).locator('.mantine-MultiSelect-input').click();
  await page.getByRole('option',{name:'MIMO OTA 测试',exact:true}).click();await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.locator('.react-flow__node[data-id="hidden-normal"]').waitFor();
  requireEqual(find(await stored(),'hidden-normal').params.visible_modes,[],'未保存恢复提前写服务器');
  checks.push('普通隐藏器件列表可达；空模式拒绝保留输入；选择/关闭不应用；应用仅改同一草稿');
  await choose('hidden-calibration');
  if(!await page.getByRole('textbox',{name:'显示模式',exact:true}).isDisabled())throw new Error('校准器件模式可被扩域');
  await page.getByRole('button',{name:'恢复到校准接线模式',exact:true}).click();await close();
  await choose('hidden-calibration');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByText(/至少选择一个有效显示模式/).last().waitFor();
  await page.getByRole('button',{name:'恢复到校准接线模式',exact:true}).click();
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  if(await page.locator('.react-flow__node[data-id="hidden-calibration"]').count())throw new Error('校准器件进入正常模式');
  checks.push('校准隐藏器件同抽屉恢复；按钮只改表单，应用后仍不进入正常模式');
  const save=async()=>{
    const response=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${topology.id}`));
    await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
    const r=await response;if(!r.ok())throw new Error(await r.text());
    await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();
  };
  await save();await page.reload();await enter();
  const recovered=await stored();
  for(const [id,modes] of [['hidden-normal',['mimo_ota']],['hidden-calibration',['calibration']]]){
    requireEqual(find(recovered,id).params.visible_modes,modes,'恢复模式未持久化');
    requireEqual(find(recovered,id).params.unknown,{keep:1},'未知参数丢失');
    requireEqual(find(recovered,id).position,find(topology,id).position,'隐藏器件位置改变');
  }
  await page.locator('.react-flow__node[data-id="hidden-normal"]').waitFor();
  await choose('hidden-normal');
  await page.getByRole('dialog',{name:'器件属性',exact:true}).locator('.mantine-MultiSelect-input').click();
  await page.getByRole('textbox',{name:'显示模式',exact:true}).press('Backspace');await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByText(/至少选择一个有效显示模式/).last().waitFor();
  await close();await page.locator('.react-flow__node[data-id="hidden-normal"]').waitFor();
  await page.getByRole('button',{name:'校准接线',exact:true}).click();
  await page.locator('.react-flow__node[data-id="hidden-calibration"]').waitFor();
  checks.push('保存真实PATCH/GET与刷新后恢复，未知参数及原坐标保持，校准仅校准模式');
  const add=async(type,label,ports)=>{
    await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:type,exact:true}).click();
    await page.getByRole('button',{name:'添加器件',exact:true}).click();
    requireEqual(await page.getByLabel('声明端口',{exact:true}).inputValue(),'A, B','双端建议缺失');
    await page.getByLabel('器件名称',{exact:true}).fill(label);
    await page.getByLabel('声明端口',{exact:true}).fill(ports);
    await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
    const node=page.locator('.react-flow__node').filter({has:page.getByText(label,{exact:true})});await node.waitFor();
    for(const pin of ports.split(', ')){
      if(await node.locator(`.topology-declared-handle[data-handleid="${pin}"]`).count()!==2)throw new Error('同一物理端口未保留左右接点');
      await node.getByText(`${pin} · 连入`,{exact:true}).waitFor();await node.getByText(`${pin} · 连出`,{exact:true}).waitFor();
    }
  };
  await add('线缆','普通双端线缆','端甲, 端乙');
  await add('校准接收线缆','接收双端线缆','RX-A, RX-B');
  await page.getByRole('textbox',{name:'新增器件类型',exact:true}).click();await page.getByRole('option',{name:'信道仿真器',exact:true}).click();
  await page.getByRole('button',{name:'添加器件',exact:true}).click();
  requireEqual(await page.getByLabel('声明端口',{exact:true}).inputValue(),'','新增仪器猜测端口');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await page.getByText('请填写器件名称，以及不重复的端口名称',{exact:true}).waitFor();
  await page.getByLabel('器件名称',{exact:true}).fill('空端口仪器');await page.getByLabel('声明端口',{exact:true}).fill('实际核对端');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await save();
  const final=await stored();
  requireEqual(final.nodes.find(n=>n.label==='普通双端线缆').params.ports,['端甲','端乙'],'普通线缆修改未保存');
  requireEqual(final.nodes.find(n=>n.label==='接收双端线缆').params.ports,['RX-A','RX-B'],'接收线缆修改未保存');
  checks.push('两类线缆A/B仅可修改建议、同名左右物理端口标签；新增仪器端口保持空且应用拒绝');
  // 模拟历史图缺少校准模式：只能按现有入口创建，再显式恢复，不自动扩域。
  const reset=await page.request.patch(`${api}${endpoint}`,{data:{
    nodes:final.nodes.map(n=>n.id==='hidden-calibration'?{...n,params:{...n.params,visible_modes:[]}}:n),
    operating_modes:final.operating_modes.filter(m=>m.id!=='calibration'),
  }});
  if(!reset.ok())throw new Error(await reset.text());
  await page.reload();await enter();await choose('hidden-calibration');
  await page.getByText(/请先关闭抽屉，点击“校准接线”创建模式/).waitFor();
  if(await page.getByRole('button',{name:'恢复到校准接线模式',exact:true}).count())throw new Error('缺模式仍自动恢复');
  await close();await page.getByRole('button',{name:'校准接线',exact:true}).click();
  await choose('hidden-calibration');await page.getByRole('button',{name:'恢复到校准接线模式',exact:true}).click();
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();await save();
  requireEqual(find(await stored(),'hidden-calibration').params.visible_modes,['calibration'],'缺校准模式恢复扩域');
  checks.push('清空已恢复节点模式会拒绝且画布不丢节点；缺校准模式提示先关闭创建后再恢复');
  await page.screenshot({path:'output/playwright/pc04a3/recovery-resume-green.png',fullPage:true});
  await page.evaluate(result=>{window.__pc04a3Task1Result=result},{checks,labId:lab.id,topologyId:topology.id});
  console.log(JSON.stringify({checks,labId:lab.id,topologyId:topology.id}));
}
