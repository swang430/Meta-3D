// Task4 真实HTTP矩阵；仅专用新库/Mock。不能以这些声明证明实物导通。
async page => {
  const origin = new URL(page.url()).origin, api = `${origin}/api/v1`;
  page.setDefaultTimeout(15000);
  await page.setViewportSize({width:1800,height:1100});
  let current = '前置';
  const check = (value, message) => { if (!value) throw Error(`${current}: ${message}`); };
  const eq = (a,b,message) => check(JSON.stringify(a)===JSON.stringify(b),message);
  const calls = [], rows = [];
  try {
  const call = async (method,path,data,status=200) => {
    const headers=method==='POST'&&/^\/lab-profiles\/[^/]+\/route-calibration-batches$/.test(path)?{'Idempotency-Key':`04a40000-0000-4000-8000-${String(calls.length).padStart(12,'0')}`} : undefined;
    const response = await page.request.fetch(`${api}${path}`,{method,data,headers});
    const text = await response.text(); let body; try {body=JSON.parse(text);} catch {body=text;}
    const exchange={row:current,method,path,request:data,headers,status:response.status(),response:body};
    calls.push(exchange); console.log(JSON.stringify({exchange}));
    eq(response.status(),status,`${method} ${path} 期望${status}实际${response.status()}: ${text}`);
    return body;
  };
  check((await call('GET','/instruments/hal/status')).mode==='mock','必须全Mock');
  const labs=await call('GET','/lab-profiles'),lab=labs.find(l=>l.name==='PC04A4c内部通路甲'),other=labs.find(l=>l.name==='PC04A4c内部通路乙');
  check(lab&&other,'专用甲乙Lab缺失');
  const historyRoot=`/lab-profiles/${lab.id}/fixed-route-acquisitions`;
  const oldHistory=await call('GET',historyRoot);
  eq(oldHistory.length,2,'生命周期采集计数必须恰两次');
  // 以真实两次采集冻结的topology_id定位源图，不凭可重复的显示名称。
  const original=await call('GET',`/switch-topologies/${oldHistory[0].result.request.topology_id}?lab_profile_id=${lab.id}`);
  check(original.name==='PC04A4c图甲','须专用Task4库，且先完成生命周期两次采集');
  const category=original.switch_category_id;
  const path=(g,suffix='')=>`/switch-topologies/${g.id}${suffix}?lab_profile_id=${lab.id}`;
  const read=g=>call('GET',path(g));
  const patch=(g,data,status=200)=>call('PATCH',path(g),data,status);
  const create=data=>call('POST','/switch-topologies',{lab_profile_id:lab.id,switch_category_id:category,...data},201);
  const clone=structuredClone;
  const pair=(a='in',b='out')=>({from_port:a,to_port:b});
  const node=(id,type,ports,dirs,extra={})=>({id,type,label:type==='ce_port'?'B1.1':id,position:{x:80,y:80},params:{ports,port_directions:dirs,opaque:{keep:id},...extra}});
  const edge=(id,source,target,source_pin='out',target_pin='in',loss=0)=>({id,source,target,source_pin,target_pin,cable_loss_db:loss});
  const base=(name,kind='pad',declared=true)=>({name,nodes:[node('ce','ce_port',['out'],{out:'output'}),
    node('mid',kind,['in','out'],{in:'input',out:'output'},declared?{internal_paths:[pair()]}:{}),
    node('p','probe',['in','ref'],{in:'input',ref:'output'},{probe_id:0,polarization:'V'})],
    connections:[edge('a','ce','mid','out','in',2),edge('b','mid','p')],
    operating_modes:[{id:'mimo_ota',name:'MIMO OTA 测试',active_connections:['a','b']}]});
  const selected=g=>{g.nodes.find(n=>n.id==='p').params.rf_path_selection={connection_ids:['a','b'],switch_mappings:[]};return g;};
  const routes=async(g,scope='simultaneous',status=200)=>{
    // 正式resolver权威是最新更新的active图，不是default。专用库仅保留
    // 本次目标active，避免SQLite同秒排序并列读取另一图；不改生产政策。
    for(;;){const active=(await call('GET',`/switch-topologies?lab_profile_id=${lab.id}&is_active=true&limit=100`)).items.filter(x=>x.id!==g.id);if(!active.length)break;for(const value of active)await patch(value,{is_active:false});}
    await patch(g,{is_active:true,is_default:true});
    return call('GET',`/lab-profiles/${lab.id}/route-calibration-paths?topology_id=${g.id}&operating_mode=mimo_ota&selection_scope=${scope}`,undefined,status);
  };
  const request=(g,r)=>({topology_id:g.id,chain_id:r.chain_id,route_digest:r.route_digest,configuration_digest:r.configuration_digest,
    frequency_mhz:2595,requested_power_dbm:-30,reference_antenna:'Task4隔离软件参考面',receive_cable_loss_db:2,
    receive_cable_source:'非实测软件fixture',fixed_route_confirmed:true,safety_confirmed:true,sample_count:2});
  const batch=(g,chains=['b'])=>({topology_id:g.id,chain_ids:chains,frequencies_mhz:[2595],references:chains.map(c=>({chain_id:c,frequency_mhz:2595,reference_antenna:'Task4隔离参考',receive_cable_loss_db:2,receive_cable_source:'非实测fixture'})),requested_power_dbm:-30,sample_count:2,fixed_route_confirmed:true,safety_confirmed:true});
  const capture=async(g,note)=>{
    await patch(g,{is_default:true});
    const saved=await read(g);
    // 原编辑器只展示最新创建的一行，不按default选图。为展示非最新源图，
    // 真实POST精确的只读展示副本；明确记录两个ID，绝不把副本冒充源行落库。
    const newest=(await call('GET',`/switch-topologies?lab_profile_id=${lab.id}`)).items[0];
    let shown=saved;
    if(newest.id!==saved.id){
      // SQLite创建时间按秒；等到下一真实时刻再POST，避免同秒排序并列。
      const delay=Date.parse(newest.created_at)+1100-Date.now();if(delay>0)await page.waitForTimeout(delay);
      shown=await create(Object.fromEntries(['name','description','version','site_name','system_model','installed_date','installed_by','is_active','nodes','connections','operating_modes'].map(k=>[k,saved[k]])));
    }
    await page.goto(origin);
    await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);
    await page.reload();
    await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
    await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
    await page.getByText(saved.name,{exact:true}).waitFor();
    const saveResponse=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${shown.id}`));
    await page.getByRole('button',{name:'保存拓扑',exact:true}).click();
    const savedResponse=await saveResponse;
    calls.push({row:current,method:'PATCH',path:path(shown),request:savedResponse.request().postDataJSON(),status:savedResponse.status(),response:await savedResponse.json(),origin:'真实UI保存展示对象'});
    eq(savedResponse.status(),200,'展示对象真实UI保存失败');
    await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();
    const displayedAfter=await read(shown);eq(displayedAfter.nodes,shown.nodes,'展示对象UI回传改了原声明');eq(displayedAfter.connections,shown.connections,'展示对象UI回传改了原外边');
    const dom=await page.locator('body').innerText();
    const screenshot=`output/playwright/pc04a4c-task4-${current}.png`;
    await page.screenshot({path:screenshot,fullPage:true,animations:'disabled'});
    const row={id:current,note,topology_id:g.id,display_topology_id:shown.id,saved,displayedAfter,dom,screenshot};rows.push(row);console.log(JSON.stringify({completed:row}));
  };
  current='C01';
  let data={name:'Task4 C01 四种两端器件',nodes:['amplifier','pad','cable','receive_cable'].map((kind,i)=>
    node(`device${i}`,kind,['in','out'],{in:'bidirectional',out:'bidirectional'},{internal_paths:[pair()],gain_db:kind==='amplifier'?0:undefined})),connections:[],operating_modes:[]};
  let g=await create(data),nodes=clone(g.nodes);
  for(const n of nodes.slice(1))n.params.internal_paths.push(pair('out','in'));
  g=await patch(g,{nodes});eq(g.connections,[],'内部声明不生成外边');
  nodes=clone(g.nodes);nodes[0].params.internal_paths.push(pair('out','in'));await patch(g,{nodes},422);
  nodes=clone(g.nodes);nodes[1].params.internal_paths=[];g=await patch(g,{nodes});eq((await read(g)).nodes[1].params.internal_paths,[],'删除没保存');
  nodes=clone(g.nodes);nodes[1].params.internal_paths=[pair(),pair('out','in')];g=await patch(g,{nodes});
  eq(g.nodes[2].params.internal_paths,[pair(),pair('out','in')],'线缆双向必须两行');await capture(g,'PA不能反向并存；pad/cable/receive_cable逐行白名单，保存/删除/恢复精确，外边0');

  current='C02';data=selected(base('Task4 C02 三口合路','combiner'));
  data.nodes[1].params={ports:['in','other','out'],port_directions:{in:'input',other:'input',out:'output'},internal_paths:[pair(),pair('other','out')]};
  data.nodes.push({...node('ce2','ce_port',['out'],{out:'output'}),label:'B1.2'});data.connections.push(edge('other','ce2','mid','out','other'));data.operating_modes[0].active_connections.push('other');
  g=await create(data);eq((await call('GET',path(g,'/paths/mimo_ota'))).map(p=>p.path_id),['ce_to_p'],'未选支路混入');
  eq((await routes(g))[0].connection_ids,['a','b'],'显式选择不是原connection_ids');
  nodes=clone(g.nodes);nodes.find(n=>n.id==='p').params.rf_path_selection.connection_ids=['other','b'];g=await patch(g,{nodes});eq((await routes(g))[0].ce_port,'B1.2','切换支路未生效');
  nodes=clone(g.nodes);nodes.find(n=>n.id==='mid').params.internal_paths=[pair('in','other')];await patch(g,{nodes},422);
  let split=base('Task4 C02 四口分路','combiner');split.nodes[1].params={ports:['in','out','h','unused'],port_directions:{in:'input',out:'output',h:'output',unused:'unknown'},internal_paths:[pair(),pair('in','h')]};
  split.nodes.push(node('ph','probe',['in'],{in:'input'},{probe_id:0,polarization:'H',rf_path_selection:{connection_ids:['a','h'],switch_mappings:[]}}));selected(split);
  split.connections.push(edge('h','mid','ph','h','in'));split.operating_modes[0].active_connections.push('h');
  const splitter=await create(split);eq((await call('GET',path(splitter,'/paths/mimo_ota'))).length,2,'只声明两条分路');await capture(g,'三口合路选中唯一支路；四口分路仅两条pair，不按口数补齐；IN→other拒绝');

  current='C03';data=base('Task4 C03 负载终点','termination');data.nodes[1].params.internal_paths=[];
  g=await create(data);const loadPaths=await call('GET',path(g,'/paths/mimo_ota'));
  check(loadPaths.some(p=>p.path_id==='ce_to_mid')&&!loadPaths.some(p=>p.path_id==='ce_to_p'),'负载可终止但不许中转到探头');
  nodes=clone(g.nodes);nodes[1].params.internal_paths=[pair()];await patch(g,{nodes},422);
  const empty=base('Task4 C03 空白名单');empty.nodes[1].params.internal_paths=[];
  const emptyGraph=await create(empty);eq(await call('GET',path(emptyGraph,'/paths/mimo_ota')),[],'空列表不可通');
  const legacy=await create(base('Task4 C03 旧双端唯一链','pad',false));eq((await call('GET',path(legacy,'/paths/mimo_ota'))).length,1,'R1旧双端链兼容');
  const multi=base('Task4 C03 多口未声明','combiner',false);multi.nodes[1].params.ports.push('third');
  const multiGraph=await create(multi);eq(await call('GET',path(multiGraph,'/paths/mimo_ota')),[],'多口缺字段被全互通');await capture(g,'负载非空422/不穿越；[]不通；白名单旧双端仅唯一链可通，多口缺键不通；BFS补证另存');

  current='C04';data=selected(base('Task4 C04 未知方向草稿'));delete data.nodes[1].params.port_directions;
  g=await create(data);await routes(g,'simultaneous',422);await call('GET',path(g,'/paths/mimo_ota'),undefined,422);
  nodes=clone(g.nodes);nodes[1].params.port_directions={in:'output',out:'input'};await patch(g,{nodes},422);
  let bse={name:'Task4 C04 BSE权威',nodes:[node('bse','bse_port',['dl','ul'],{dl:'input',ul:'input'},{port_roles:{dl:'dl',ul:'ul'},internal_paths:[]})],connections:[],operating_modes:[]};
  await call('POST','/switch-topologies',{...bse,lab_profile_id:lab.id,switch_category_id:category},422);
  const air=original.nodes.find(n=>n.id==='air');check(air.type==='air_path','空气不是物理RF器件');await capture(g,'unknown只允许保存草稿，查询422；明确反向拒绝，BSE dl/ul原权威冲突拒绝；虚拟参考不授物理能力');

  current='C05';g=await create(selected(base('Task4 C05 引用保护')));const before=await read(g);
  for(const fault of ['delete-port','direction','pair']){nodes=clone(g.nodes);const n=nodes[1];if(fault==='delete-port')n.params.ports=['out'];else if(fault==='direction')n.params.port_directions.in='output';else n.params.internal_paths=[];
    await patch(g,{nodes},422);eq(await read(g),before,`${fault}422丢了原图`);}
  nodes=clone(g.nodes);delete nodes[2].params.rf_path_selection;nodes[1].params.internal_paths=[];g=await patch(g,{nodes});eq(g.nodes[1].params.internal_paths,[],'解除路径引用后不能存');await capture(g,'端口/方向/pair被所有引用保护；422未写库；先解除探头路径引用后才可存[]');

  current='C06';g=original;const snapshot=await read(g),listBefore=await call('GET',`/switch-topologies?lab_profile_id=${lab.id}`);
  data=base('不得出现的default');data.is_default=true;data.nodes[1].params.internal_paths=[pair('missing','out')];await call('POST','/switch-topologies',{...data,lab_profile_id:lab.id,switch_category_id:category},422);
  nodes=clone(snapshot.nodes);nodes.find(n=>n.id==='pa').params.internal_paths=[];await patch(g,{nodes,is_default:true,name:'不得写入'},422);
  await patch(g,{operating_modes:[{id:'mimo_ota',active_connections:['unknown-edge']}]},422);
  await call('PATCH',`/switch-topologies/${g.id}?lab_profile_id=${other.id}`,{name:'cross'},409);
  await call('PATCH',`/switch-topologies/${g.id}?lab_profile_id=bad`,{name:'bad'},422);
  await call('POST',`/switch-topologies/import/from-template?switch_category_id=${category}&lab_profile_id=bad&template_id=caict_v4&replace_existing=true`,undefined,422);
  await call('POST',`/switch-topologies/import/from-template?switch_category_id=${category}&lab_profile_id=${lab.id}&template_id=does_not_exist&replace_existing=true`,undefined,404);
  eq(await read(g),snapshot,'拒绝操作改了图');eq(await call('GET',`/switch-topologies?lab_profile_id=${lab.id}`),listBefore,'拒绝操作改行数/default');eq(await call('GET',historyRoot),oldHistory,'拒绝操作改历史');await capture(g,'POST/PATCH部分nodes/模式/import replace错误及跨Lab原子性；GET行数/默认/图/历史不变，ORM另存');

  current='C07';const caict=await call('POST',`/switch-topologies/import/from-template?switch_category_id=${category}&lab_profile_id=${other.id}&template_id=caict_v4`);
  check(caict.nodes.every(n=>!Object.hasOwn(n.params||{},'internal_paths')),'旧CAICT被自动迁移');
  data=base('Task4 C07 旧稀疏JSON','pad',false);data.nodes[1].params.attenuation_db=0;
  g=await create(data);const routeBefore=(await routes(g))[0];
  const edgesBefore=clone(g.connections);nodes=clone(g.nodes);nodes[1].label='仅改名';nodes[1].position={x:361,y:247};nodes[1].params.attenuation_db=0;nodes[1].params.nominal_metadata={attenuation_db:{unit:'dB',source_note:'Task4目录待核',frequency_range_mhz:null}};
  g=await patch(g,{nodes});eq(g.connections,edgesBefore,'无关编辑改了原连接');eq((await routes(g))[0].route_digest,routeBefore.route_digest,'显示/标称改了digest');check(!Object.hasOwn(g.nodes[1].params,'internal_paths'),'旧缺键被补');
  await capture(g,'CAICT真实import缺键保留；旧图改名/位置/标称0/opaque回传不转换、不改route_digest；稀疏pin另见C08');

  current='C08';
  for(const explicit of [true,false])for(const missing of ['incoming','outgoing','both']){
    data=base(`Task4 C08 ${explicit?'声明':'legacy'} ${missing}`,'pad',explicit);
    if(missing!=='outgoing')delete data.connections[0].target_pin;if(missing!=='incoming')delete data.connections[1].source_pin;
    g=await create(data);eq(await call('GET',path(g,'/paths/mimo_ota')),[],'稀疏pin造了完整路径');
    eq((await call('GET',path(g,'/calibration-matrix/mimo_ota'))).matrix,{},'matrix造了path');
    const issues=(await call('GET',path(g,'/validate'))).issues;check(issues.some(i=>i.message.includes('mid')&&(i.message.includes('a')||i.message.includes('b'))),'validate不定位原边');
    const saved=await read(g);check(missing==='outgoing'||!Object.hasOwn(saved.connections[0],'target_pin'),'GET补入pin');check(missing==='incoming'||!Object.hasOwn(saved.connections[1],'source_pin'),'GET补出pin');
    const fixed=clone(saved.connections);fixed[0].target_pin='in';fixed[1].source_pin='out';g=await patch(g,{connections:fixed});eq((await call('GET',path(g,'/paths/mimo_ota'))).length,1,'补真实pin没恢复');
    const matrix=await call('GET',path(g,'/calibration-matrix/mimo_ota'));check(Object.hasOwn(matrix.matrix,'ce_to_p'),'补pin matrix未恢复');
  }
  await capture(g,'显式及R1各缺入pin/出pin/两pin共6组：保存raw缺键、paths空、matrix空、validate原边；补真实pin后恢复。BFS/参考PA及接收线ORM补证');

  current='C10';await routes(splitter,'individual');await routes(splitter,'simultaneous',422);
  await call('POST',`/lab-profiles/${lab.id}/route-calibration-batches/preview`,batch(splitter,['b','h']),422);
  await call('POST',`/lab-profiles/${lab.id}/route-calibration-batches`,{...batch(splitter,['b','h']),preview_digest:'0'.repeat(64)},422);
  await capture(splitter,'individual候选可读；同CE非互斥分路simultaneous/preview/start拒绝，无新作业；预览零HAL补证见ORM/相关测试');

  current='C11';g=original;let saved=await read(g),r=(await routes(g))[0],individual=(await routes(g,'individual'))[0];
  const originalHistory=await call('GET',historyRoot),oldRequest=request(g,r),batchRequest=batch(g,['n4']),preview=await call('POST',`/lab-profiles/${lab.id}/route-calibration-batches/preview`,batchRequest);
  nodes=clone(saved.nodes);let edges=clone(saved.connections);const normalPin=`${nodes.find(n=>n.id==='pa').params.ports[0]}_NEW`;nodes.find(n=>n.id==='pa').params={...nodes.find(n=>n.id==='pa').params,ports:[normalPin,'OUT'],port_directions:{[normalPin]:'input',OUT:'output'},internal_paths:[pair(normalPin,'OUT')]};edges.find(e=>e.id==='n1').target_pin=normalPin;g=await patch(g,{nodes,connections:edges});
  const normalAfter=(await routes(g))[0];check(normalAfter.route_digest!==r.route_digest&&normalAfter.configuration_digest!==r.configuration_digest,'正常pair没有更新摘要');
  await call('POST',historyRoot,oldRequest,422);await call('POST',`/lab-profiles/${lab.id}/route-calibration-batches`,{...batchRequest,preview_digest:preview.preview_digest},422);
  r=normalAfter;individual=(await routes(g,'individual'))[0];nodes=clone(g.nodes);edges=clone(g.connections);const referencePin=`${nodes.find(n=>n.id==='ref').params.ports[0]}_NEW`;nodes.find(n=>n.id==='ref').params={...nodes.find(n=>n.id==='ref').params,ports:[referencePin,'OUT'],port_directions:{[referencePin]:'input',OUT:'output'},internal_paths:[pair(referencePin,'OUT')]};edges.find(e=>e.id==='r2').target_pin=referencePin;g=await patch(g,{nodes,connections:edges});
  const refAfter=(await routes(g))[0],refIndividual=(await routes(g,'individual'))[0];check(refAfter.route_digest!==r.route_digest,'参考pair未改route_digest');eq(refAfter.configuration_digest,r.configuration_digest,'普通scope不得包含参考段');check(refIndividual.configuration_digest!==individual.configuration_digest,'selected scope未包含参考变更');
  await call('POST',historyRoot,request(g,r),422);eq(await call('GET',historyRoot),originalHistory,'新声明改了旧run');
  for(const run of originalHistory){const p=await call('GET',`${historyRoot}/${run.run_id}/application-preview`);eq(p.eligibility.eligible_for_adoption,false,'Mock不可采用');}
  await capture(g,'正常pair普通摘要变化；参考pair普通scope不扩张但route/selected摘要变化；旧请求/preview422，旧两run逐字保持，Mock不获采用资格');

  current='C16';data=selected(base('Task4 C16 两端unknown'));data.nodes[1].params.port_directions={in:'unknown',out:'unknown'};g=await create(data);
  const countBefore=await call('GET',historyRoot);await routes(g,'individual',422);
  await call('POST',historyRoot,{...oldRequest,topology_id:g.id,chain_id:'b'},422);eq(await call('GET',historyRoot),countBefore,'unknown创建job');
  nodes=clone(g.nodes);nodes[1].params.port_directions={in:'input',out:'output'};g=await patch(g,{nodes});await routes(g,'individual');
  eq(await call('GET',historyRoot),countBefore,'声明方向擅自创建job');
  const finalHistory=await call('GET',historyRoot);for(const run of finalHistory){eq(run.formal_eligible,false,'Mock给资格');eq(run.result.net_loss_db,null,'Mock给正式量值');eq(run.result.samples,[],'Mock造样本');}
  await capture(g,'unknown草稿可保存但路径/采集422无job；明确方向可解析，实际Mock两次采集见C15；缺绑定及采用拒绝由补证覆盖');
  return {boundary:'仅隔离软件验证；无CE/OTA执行，无真实RF/资格结论',labs,original_topology_id:original.id,rows,calls,history:finalHistory};
  } catch(error) { return {failed:true,current,error:String(error.stack||error),rows,calls}; }
}
