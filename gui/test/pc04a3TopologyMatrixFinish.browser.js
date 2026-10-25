// 承接真实原生确认之后，验证删除原子清理及真实持久化。
async page=>{
  const pending=await page.evaluate(()=>window.__pc04a3MatrixPending);if(!pending)throw new Error('缺少矩阵上下文');
  const api=`${new URL(page.url()).origin}/api/v1`,{id,edgeId,endpoint,topologyId}=pending;
  await page.getByRole('dialog').waitFor({state:'hidden'});
  if(await page.locator(`.react-flow__node[data-id="${id}"]`).count()||await page.locator(`.react-flow__edge[data-id="${edgeId}"]`).count())throw new Error('删除未清理真实画布');
  const response=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().includes(`/switch-topologies/${topologyId}`));await page.getByRole('button',{name:'保存拓扑',exact:true}).click();const r=await response;if(!r.ok())throw new Error(await r.text());
  const saved=await(await page.request.get(`${api}${endpoint}`)).json();
  if(saved.nodes.some(n=>n.id===id)||saved.connections.some(e=>e.id===edgeId)||saved.operating_modes.some(m=>m.active_connections.includes(edgeId)))throw new Error('删除后服务器仍有节点/边/模式引用');
  await page.reload();await page.getByRole('tab',{name:'实验室配置',exact:true}).click();await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.locator('.react-flow').first().waitFor();
  if(await page.locator(`.react-flow__node[data-id="${id}"]`).count())throw new Error('刷新后删除节点恢复');
  const result={...pending,checks:[...pending.checks,'无引用删除真实确认，清节点/关联边/所有模式，保存GET/reload保持'],passed:true};
  await page.evaluate(result=>{window.__pc04a3MatrixResult=result},result);return result;
}
