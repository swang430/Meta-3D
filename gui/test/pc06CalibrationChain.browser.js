async page => {
  await page.unrouteAll({behavior:'wait'});
  const lab='11111111-1111-4111-8111-111111111111', chamber='22222222-2222-4222-8222-222222222222';
  let mode='ok'; const requests=[];
  const types=['channel_emulator','probe','pad','reference_antenna','receive_cable','signal_analyzer','vna','signal_generator'];
  const graph={id:'topo',name:'完整接线回归',revision:1,switch_category_id:'switch',chamber_id:chamber,is_active:true,is_default:true,
    nodes:types.map((type,i)=>({id:type,type,label:type,position:{x:i*230,y:100},params:{ports:['in','out'],visible_modes:i<2?['mimo_ota']:['calibration'],instrument_category_id:type==='signal_analyzer'?'sa':undefined}})),
    connections:types.slice(0,5).map((type,i)=>({id:'edge'+i,source:type,target:types[i+1],source_pin:'out',target_pin:'in',modes:[i===0?'mimo_ota':'calibration']})),
    operating_modes:[{id:'mimo_ota',name:'正常测试',active_connections:['edge0']},{id:'calibration',name:'参考接线',active_connections:['edge1','edge2','edge3','edge4']}]};
  await page.route('**/api/v1/**',async route=>{
    const p=new URL(route.request().url()).pathname; requests.push(route.request().method()); let body={};
    if(p.endsWith('/lab-profiles'))body=[{id:lab,name:'校准回归实验室',is_active:true,chamber_config_id:chamber}];
    else if(p.endsWith('/instruments/catalog'))body={categories:[{key:'rfSwitch',categoryId:'switch',label:'射频开关',models:[],connection:{invalid_fields:{}},driverMode:'mock'},{key:'signalAnalyzer',categoryId:'sa',label:'分析仪资源',models:[],connection:{invalid_fields:{}},driverMode:'mock'}]};
    else if(p.endsWith('/hal/readiness')){
      if(mode==='error')return route.fulfill({status:503,json:{detail:'读取失败'}});
      body={available:true,drivers:[{category:'signalAnalyzer',model:'FSVA',status:'ok',detail:'快照回读'}],lab_profile:{profile_id:mode==='wrong'?'other':lab,status:'ok'},calibration:{status:'missing'},dut_attach:{},subnets:[],base_station_testcase_compatibility:{lab_profile_id:lab}};
    }else if(p.endsWith('/switch-topologies/templates'))body=[];
    else if(p.endsWith('/switch-topologies'))body={items:[graph],total:1};
    else if(/route-calibration|fixed-route/.test(p))body=[];
    else if(p.endsWith('/test-executions'))body={items:[],total:0};
    else if(p.endsWith('/alerts/summary'))body={total_active:0,by_severity:{},by_category:{}};
    else if(p.endsWith('/system-logs/tail'))body={entries:[],total_lines_read:0};
    else return route.fulfill({status:503,json:{detail:'测试未提供该只读投影'}});
    await route.fulfill({status:200,json:body});
  });
  await page.setViewportSize({width:1720,height:1100});await page.goto('http://127.0.0.1:5181');
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
  const card=page.getByTestId('calibration-instruments');await card.waitFor();
  for(const type of types)await page.locator(`.react-flow__node[data-id="${type}"]`).waitFor();
  await card.getByText(/HAL快照：ok/).waitFor();
  mode='wrong';await card.getByRole('button',{name:'刷新仪器状态'}).click();await card.getByText(/运行快照读取中、不可用/).waitFor();
  if(await card.getByText(/HAL快照：ok/).count())throw Error('错Lab仍发布旧快照');
  mode='error';await card.getByRole('button',{name:'刷新仪器状态'}).click();await card.getByText(/运行快照读取中、不可用/).waitFor();
  if(requests.some(method=>method!=='GET'))throw Error('展示触发写操作');
  await page.getByRole('button',{name:'添加器件',exact:true}).click();
  if(await card.getByRole('button',{name:'前往仪器资源核对驱动'}).count())throw Error('草稿仍可绕过导航保护');
  return {passed:['完整接线含普通pad及孤立VNA/信号源','错Lab与失败保持未知','只读不发硬件写操作','草稿禁止快捷离开']};
}
