async page => {
  page.setDefaultTimeout(10000);
  await page.unrouteAll({behavior:'wait'});
  const lab='11111111-1111-4111-8111-111111111111', chamber='22222222-2222-4222-8222-222222222222';
  let mode='ok', job=null, plan=null, started=null; const requests=[];
  const types=['channel_emulator','probe','pad','reference_antenna','receive_cable','signal_analyzer','vna','signal_generator'];
  const graph={id:'topo',name:'完整接线回归',revision:1,switch_category_id:'switch',chamber_id:chamber,is_active:true,is_default:true,
    nodes:types.map((type,i)=>({id:type,type,label:type,position:{x:i*230,y:100},params:{ports:['in','out'],visible_modes:i<2?['mimo_ota']:['calibration'],instrument_category_id:type==='signal_analyzer'?'sa':undefined}})),
    connections:types.slice(0,5).map((type,i)=>({id:'edge'+i,source:type,target:types[i+1],source_pin:'out',target_pin:'in',modes:[i===0?'mimo_ota':'calibration']})),
    operating_modes:[{id:'mimo_ota',name:'正常测试',active_connections:['edge0']},{id:'calibration',name:'参考接线',active_connections:['edge1','edge2','edge3','edge4']}]};
  graph.nodes[0].params.ce_port='B1.1';
  const digest='b'.repeat(64), routeDigest='a'.repeat(64);
  const selection={lab_profile_id:lab,chamber_id:chamber,topology_id:'topo',operating_mode:'mimo_ota',chain_id:'edge0',ce_port:'B1.1',probe_id:0,polarization:'V',route_digest:routeDigest,configuration_digest:digest,
    nodes:graph.nodes.slice(0,2),node_ids:types.slice(0,2),connections:graph.connections.slice(0,1),connection_ids:['edge0'],ports:[],
    calibration_nodes:graph.nodes.slice(2,6),calibration_node_ids:types.slice(2,6),calibration_connections:graph.connections.slice(1),calibration_connection_ids:['edge1','edge2','edge3','edge4']};
  const snapshot={configuration_complete:true,digest,payload:{lab_profile_id:lab,chamber_id:chamber,operating_mode:'mimo_ota',topology:{...graph,scope_source:'selected_route',selected_chain_id:'edge0',selected_route_digest:routeDigest}}};
  const record={run_id:'record',lab_profile_id:lab,run_at:'2026-11-04T00:00:00Z',status:'completed',result:{version:2,status:'completed',cleanup_confirmed:true,net_loss_db:20,sample_std_db:0.1,
    request:{topology_id:'topo',operating_mode:'mimo_ota',chain_id:'edge0',frequency_mhz:3500},configuration:{route_selection:selection},samples:[]}};
  await page.route('**/api/v1/**',async route=>{
    const p=new URL(route.request().url()).pathname; requests.push({method:route.request().method(),path:p}); let body={};
    if(p.endsWith('/lab-profiles'))body=[{id:lab,name:'校准回归实验室',is_active:true,chamber_config_id:chamber}];
    else if(p.endsWith('/instruments/catalog'))body={categories:[{key:'rfSwitch',categoryId:'switch',label:'射频开关',models:[],connection:{invalid_fields:{}},driverMode:'mock'},{key:'signalAnalyzer',categoryId:'sa',label:'分析仪资源',models:[],connection:{invalid_fields:{}},driverMode:'mock'}]};
    else if(p.endsWith('/hal/readiness')){
      if(mode==='error')return route.fulfill({status:503,json:{detail:'读取失败'}});
      body={available:true,drivers:[{category:'signalAnalyzer',model:'FSVA',status:'ok',detail:'快照回读'}],lab_profile:{profile_id:mode==='wrong'?'other':lab,status:'ok'},calibration:{status:'missing'},dut_attach:{},subnets:[],base_station_testcase_compatibility:{lab_profile_id:lab}};
    }else if(p.endsWith('/switch-topologies/templates'))body=[];
    else if(p.endsWith('/switch-topologies'))body={items:[graph],total:1};
    else if(p.endsWith('/route-calibration-paths'))body=[selection];
    else if(p.endsWith('/route-calibration-batches/preview')){
      const data=route.request().postDataJSON(); const ref=data.references[0];
      plan={lab_profile_id:lab,topology_id:'topo',operating_mode:'mimo_ota',preview_digest:'c'.repeat(64),switch_scope_digest:null,
        items:[{item_id:'item',route_selection:selection,configuration_scope:snapshot,transition_reasons:['固定直连，无开关动作'],switch_steps:[],
          request:{...data,...ref,chain_id:'edge0',configuration_digest:digest,route_digest:routeDigest}}]};body=plan;
    }else if(p.endsWith('/route-calibration-batches')&&route.request().method()==='POST'){
      started=route.request().postDataJSON();job={job_id:'job',lab_id:lab,topology_id:'topo',operating_mode:'mimo_ota',status:'waiting_manual',current_index:0,transition_id:'transition',plan,
        items:[{item_id:'item',status:'waiting_manual',run_id:null,request:plan.items[0].request}]};body=job;
    }else if(p.endsWith('/route-calibration-batches/job/cancel')){
      job={...job,status:'cancelled',current_index:null,f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:true,
        items:job.items.map(i=>({...i,status:'cancelled'}))};body=job;
    }else if(p.endsWith('/route-calibration-batches/job'))body=job;
    else if(p.endsWith('/route-calibration-batches'))body=job?[job]:[];
    else if(p.endsWith('/fixed-route-acquisitions'))body=[record];
    else if(p.endsWith('/fixed-route-acquisitions/record'))body=record;
    else if(p.endsWith('/fixed-route-acquisitions/record/application-preview'))body={selection,acquisition_run_id:'record',old_value_db:null,new_net_loss_db:20,delta_db:null,
      eligibility:{eligible_for_adoption:true,measurement_provenance:'real',certification_status:'unknown',blockers:[],warnings:[]}};
    else if(p.endsWith('/route-calibration-applications')&&route.request().method()==='POST'){
      await new Promise(resolve=>setTimeout(resolve,1200));return route.fulfill({status:503,json:{detail:'回执未确认测试'}});
    }
    else if(/route-calibration|fixed-route/.test(p))body=[];
    else if(p.endsWith('/test-executions'))body={items:[],total:0};
    else if(p.endsWith('/alerts/summary'))body={total_active:0,by_severity:{},by_category:{}};
    else if(p.endsWith('/system-logs/tail'))body={entries:[],total_lines_read:0};
    else return route.fulfill({status:503,json:{detail:'测试未提供该只读投影'}});
    await route.fulfill({status:200,json:body});
  });
  await page.setViewportSize({width:1720,height:1100});await page.goto('http://127.0.0.1:5181');
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  const panel=page.getByTestId('route-calibration-panel'),fixed=page.getByTestId('fixed-route-preparation'),list=page.getByTestId('batch-route-preparation');
  await list.waitFor();if(await fixed.isVisible())throw Error('两套准备表单同时显示');
  const phase=async name=>panel.getByText(name,{exact:true}).click();
  await list.getByLabel('批量频点（MHz，逗号分隔）',{exact:true}).fill('3500');
  await phase('3 审阅与采用');if(await list.isVisible())throw Error('审阅仍显示准备表单');
  await phase('1 准备');if(await list.getByLabel('批量频点（MHz，逗号分隔）',{exact:true}).inputValue()!=='3500')throw Error('切步骤丢草稿');
  await list.locator('.mantine-MultiSelect-root').click();await page.getByRole('option').filter({hasText:'edge0'}).click();await page.keyboard.press('Escape');
  await list.getByLabel('批量请求功率（dBm，不作实测值）',{exact:true}).fill('-30');
  await list.getByLabel('参考天线／位置 edge0 @3500',{exact:true}).fill('参考位置A');
  await list.getByLabel('接收线损（dB） edge0 @3500',{exact:true}).fill('2');
  await list.getByLabel('接收线依据 edge0 @3500',{exact:true}).fill('明确来源');
  await list.getByLabel('已核对清单的固定接线条件',{exact:true}).check();await list.getByLabel('已确认请求功率及现场安全条件',{exact:true}).check();
  await list.getByRole('button',{name:'预览完整批清单',exact:true}).click();await page.getByTestId('batch-plan').waitFor();
  await list.getByRole('button',{name:'明确开始此批校准',exact:true}).click();
  await page.getByTestId('batch-manual').waitFor();
  if(started.chain_ids.length!==1||started.frequencies_mhz.length!==1)throw Error('单项清单请求改变');
  for(const name of ['1 准备','3 审阅与采用','2 采集']){
    await phase(name);if(!await page.getByTestId('batch-manual').isVisible())throw Error('步骤隐藏人工确认');
    if(!await panel.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).isVisible())throw Error('步骤隐藏取消');
  }
  await panel.getByRole('button',{name:'取消批校准并等待真实停发／释放',exact:true}).click();
  await panel.getByTestId('batch-history-detail').waitFor();
  await phase('1 准备');await panel.getByLabel('采集方式',{exact:true}).click();await page.getByRole('option',{name:'固定接线采集（不自动切换通路）',exact:true}).click();
  await fixed.waitFor();if(await list.isVisible())throw Error('切固定接线仍显示清单表单');
  await fixed.getByLabel('完整校准通路',{exact:true}).click();await page.getByRole('option').filter({hasText:'edge0'}).click();
  await fixed.getByRole('button',{name:'开始自动采集',exact:true}).waitFor();
  await panel.getByTestId('acquisition-history').locator('summary').click();
  await panel.getByRole('button',{name:'查看记录',exact:true}).click();
  await panel.getByLabel('选用截止时间（本地时间，明确填写）',{exact:true}).fill('2099-01-01T12:00');
  await panel.getByRole('button',{name:'确认采用此实测记录',exact:true}).click();
  await phase('1 准备');await panel.getByText(/确认请求未获成功回执/).waitFor();
  if(!await panel.getByRole('button',{name:'重新读取采用预览与历史',exact:true}).isVisible())throw Error('采用未知回执核对入口被步骤隐藏');
  const summary=panel.getByTestId('calibration-result-summary');
  await summary.getByText('0.100 dB',{exact:true}).waitFor();
  if(await panel.locator('details').filter({has:page.locator('summary',{hasText:'本次冻结配置、原始回复与读数'})}).getAttribute('open')!==null)throw Error('原始JSON默认展开');
  record.status='simulated';record.result.status='simulated';record.result.sample_std_db=99;record.result.net_loss_db=99;record.result.request.mock_input={samples:[],expected_loss_db:null};
  await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  await panel.getByTestId('acquisition-history').locator('summary').click();await panel.getByRole('button',{name:'查看记录',exact:true}).click();
  await panel.getByTestId('calibration-result-summary').waitFor();
  if(await panel.getByTestId('calibration-result-summary').getByText(/99/).count())throw Error('模拟数值进入正式摘要');
  if(!await panel.getByRole('button',{name:'确认采用此实测记录',exact:true}).isDisabled())throw Error('模拟记录可采用');
  if(await panel.getByTestId('mock-calibration-result').locator('details').getAttribute('open')!==null)throw Error('模拟原始明细默认展开');
  return {passed:['三步骤保持表单状态','1×1清单沿原预览启动','所有步骤保留人工与取消','取消后审阅原记录','固定接线证据入口保留','采用未知回执跨步骤可见','重复性摘要和原始证据分层','模拟数值不进入正式摘要且不可采用']};
}
