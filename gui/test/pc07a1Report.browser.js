// 真实隔离API，全Mock；不拦截/伪造网络响应。通过 playwright-cli run-code 运行。
async page => {
  page.setDefaultTimeout(15000);
  const api = 'http://127.0.0.1:18089/api/v1';
  const output = `output/playwright/pc07a1-task3-${Date.now()}`;
  const evidence = [];
  const json = async (method, path, data) => {
    const response = await page.request[method](`${api}${path}`, data ? {data} : undefined);
    const body = await response.json();
    evidence.push({method, path, request: data ?? null, status: response.status(), body});
    if (!response.ok()) throw new Error(JSON.stringify(evidence.at(-1)));
    return body;
  };
  const hal = await json('get', '/instruments/hal/status');
  if (hal.mode !== 'mock' || hal.driver_count !== 2) throw new Error('必须为隔离全Mock HAL');
  const list = await json('get', '/reports');
  const report = list.reports.find(r => r.title === 'PC07A1 合成真实来源历史（非真机认证）');
  const old = list.reports.find(r => r.title === 'PC07A1 旧无键报告');
  if (!report || !old) throw new Error('必须使用专属隔离种子');
  const before = await json('get', `/reports/${report.id}`);
  const original = before.content_data.calibration_traceability;
  if (original.execution_frequency_mhz !== 2595 || new Set(original.routes.map(r => r.source_kind)).size !== 2)
    throw new Error('历史必须混合新旧来源');
  await json('get', `/reports/${old.id}`);
  for (let i = 0; i < 2; i++) {
    const result = await json('post', `/reports/${report.id}/generate`);
    if (result.status !== 'completed' || JSON.stringify(result.content_data.calibration_traceability) !== JSON.stringify(original))
      throw new Error('生成/重建漂移');
    const detail = await json('get', `/reports/${report.id}`);
    if (detail.content_data.overall_result === 'passed' || detail.content_data.formal_quiet_zone_verified)
      throw new Error('合成来源历史不得成为认证PASS');
  }
  await page.goto('http://127.0.0.1:5197');
  await page.getByRole('tab', {name:'数据归档与报告',exact:true}).click();
  await page.getByRole('tab', {name:'我的报告',exact:true}).click();
  const row = page.getByRole('row').filter({hasText: report.title});
  await row.waitFor();
  await page.screenshot({path:`${output}/list.png`, fullPage:true});
  // 图标无accessible name，按真实图标身份定位已存在的详情按钮。
  await row.locator('button').filter({has: page.locator('svg.tabler-icon-eye')}).click();
  const panel = page.getByTestId('calibration-traceability');
  await panel.waitFor();
  const text = await panel.innerText();
  for (const route of original.routes) if (!text.includes(route.source_id)) throw new Error('页面丢失原来源');
  if (!text.includes('原始读数未内嵌') || text.includes('认证通过')) throw new Error('页面错误认证/原始读数声明');
  // 等待真实弹窗过渡完成，截图不捕获半透明过渡帧。
  await page.waitForTimeout(350);
  await page.screenshot({path:`${output}/detail.png`,fullPage:true});
  await page.getByRole('dialog').getByRole('button').first().click();
  const downloaded = page.waitForEvent('download');
  await row.locator('button').filter({has:page.locator('svg.tabler-icon-download')}).click();
  const download = await downloaded;
  await download.saveAs(`${output}/downloaded.pdf`);
  // 与合成真实来源历史严格分开：真实API实际全Mock采集不得产出正式数值。
  const lab = (await json('get','/lab-profiles')).find(l => l.id === before.content_data.lab_profile_id) ?? (await json('get','/lab-profiles'))[0];
  const scope = await json('get',`/lab-profiles/${lab.id}/calibration-scope`);
  const run = await json('post',`/lab-profiles/${lab.id}/fixed-route-acquisitions`, {
    chain_id:'conn_p0v', configuration_digest:scope.digest, frequency_mhz:2595,
    requested_power_dbm:-20, reference_antenna:'PC07A1 实际Mock采集，不是历史来源',
    receive_cable_loss_db:2,receive_cable_source:'隔离Mock', fixed_route_confirmed:true,safety_confirmed:true,sample_count:2,
  });
  let measured;
  for(let i=0;i<100;i++) {
    measured=await json('get',`/lab-profiles/${lab.id}/fixed-route-acquisitions/${run.run_id}`);
    if(measured.status!=='running') break;
    await page.waitForTimeout(50);
  }
  if(measured.status!=='simulated' || measured.result.net_loss_db!==null || measured.result.formal_eligible!==false || measured.result.samples.length)
    throw new Error('Mock数据被提升为实测');
  const preview=await json('get',`/lab-profiles/${lab.id}/fixed-route-acquisitions/${run.run_id}/application-preview`);
  if(preview.eligibility.eligible_for_adoption || preview.new_net_loss_db!==null) throw new Error('Mock被允许采用');
  await json('post',`/reports/${old.id}/generate`);
  await json('get',`/reports/${old.id}`);
  await page.evaluate(evidence=>{window.__pc07a1Evidence=evidence},evidence);
  return {passed:8,output,report_id:report.id,old_id:old.id,mock_run:run.run_id,evidence};
}
