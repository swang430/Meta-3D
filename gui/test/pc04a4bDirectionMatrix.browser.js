// 全16组合：真实API、实际鼠标、真实DOM候选约束；不伪造响应。
async page=>{
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1200});
  const origin=new URL(page.url()).origin,api=`${origin}/api/v1`,results=[],exchanges=[];
  const eq=(a,b,message)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(`${message}: ${JSON.stringify(a)}`)};
  const get=async path=>{const r=await page.request.get(`${api}${path}`);if(!r.ok())throw Error(await r.text());return r.json()};
  eq((await get('/instruments/hal/status')).mode,'mock','仅允许Mock');
  const lab=(await get('/lab-profiles')).find(l=>l.name==='PC04A4b端口甲'),base=(await get(`/switch-topologies?lab_profile_id=${lab.id}&limit=100`)).items[0];
  const directions=['input','output','bidirectional','unknown'];
  for(const source of directions)for(const target of directions){
    // SQLite创建时间精度为秒；让连续无边fixture拥有严格较新的时间，不改服务器排序或历史行。
    const latest=(await get(`/switch-topologies?lab_profile_id=${lab.id}&limit=1`)).items[0];
    await page.waitForFunction(stamp=>Date.now()>stamp,Date.parse(latest.created_at)+1000,{polling:50});
    const allowed=source!=='input'&&target!=='output',body={name:`PC04A4bUI方向-${source}-${target}`,lab_profile_id:lab.id,switch_category_id:base.switch_category_id,nodes:[
      {id:'a',type:'pad',label:'源',position:{x:80,y:100},params:{ports:['P','Q'],port_directions:{P:source,Q:source},visible_modes:['mimo_ota']}},
      {id:'b',type:'pad',label:'目标',position:{x:700,y:100},params:{ports:['I','J'],port_directions:{I:target,J:target},visible_modes:['mimo_ota']}}],connections:[],operating_modes:[{id:'mimo_ota',name:'MIMO OTA 测试',active_connections:[]}]};
    const r=await page.request.post(`${api}/switch-topologies`,{data:body});eq(r.status(),201,'无边图POST');const graph=await r.json();exchanges.push({method:'POST',body,response:graph});
    await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();
    await page.getByText(graph.name,{exact:true}).waitFor();await page.locator('.react-flow__node[data-id="b"] .react-flow__handle[data-handleid="I"]').first().waitFor();
    await page.getByRole('button',{name:'Fit View',exact:true}).click();await page.waitForFunction(()=>new Promise(resolve=>{let same=0,last='';const tick=()=>{const now=document.querySelector('.react-flow__viewport')?.getAttribute('style');same=now===last?same+1:0;last=now;if(same>5)resolve(true);else requestAnimationFrame(tick)};tick()}));
    const a=page.locator('.react-flow__node[data-id="a"] .source[data-handleid="P"]'),b=page.locator('.react-flow__node[data-id="b"] .target[data-handleid="I"]');
    eq(await a.count(),source==='input'?0:1,'source方向handle');eq(await b.count(),target==='output'?0:1,'target方向handle');
    const url=`${api}/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
    if(allowed){
      const left=await a.boundingBox(),right=await b.boundingBox();await page.mouse.move(left.x+left.width/2,left.y+left.height/2);await page.mouse.down();await page.mouse.move(right.x+right.width/2,right.y+right.height/2,{steps:15});await page.mouse.up();
      const edge=page.locator('.react-flow__edge').first();await edge.waitFor({state:'attached'});const path=edge.locator('.react-flow__edge-path');
      eq(Boolean(await path.getAttribute('marker-end')),source!=='unknown'&&target!=='unknown','箭头误证未知方向');
      const center=await path.evaluate(p=>{const q=p.getPointAtLength(p.getTotalLength()/2),m=p.getScreenCTM();return{x:m.a*q.x+m.c*q.y+m.e,y:m.b*q.x+m.d*q.y+m.f}});await page.mouse.click(center.x,center.y);const dialog=page.getByRole('dialog',{name:'连线参数编辑',exact:true});await dialog.waitFor();
      await page.getByRole('textbox',{name:'源端口',exact:true}).click();const sourceOptions=await page.getByRole('listbox').getByRole('option').allTextContents();eq(sourceOptions.length,2,'同方向源ID被合并');await page.keyboard.press('Escape');
      await page.getByRole('textbox',{name:'目标端口',exact:true}).click();const targetOptions=await page.getByRole('listbox').getByRole('option').allTextContents();eq(targetOptions.length,2,'同方向目标ID被合并');await page.keyboard.press('Escape');
      await page.getByRole('button',{name:'取消',exact:true}).click();await dialog.waitFor({state:'hidden'});await page.locator('.mantine-Drawer-overlay').waitFor({state:'hidden'});
      const response=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(graph.id));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const saved=await response;eq(saved.status(),200,'合法拖线保存');exchanges.push({method:'UI PATCH',body:saved.request().postDataJSON(),response:await saved.json()});
      const stored=await get(`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`);eq(stored.connections[0].source_pin,'P','原sourceID');eq(stored.connections[0].target_pin,'I','原targetID');results.push({source,target,allowed,sourceOptions,targetOptions,stored});
    }else{
      const patch={connections:[{id:'illegal',source:'a',source_pin:'P',target:'b',target_pin:'I'}]},response=await page.request.patch(url,{data:patch});eq(response.status(),422,'直接PATCH绕GUI');const rejected=await response.json(),stored=await get(`/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`);eq(stored,graph,'拒绝污染原行');eq(await page.locator('.react-flow__edge').count(),0,'禁止组合出现线');exchanges.push({method:'PATCH',body:patch,status:422,response:rejected});results.push({source,target,allowed,missingRequiredHandle:true,stored});
    }
    await page.screenshot({path:`output/playwright/pc04a4b-direction-${source}-${target}.png`,fullPage:true,animations:'disabled'});
  }
  return {results,exchanges,counts:{combinations:16,allowed:results.filter(r=>r.allowed).length,rejected:results.filter(r=>!r.allowed).length}};
}
