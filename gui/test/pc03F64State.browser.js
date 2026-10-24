// 真实浏览器→真实FastAPI→临时SQLite；启动环境必须为七类全部Mock，不拦截任何HTTP。
async (page) => {
  page.setDefaultTimeout(10000);
  const api = 'http://127.0.0.1:18080/api/v1';
  const checks = [];
  const status = await (await page.request.get(`${api}/instruments/hal/status`)).json();
  const readiness = await (await page.request.get(`${api}/instruments/hal/readiness`)).json();
  if (status.mode !== 'mock' || status.driver_count !== 7 || readiness.drivers.some(d => !d.detail.startsWith('Mock'))) throw new Error('必须全部为Mock');
  checks.push('七类驱动全部Mock');
  const catalog = await (await page.request.get(`${api}/instruments/catalog`)).json();
  const ce = catalog.categories.find(c => c.key === 'channelEmulator');
  if (!ce || !ce.connection.endpoint || ce.models.find(m => m.id === ce.selectedModelId)?.model !== 'PROPSIM F64') throw new Error('测试环境未明确配置F64');
  const labs = [];
  for (const suffix of ['甲', '乙']) {
    const name = `PC03-${Date.now()}-${suffix}`;
    const chamber = await (await page.request.post(`${api}/chambers`, { data: { name, chamber_radius_m: 4, num_probes: 2, num_rings: 1 } })).json();
    const result = await page.request.post(`${api}/lab-profiles`, {data: {name, chamber_config_id: chamber.id, instrument_bindings: [{category_id: ce.categoryId, instrument_model_id: ce.selectedModelId, connection_endpoint: ce.connection.endpoint, driver_mode: 'mock', role: 'primary_channel_emulator'}]}});
    if (!result.ok()) throw new Error(await result.text());
    labs.push(await result.json());
  }
  await page.goto('http://127.0.0.1:5187');
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), labs[0].id);
  await page.reload();
  await page.getByRole('tab', {name: '实验室配置', exact: true}).click();
  const card = page.getByTestId('f64-calibration-state');
  await card.waitFor();
  for (const label of ['信道组编号', '物理输入口编号', '物理输出口编号']) {
    if (await card.getByLabel(`${label} *`, {exact:true}).inputValue()) throw new Error('不应预设编号');
  }
  checks.push('三个编号无猜测默认值');
  for (const [label,value] of [['信道组编号','2'],['物理输入口编号','1'],['物理输出口编号','3']]) await card.getByLabel(`${label} *`,{exact:true}).fill(value);
  const wait = page.waitForResponse(r => r.url().endsWith('/f64-calibration-state') && r.request().method() === 'POST');
  await card.getByRole('button',{name:'读取 F64 状态',exact:true}).click();
  const response = await wait;
  const record = await response.json();
  if (response.status() !== 200 || record.state?.acquisition_status !== 'simulated' || record.state.formal_eligible !== false || record.state.fields.some(f => f.status !== 'simulated' || f.value !== null || f.raw !== null)) throw new Error(JSON.stringify(record));
  await card.getByTestId('f64-current-result').getByText('模拟记录，不含真实仪器读数',{exact:true}).waitFor();
  checks.push('真实POST返回模拟标记且不编造读数');
  const history = await (await page.request.get(`${api}/lab-profiles/${labs[0].id}/f64-calibration-state`)).json();
  if (history[0]?.diagnostic_run_id !== record.diagnostic_run_id || history[0].state.binding_digest !== record.state.binding_digest) throw new Error('审计持久化失败');
  checks.push('真实数据库历史保留同一记录与配置标识');
  await card.getByLabel('物理输出口编号 *',{exact:true}).fill('4');
  if (await card.getByTestId('f64-current-result').count()) throw new Error('改编号后仍显示旧读取结果');
  checks.push('修改编号清除本次旧结果，历史仍单独可查');
  await card.scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/playwright/pc03-mock-state.png',fullPage:true});
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option').filter({hasText:labs[1].name}).click();
  await card.getByLabel('信道组编号 *',{exact:true}).waitFor();
  if (await card.getByLabel('信道组编号 *',{exact:true}).inputValue() !== '') throw new Error('跨实验室沿用输入');
  await card.getByText('尚无读取记录。',{exact:true}).waitFor();
  checks.push('切换实验室清空输入，历史按实验室隔离');
  await page.reload();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  await card.getByText('尚无读取记录。',{exact:true}).waitFor();
  checks.push('页面重载不把其他实验室记录当作当前状态');
  return {passed:checks.length,checks,lab_ids:labs.map(l=>l.id),record_id:record.diagnostic_run_id};
}
