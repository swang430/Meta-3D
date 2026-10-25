// 独立临时SQLite/全HAL Mock；真实API、原画布、真实鼠标与服务器回读，不拦截HTTP响应。
async page=>{
  await page.evaluate(()=>{window.__routeCalibrationResult=null});
  page.setDefaultTimeout(15000);
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,checks=[];
  const json=async response=>{if(!response.ok())throw new Error(await response.text());return response.json()};
  const status=await json(await page.request.get(`${api}/instruments/hal/status`));
  if(status.mode!=='mock')throw new Error('仅允许隔离全Mock环境');
  const labs=await json(await page.request.get(`${api}/lab-profiles`));
  const a=labs.find(row=>row.name==='PC04自动采集甲'),b=labs.find(row=>row.name==='PC04自动采集乙');
  if(!a||!b)throw new Error('缺少隔离浏览器fixture');
  const historyUrl=`${api}/lab-profiles/${a.id}/fixed-route-acquisitions`;
  if((await json(await page.request.get(historyUrl))).length)throw new Error('必须使用尚无采集记录的新数据库');
  const listed=await json(await page.request.get(`${api}/switch-topologies`,{params:{lab_profile_id:a.id}}));
  const topology=listed.items.find(row=>row.chamber_id===a.chamber_config_id);
  const url=`${api}/switch-topologies/${topology.id}?lab_profile_id=${a.id}`;
  const modes=['mimo_ota','trp_tis'],cal=['calibration'];
  const nodes=[
    {id:'ce1',type:'ce_port',label:'B1.1',position:{x:30,y:50},params:{ports:['out'],visible_modes:modes}},
    {id:'ce2',type:'ce_port',label:'B1.2',position:{x:30,y:300},params:{ports:['out'],visible_modes:modes}},
    {id:'pv',type:'probe',label:'探头0V',position:{x:390,y:50},params:{probe_id:0,polarization:'V',ports:['in','out'],visible_modes:[...modes,...cal]}},
    {id:'ph',type:'probe',label:'探头0H',position:{x:390,y:300},params:{probe_id:0,polarization:'H',ports:['in','out'],visible_modes:modes}},
    ...[['air','air_path','空气参考段'],['ref','reference_antenna','参考天线V'],['rx','receive_cable','接收线缆'],['sa','signal_analyzer','频谱分析仪']].map(([id,type,label],i)=>
      ({id,type,label,position:{x:650+i*220,y:50},params:{connection_scope:'calibration',visible_modes:cal,ports:['in','out']}}))];
  const connections=[{id:'fixed-v',source:'ce1',target:'pv',source_pin:'out',target_pin:'in',modes},
    {id:'fixed-h',source:'ce2',target:'ph',source_pin:'out',target_pin:'in',modes},
    ...[['pv','air'],['air','ref'],['ref','rx'],['rx','sa']].map(([source,target],i)=>
      ({id:`reference-${i}`,source,target,source_pin:'out',target_pin:'in',modes:cal}))];
  await json(await page.request.patch(url,{data:{nodes,connections,operating_modes:[
    {id:'mimo_ota',name:'固定通路',active_connections:['fixed-v','fixed-h']},
    {id:'trp_tis',name:'另一正常模式',active_connections:['fixed-v','fixed-h']},
    {id:'calibration',name:'校准参考接线',active_connections:connections.filter(row=>row.id.startsWith('reference-')).map(row=>row.id)}]}}));
  await page.setViewportSize({width:1720,height:1100});
  await page.goto(origin);
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option').filter({hasText:a.name}).click();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'总览',exact:true}).click();
  await page.getByTestId('fixed-route-method').waitFor();
  if(await page.getByTestId('fixed-route-calibration').count()||await page.getByTestId('fixed-route-acquisition').count())throw new Error('总览仍有重复独立校准表单');
  checks.push('总览只保留静态方法说明，独立自动/手填校准表单入口已撤');
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  const panel=page.getByTestId('route-calibration-panel');await panel.waitFor();
  const choosePath=async()=>{const select=panel.getByRole('textbox',{name:'完整校准通路',exact:true});if((await select.inputValue()).includes('fixed-v'))return;await select.click();await page.getByRole('option').filter({hasText:'fixed-v'}).click()};
  await choosePath();await panel.getByTestId('selected-calibration-path').waitFor();
  await page.waitForFunction(()=>document.querySelector('.react-flow__node[data-id="pv"]')?.style.outline.includes('solid'));
  const selected=await page.locator('.react-flow__node[data-id="pv"]').getAttribute('style');
  if(!selected?.includes('outline'))throw new Error('没有高亮原画布节点');
  await page.waitForFunction(()=>{
    const path=document.querySelector('.react-flow__edge[data-id="fixed-v"] .react-flow__edge-path');
    const node=document.querySelector('.react-flow__node[data-id="ce1"]');
    return path?.getTotalLength()>100 && node?.querySelectorAll('.react-flow__handle.source[data-handleid="out"]').length===1;
  });
  checks.push('服务器完整正常通路与参考测量段同屏，原节点高亮');
  // 原双击编辑及真实网络失败保留草稿；不拦截响应制造假保存。
  await page.getByRole('button',{name:'Fit View',exact:true}).click();
  await page.locator('.react-flow__node[data-id="pv"]').dblclick();
  await page.getByLabel('器件名称',{exact:true}).fill('探头0V·侧栏验收');
  await page.getByRole('button',{name:'应用器件修改',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option').filter({hasText:b.name}).click();
  if(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId'))!==a.id)throw new Error('dirty拓扑仍切到了另一实验室');
  if(!await page.locator('.react-flow__node[data-id="pv"]').getByText('探头0V·侧栏验收',{exact:true}).count())throw new Error('dirty切lab拒绝后草稿丢失');
  checks.push('dirty切lab明确拒绝且原草稿保留');
  if(await panel.getByRole('textbox',{name:'完整校准通路',exact:true}).isEnabled())throw new Error('草稿未保存仍能选择旧路径采集');
  await page.context().setOffline(true);
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
  await page.getByTestId('topology-save-stage').getByText('拓扑保存失败；草稿未保存',{exact:true}).waitFor();
  if(!await page.locator('.react-flow__node[data-id="pv"]').getByText('探头0V·侧栏验收',{exact:true}).count())throw new Error('保存失败丢失草稿');
  await page.context().setOffline(false);
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
  await page.getByTestId('topology-save-stage').getByText('拓扑已保存到服务器；不自动同步仪器绑定',{exact:true}).waitFor();
  const stored=await json(await page.request.get(url));
  if(stored.nodes.find(row=>row.id==='pv').label!=='探头0V·侧栏验收')throw new Error('重试未持久化原草稿');
  await choosePath();checks.push('原双击编辑保留；离线保存失败保留草稿，恢复网络后真实持久化');
  // 保存通知覆盖顶部选择器时，在开始采集前等待其真实离开DOM；不在run结束后误称采集中切换。
  await page.waitForFunction(()=>document.querySelectorAll('.mantine-Notification-root').length===0);
  for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','临时软件验证参考件 V 中心位置'],['接收线缆损耗','2'],['接收线缆记录来源','临时记录@2595MHz']])
    await panel.getByLabel(label,{exact:false}).fill(value);
  const confirmSafety=async()=>{await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check()};
  const start=async(beforeResponse)=>{await confirmSafety();const pending=page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions')&&r.request().method()==='POST');await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();if(beforeResponse)await beforeResponse();const response=await pending;if(response.status()!==202)throw new Error(await response.text());return response.json()};
  // 在开始请求回执前实际尝试切换；不延长/伪造采集、不拦截响应、不固定sleep等DOM。
  const first=await start(async()=>{
    await page.waitForFunction(()=>document.querySelector('input[aria-label="操作模式"]')?.disabled===true);
    const interactive=page.locator('.react-flow__controls-interactive');
    // RED原生复现：默认Controls连续两次切换会直接把冻结store重新设为可交互。
    if(await interactive.count()){await interactive.click();await interactive.click()}
    const frozen=await page.evaluate(()=>({
      inputs:['器件列表','新增器件类型','操作模式'].every(label=>document.querySelector(`input[aria-label="${label}"]`)?.disabled===true),
      buttons:['添加器件','校准接线','保存拓扑'].every(text=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===text)?.disabled===true),
      draggable:document.querySelectorAll('.react-flow__node.draggable').length,
      connectable:document.querySelectorAll('.react-flow__handle.connectablestart, .react-flow__handle.connectableend').length,
      drawers:document.querySelectorAll('[role="dialog"]').length,
      interactiveButtons:document.querySelectorAll('.react-flow__controls-interactive').length,
      zoomButtons:document.querySelectorAll('.react-flow__controls-zoomin, .react-flow__controls-zoomout').length,
      fitView:document.querySelector('.react-flow__controls-fitview')?.disabled===false,
    }));
    if(!frozen.inputs||!frozen.buttons||frozen.draggable||frozen.connectable||frozen.drawers||frozen.interactiveButtons||frozen.zoomButtons!==2||!frozen.fitView)throw new Error(`采集pending编辑入口未全部冻结：${JSON.stringify(frozen)}`);
    checks.push(`真实pending窗口全部编辑冻结：${JSON.stringify(frozen)}`);
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
    await page.getByRole('option').filter({hasText:b.name}).click();
    if(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId'))!==a.id)throw new Error('开始状态未确认时实际切换了实验室');
  });
  const request=first.result.request;
  if(request.topology_id!==topology.id||request.operating_mode!=='mimo_ota'||!request.route_digest)throw new Error('新客户端漏完整路径请求身份');
  checks.push('新请求含三项路径身份；开始状态未确认期间图/模式/实验室锁定，服务器run取消可达');
  await panel.getByText('模拟流程完成（无真实测量）',{exact:true}).first().waitFor();
  await page.getByRole('button',{name:'添加器件',exact:true}).waitFor();
  if(!await page.getByRole('textbox',{name:'器件列表',exact:true}).isEnabled()||!await page.getByRole('button',{name:'保存拓扑',exact:true}).isEnabled())throw new Error('模拟采集结束后未恢复编辑');
  const interactive=page.locator('.react-flow__controls-interactive');
  await interactive.waitFor();await interactive.click();await interactive.click();
  await page.waitForFunction(()=>document.querySelectorAll('.react-flow__node.draggable').length>0&&document.querySelectorAll('.react-flow__handle.connectablestart').length>0);
  checks.push('冻结时无Controls交互旁路但保留缩放/FitView；解除后原生连续切换可恢复拖动和连接');
  await panel.getByText('服务器采用预览（认证资格未知）',{exact:true}).waitFor();
  if(await panel.getByRole('button',{name:'确认采用此实测记录',exact:true}).isEnabled())throw new Error('Mock可采用');
  const record=await json(await page.request.get(`${historyUrl}/${first.run_id}`));
  if(record.result.version!==2||record.status!=='simulated'||record.result.net_loss_db!==null||record.result.samples.length||record.formal_eligible!==false||record.result.configuration.route_selection.connection_ids.length!==1)throw new Error(JSON.stringify(record));
  const rejected=await page.request.post(`${api}/lab-profiles/${a.id}/route-calibration-applications`,{data:{acquisition_run_id:first.run_id,
    route_digest:request.route_digest,expected_current_application_id:null,idempotency_key:crypto.randomUUID(),confirmed:true,adoption_valid_until:'2099-01-01T00:00:00Z'}});
  if(rejected.status()!==422)throw new Error('服务器没有拒绝Mock确认');
  const applications=await json(await page.request.get(`${api}/lab-profiles/${a.id}/route-calibration-applications`,{params:{topology_id:topology.id,chain_id:'fixed-v'}}));
  if(applications.length)throw new Error('Mock错误创建采用记录');
  await panel.getByTestId('route-acquisition-result').scrollIntoViewIfNeeded();await page.screenshot({path:'output/playwright/pc04a3/lifecycle-mock-result.png',fullPage:true});
  checks.push('真实持久化version2模拟记录，功率/损耗为空；UI与服务器双重拒绝Mock采用，采用历史为零');
  const second=await start();
  const cancelledResponse=page.waitForResponse(r=>r.url().endsWith(`/${second.run_id}/cancel`)&&r.request().method()==='POST');
  await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();
  await json(await cancelledResponse);
  await panel.getByText('已取消',{exact:true}).first().waitFor();
  const cancelled=await json(await page.request.get(`${historyUrl}/${second.run_id}`));
  if(cancelled.status!=='cancelled'||cancelled.result.net_loss_db!==null)throw new Error(JSON.stringify(cancelled));
  checks.push('实际POST取消并保存cancelled，不用HTTP断开冒充停发');
  // 切模式只换候选，不换正在查看的历史run；跨lab完全隔离。
  await page.getByRole('textbox',{name:'操作模式',exact:true}).click();await page.getByRole('option',{name:'另一正常模式',exact:true}).click();
  if(!(await panel.getByTestId('route-acquisition-result').innerText()).includes(second.run_id))throw new Error('切模式改了历史run身份');
  checks.push('切正常模式保留历史run冻结身份，不冒充当前选择');
  await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await panel.getByRole('button',{name:'查看记录',exact:true}).first().waitFor();
  const afterReload=await json(await page.request.get(historyUrl));
  if(afterReload.length!==2)throw new Error('刷新未持久化两次采集');
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:b.name}).click();
  await panel.getByText('暂无采集记录。',{exact:true}).waitFor();
  if(await panel.getByTestId('route-acquisition-result').count())throw new Error('跨lab泄漏原结果');
  await page.getByText('PC04A3显式路径乙',{exact:true}).waitFor();
  if(await page.locator('.react-flow__node[data-id="pv"]').count())throw new Error('清洁切乙携带了甲的草稿节点');
  checks.push('刷新读取持久历史；跨lab无记录/结果泄漏');
  const result={passed:checks.length,checks,lab_id:a.id,topology_id:topology.id,run_ids:[first.run_id,second.run_id],mock_confirmation_status:rejected.status(),application_count:applications.length};
  await page.evaluate(value=>{window.__pc04a3LifecycleResult=value},result);return result;
}
