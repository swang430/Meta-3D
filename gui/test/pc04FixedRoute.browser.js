// 真实浏览器→真实Vite/FastAPI→独立临时SQLite；不拦截HTTP，不连接现场仪器。
async (page) => {
  page.setDefaultTimeout(10000);
  const api = 'http://127.0.0.1:18080/api/v1';
  const checks = [];
  const status = await (await page.request.get(`${api}/instruments/hal/status`)).json();
  const readiness = await (await page.request.get(`${api}/instruments/hal/readiness`)).json();
  if (status.mode !== 'mock' || readiness.drivers.some(d => !d.detail.startsWith('Mock'))) throw new Error('必须全Mock');
  checks.push('真实HAL全部Mock');
  const labs = await (await page.request.get(`${api}/lab-profiles`)).json();
  const labA = labs.find(l => l.name === 'PC04自动采集甲');
  const labB = labs.find(l => l.name === 'PC04自动采集乙');
  if (!labA || !labB) throw new Error('临时实验室缺失');
  // 临时HAL启动可能恢复saved preset；通过真实独立同步入口更新测试实验室绑定。
  for (const lab of [labA,labB]) for (const category of ['channelEmulator','signalAnalyzer']) {
    const catalog = await (await page.request.get(`${api}/instruments/catalog`)).json();
    const configured = catalog.categories.find(c=>c.key===category);
    const synced = await page.request.put(`${api}/lab-profiles/${lab.id}/instrument-bindings/${category}/sync-current`,
      {data:{expected_saved_configuration_digest:configured.savedConfigurationDigest}});
    if (!synced.ok()) throw new Error(await synced.text());
  }
  await page.goto('http://127.0.0.1:5187');
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), labA.id);
  await page.reload();
  await page.getByRole('tab', {name:'实验室配置',exact:true}).click();
  const card = page.getByTestId('fixed-route-acquisition');
  await card.getByRole('heading',{name:'固定通路自动采集（PC-04A）'}).waitFor();
  await card.getByLabel('采集链路',{exact:false}).click();
  await page.getByRole('option').filter({hasText:'fixed-v'}).click();
  await card.getByText('F64输出口：B1.1', {exact:false}).waitFor();
  checks.push('已有链路自动带出F64端口及极化');
  for (const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-20'],
    ['参考天线身份','SN-REF 临时Mock参考天线 静区中心V'],['接收线缆损耗','2'],
    ['接收线缆记录来源','SN-CABLE 2595MHz临时软件验证资料']]) {
    await card.getByLabel(label,{exact:false}).fill(value);
  }
  if (await card.getByRole('textbox', {name:'F64输出口实测功率'}).count()) throw new Error('不应要求手填功率');
  if (await card.getByRole('button',{name:'开始自动采集',exact:true}).isEnabled()) throw new Error('未确认安全仍可发射');
  checks.push('不提供两端功率手填入口，安全确认前禁用开始');
  await card.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();
  await card.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();
  const wait = page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions') && r.request().method()==='POST');
  await card.getByRole('button',{name:'开始自动采集',exact:true}).click();
  const response = await wait;
  if (response.status() !== 202) throw new Error(await response.text());
  const created = await response.json();
  await card.getByText('模拟流程完成（无真实测量）',{exact:true}).first().waitFor();
  const history = await (await page.request.get(`${api}/lab-profiles/${labA.id}/fixed-route-acquisitions`)).json();
  const first = history.find(r=>r.run_id===created.run_id);
  if (first?.result?.status!=='simulated' || first.result.samples.length || first.result.net_loss_db!==null
    || first.result.formal_eligible!==false || first.result.exchanges.some(e=>!e.simulated||e.response!==null)) throw new Error(JSON.stringify(first));
  if (!first.result.exchanges.some(e=>e.command==='OUTPut:MEASure:RESult:GET? 1,1')) throw new Error('未共用实测命令');
  await card.getByText('整条路径损耗或增益：未计算',{exact:true}).waitFor();
  checks.push('真实POST和数据库记录均为模拟，功率/损耗为空且无正式资格');
  const wait2 = page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions') && r.request().method()==='POST');
  await card.getByRole('button',{name:'开始自动采集',exact:true}).click();
  const created2 = await (await wait2).json();
  await card.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();
  await card.getByText('已取消',{exact:true}).first().waitFor();
  const cancelled = await (await page.request.get(`${api}/lab-profiles/${labA.id}/fixed-route-acquisitions/${created2.run_id}`)).json();
  if (cancelled.status!=='cancelled' || cancelled.result.net_loss_db!==null) throw new Error(JSON.stringify(cancelled));
  checks.push('第二次运行及服务器取消成功，未把请求取消当作真实停发证明');
  await card.scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/playwright/pc04-mock-acquisition.png',fullPage:true});
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await card.getByText('模拟流程完成（无真实测量）',{exact:false}).first().waitFor();
  checks.push('刷新页面保留本实验室历史');
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option').filter({hasText:labB.name}).click();
  await card.getByText('暂无自动采集记录。',{exact:true}).waitFor();
  if (await card.getByLabel('采集频率',{exact:false}).inputValue()) throw new Error('跨实验室沿用输入');
  checks.push('切换实验室清空输入，历史不串用');
  await page.getByRole('tab',{name:'调试序列 + 单阶段',exact:true}).click();
  const evidenceResponse = page.waitForResponse(r=>r.url().includes('/diagnostic-runs/') && r.request().method()==='GET');
  await page.locator('code').filter({hasText:/^fixed_route_power_acquisition$/}).first().locator('..').getByRole('button',{name:'查看完整证据'}).click();
  const detail = await evidenceResponse;
  if (!detail.ok()) throw new Error(await detail.text());
  const shared = (await detail.json()).sequence_evidence;
  if (!shared?.extra?.fixed_route_acquisition || !['UNDETERMINED','ABORTED'].includes(shared.extra.verdict)) throw new Error(JSON.stringify(shared));
  await page.getByRole('heading',{name:'历史完整证据',exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/pc04-shared-diagnostic-evidence.png',fullPage:true});
  checks.push('共享调试序列历史可打开采集完整证据，不报500且不显示模拟正式通过');
  return {passed:checks.length,checks,run_ids:[created.run_id,created2.run_id],lab_ids:[labA.id,labB.id]};
}
