// 专属新库、真实REST和原拓扑；只证明全Mock软件通路，不提供正式计量资格。
async page => {
  const base=new URL(page.url()).origin, api=`${base}/api/v1`, checks=[], requests=[];
  page.setDefaultTimeout(15000);
  const ensure=(ok,message)=>{if(!ok)throw Error(message)};
  const json=async response=>{ensure(response.ok(),await response.text());return response.json()};
  const read=path=>page.request.get(`${api}${path}`).then(json);
  const status=await read('/instruments/hal/status');ensure(status.mode==='mock','只允许全Mock');
  const labs=await read('/lab-profiles'),a=labs.find(l=>l.name==='PC06A2入口甲'),b=labs.find(l=>l.name==='PC06A2入口乙');
  ensure(labs.length===3&&a&&b,'必须是本片fixture');
  const topologies=await read(`/switch-topologies?lab_profile_id=${a.id}`),topology=topologies.items.find(t=>t.chamber_id===a.chamber_config_id);
  const root=`/lab-profiles/${a.id}`,single=`${root}/fixed-route-acquisitions`,batch=`${root}/route-calibration-batches`;
  ensure((await read(single)).length===0,'生命周期只在新库首次执行');
  const modes=['mimo_ota','trp_tis'],cal=['calibration'],nodes=[],connections=[];
  for(const [i,pol] of [[1,'v'],[2,'h']]){
    nodes.push({id:`ce${i}`,type:'ce_port',label:`B1.${i}`,position:{x:30,y:60+(i-1)*300},params:{ports:['out'],visible_modes:modes}},
      {id:`p${pol}`,type:'probe',label:`探头0${pol.toUpperCase()}`,position:{x:390,y:60+(i-1)*300},params:{probe_id:0,polarization:pol.toUpperCase(),ports:['in','out'],visible_modes:[...modes,...cal]}});
    connections.push({id:`fixed-${pol}`,source:`ce${i}`,target:`p${pol}`,source_pin:'out',target_pin:'in',modes});
    const reference=[['air','air_path','空气参考段'],['ref','reference_antenna','参考天线'],['rx','receive_cable','接收线缆'],['sa','signal_analyzer','频谱分析仪']];
    reference.forEach(([id,type,label],n)=>nodes.push({id:`${pol}_${id}`,type,label:`${label}${pol.toUpperCase()}`,position:{x:650+n*220,y:60+(i-1)*300},params:{connection_scope:'calibration',visible_modes:cal,ports:['in','out']}}));
    const chain=[`p${pol}`,...reference.map(([id])=>`${pol}_${id}`)];
    chain.slice(0,-1).forEach((source,n)=>connections.push({id:`reference-${pol}-${n}`,source,target:chain[n+1],source_pin:'out',target_pin:'in',modes:cal}));
  }
  const saved=await json(await page.request.patch(`${api}/switch-topologies/${topology.id}?lab_profile_id=${a.id}`,{data:{nodes,connections,operating_modes:[
    {id:'mimo_ota',name:'固定通路',active_connections:['fixed-v','fixed-h']},
    {id:'trp_tis',name:'另一正常模式',active_connections:['fixed-v','fixed-h']},
    {id:'calibration',name:'校准参考接线',active_connections:connections.filter(c=>c.id.startsWith('reference-')).map(c=>c.id)}]}}));
  ensure(saved.nodes.length===12&&saved.connections.length===10,'完整双极化参考接线未保存');
  const candidates=await read(`${root}/route-calibration-paths?topology_id=${topology.id}&operating_mode=mimo_ota&selection_scope=individual`);
  ensure(candidates.length===2&&candidates.every(c=>c.calibration_node_ids.length===4),'真实候选缺少完整参考段');
  checks.push('真实PATCH保存12节点10连线，正常/空气/参考天线/接收线缆/分析仪完整，真实候选回读');
  const onRequest=r=>{if(new URL(r.url()).pathname.startsWith('/api/'))requests.push({method:r.method(),url:r.url(),body:r.postData()})};
  page.on('request',onRequest);
  try{
  await page.setViewportSize({width:1720,height:1100});await page.goto(base);
  const choose=async lab=>{await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();await page.getByRole('option').filter({hasText:lab.name}).click()};
  const manage=()=>page.getByRole('tab',{name:'系统校准',exact:true}).click();
  const open=async()=>{await manage();await page.getByRole('button',{name:'进入当前实验室射频拓扑',exact:true}).click();await page.getByTestId('route-calibration-panel').waitFor()};
  await choose(a);await open();
  const panel=page.getByTestId('route-calibration-panel'),bp=page.getByTestId('route-batch-panel');
  await panel.getByRole('textbox',{name:'完整校准通路',exact:true}).click();await page.getByRole('option').filter({hasText:'fixed-v'}).click();
  await panel.getByTestId('selected-calibration-path').waitFor();
  for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','隔离Mock参考天线V中心'],['接收线缆损耗','2'],['接收线缆记录来源','隔离软件记录@2595MHz']])await panel.getByLabel(label,{exact:false}).fill(value);
  await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();
  const pending=page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions')&&r.request().method()==='POST');
  await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();
  const response=await pending;ensure(response.status()===202,'单路未被接受');const first=await response.json();
  await panel.getByText('模拟流程完成（无真实测量）',{exact:true}).first().waitFor();
  const run=await read(`${single}/${first.run_id}`),preview=await read(`${single}/${first.run_id}/application-preview`);
  ensure(run.lab_profile_id===a.id&&run.status==='simulated'&&run.result.net_loss_db===null&&!preview.eligibility.eligible_for_adoption,'Mock单路资格错误');
  ensure(await panel.getByRole('button',{name:'确认采用此实测记录',exact:true}).isDisabled(),'Mock采用未禁用');
  await manage();await open();await panel.getByRole('button',{name:'查看记录',exact:true}).first().waitFor();
  ensure((await read(single)).some(r=>r.run_id===run.run_id),'离页丢失原run');
  await page.screenshot({path:'output/playwright/pc06a2-task3-single.png',fullPage:true});
  checks.push('显式选择真实候选单路采集simulated/损耗null/采用禁用；管理离页回来同run无取消');
  const wait=async(id,predicate)=>{for(let n=0;n<120;n++){const r=await read(`${batch}/${id}`);if(predicate(r))return r;await page.waitForTimeout(100)}throw Error('批状态未到达预期')};
  const prepare=async()=>{
    await page.waitForFunction(()=>document.querySelector('[data-testid="route-batch-panel"] fieldset')?.disabled===false);
    await bp.locator('.mantine-MultiSelect-root').click();for(const c of candidates)await page.getByRole('option').filter({hasText:c.chain_id}).click();await page.keyboard.press('Escape');
    await bp.getByLabel('批量频点（MHz，逗号分隔）',{exact:true}).fill('2595,3500');await bp.getByLabel('批量请求功率（dBm，不作实测值）',{exact:true}).fill('-30');await bp.getByLabel('每项采样数（2–10）',{exact:true}).fill('10');
    for(const c of candidates)for(const f of [2595,3500])for(const [label,value] of [['参考天线／位置',`REF ${c.chain_id} 中心`],['接收线损（dB）','2'],['接收线依据',`隔离软件记录 ${f}MHz`]])await bp.getByLabel(`${label} ${c.chain_id} @${f}`,{exact:true}).fill(value);
    await bp.getByRole('checkbox',{name:'已核对清单的固定接线条件',exact:true}).check();await bp.getByRole('checkbox',{name:'已确认请求功率及现场安全条件',exact:true}).check();await bp.getByRole('button',{name:'预览完整批清单',exact:true}).click();await bp.getByText('服务器完整清单：4项',{exact:true}).waitFor();
  };
  const begin=async()=>{const pending=page.waitForResponse(r=>r.url().endsWith('/route-calibration-batches')&&r.request().method()==='POST');await bp.getByRole('button',{name:'明确开始此批校准',exact:true}).click();const r=await pending;ensure(r.status()===202,await r.text());return r.json()};
  const next=async row=>{const manual=bp.getByTestId('batch-manual');await manual.waitFor();await manual.getByLabel('重新输入当前参考位置',{exact:true}).fill(row.items[row.current_index].request.reference_antenna);await manual.getByRole('checkbox',{name:'确认仅对应当前项和当前人工步骤',exact:true}).check();await manual.getByRole('button',{name:'确认当前步骤并继续',exact:true}).click()};
  await prepare();await page.screenshot({path:'output/playwright/pc06a2-task3-preview.png',fullPage:true});
  const initial=await begin();let row=await wait(initial.job_id,r=>r.status==='waiting_manual');
  ensure(await page.getByRole('button',{name:'保存拓扑',exact:true}).isDisabled(),'活动批未冻结图');
  await manage();await choose(b);ensure(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId'))===a.id,'离图后activeWork没有保护跨Lab');
  const still=await read(`${batch}/${row.job_id}`);ensure(still.status==='waiting_manual','离页自动取消了活动批');
  await open();await bp.getByRole('button',{name:'读取批历史／恢复活动批',exact:true}).click();await bp.getByTestId('batch-manual').waitFor();
  await page.screenshot({path:'output/playwright/pc06a2-task3-active-recovery.png',fullPage:true});
  checks.push('真实waiting_manual活动窗口：图冻结，离开到管理仍阻止跨Lab，服务端未取消，回来恢复原job');
  await next(row);row=await wait(row.job_id,r=>r.status==='waiting_manual'&&r.current_index===2);
  ensure(row.items.slice(0,2).every(i=>i.status==='simulated'),'前两项未模拟持久化');
  await page.screenshot({path:'output/playwright/pc06a2-task3-cross-route.png',fullPage:true});
  await next(row);row=await wait(row.job_id,r=>r.status==='completed'&&r.finalization_committed);
  ensure(row.items.length===4&&row.items.every(i=>i.status==='simulated')&&row.f64_control_released===null,'批次冒充真值');
  for(const item of row.items){const child=await read(`${single}/${item.run_id}`),p=await read(`${single}/${item.run_id}/application-preview`);ensure(child.status==='simulated'&&child.result.net_loss_db===null&&!p.eligibility.eligible_for_adoption,'批次子项错误采用')}
  await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent==='添加器件')?.disabled);
  await choose(b);await panel.getByText('暂无采集记录。',{exact:true}).waitFor();ensure(!await panel.getByTestId('route-acquisition-result').count(),'乙泄漏甲结果');
  ensure((await read(`/lab-profiles/${b.id}/fixed-route-acquisitions`)).length===0&&(await read(`/lab-profiles/${b.id}/route-calibration-batches`)).length===0,'乙有甲记录');
  await manage();await choose(a);await open();const completedHistory=await read(single);ensure(completedHistory.length===5&&completedHistory.some(r=>r.run_id===first.run_id),'返回甲复制或丢失run');
  checks.push('第一批completed且软件锁释放后可切乙，乙历史为空；返回甲保留5个原run');
  await page.reload();await open();await prepare();const second=await begin();const cancelBefore=await wait(second.job_id,r=>r.status==='waiting_manual');
  await next(cancelBefore);await wait(second.job_id,r=>r.status==='waiting_manual'&&r.current_index===2);
  await bp.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).click();const cancelled=await wait(second.job_id,r=>r.status==='cancelled'&&r.finalization_committed);
  await page.reload();await open();ensure((await read(`${batch}/${second.job_id}`)).status==='cancelled','刷新取消批自动续跑');
  await bp.getByText('批历史（不覆盖活动身份）',{exact:true}).waitFor();
  ensure(await page.getByRole('button',{name:'保存拓扑',exact:true}).isDisabled(),'取消Mock缺真实释放证明却被解锁');
  await page.screenshot({path:'output/playwright/pc06a2-task3-cancelled.png',fullPage:true});
  checks.push('真实四项预览/首项与跨路人工确认/四项simulated完成，第二批两项后取消并刷新不续跑');
  const after=await read(single);ensure(after.length===7&&after.some(r=>r.run_id===first.run_id),'取消后复制或丢失run');
  checks.push('取消Mock虽服务端终态但无真实释放证明，既有保守锁仍保留；不是取消后切Lab通过');
  return {checks,requests,hal:status,lab_id:a.id,other_lab_id:b.id,topology_id:topology.id,candidates,single:run,completed:row,cancelled,run_ids:after.map(r=>r.run_id),formal_acceptance:false,
    single_active_window_observed:false,single_active_window_note:'单路Mock快速终止，跨页活动保护由真实waiting_manual批窗口和后端生命周期回归补证，不声称观察单路活动窗口'};
  }finally{page.off('request',onRequest)}
}
