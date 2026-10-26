// C09/C12及参考补证：同一真实最新图重载、UI保存、GET，不替换网络。
async page=>{
  const url=new URL(page.url()),row=url.searchParams.get('matrixCapture'),name=url.searchParams.get('matrixName'),origin=url.origin,api=`${origin}/api/v1`;
  page.setDefaultTimeout(15000);await page.setViewportSize({width:1800,height:1100});
  const lab=(await(await page.request.get(`${api}/lab-profiles`)).json()).find(x=>x.name==='PC04A4c内部通路甲');
  const graph=(await(await page.request.get(`${api}/switch-topologies?lab_profile_id=${lab.id}`)).json()).items[0];
  if(graph.name!==name)throw Error(`最新图不是目标${name}: ${graph.name}`);
  const endpoint=`${api}/switch-topologies/${graph.id}?lab_profile_id=${lab.id}`;
  await page.goto(origin);await page.evaluate(id=>localStorage.setItem('mimo.operationalLabProfileId',id),lab.id);await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.getByText(name,{exact:true}).waitFor();
  const pending=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${graph.id}`));
  await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const response=await pending;
  if(response.status()!==200)throw Error(await response.text());
  await page.getByTestId('topology-save-stage').filter({hasText:'拓扑已保存到服务器'}).waitFor();
  const saved=await(await page.request.get(endpoint)).json();
  for(const key of ['nodes','connections','operating_modes'])if(JSON.stringify(saved[key])!==JSON.stringify(graph[key]))throw Error(`UI改变${key}`);
  const dom=await page.locator('body').innerText(),screenshot=`output/playwright/pc04a4c-task4-${row}.png`;
  await page.screenshot({path:screenshot,fullPage:true,animations:'disabled'});
  return {row,topology_id:graph.id,request:response.request().postDataJSON(),status:response.status(),response:await response.json(),saved,dom,screenshot};
}
