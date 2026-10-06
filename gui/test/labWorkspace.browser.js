// playwright_cli.sh -s=p283a run-code --filename gui/test/labWorkspace.browser.js
// 真实App与上下文；仅隔离HTTP/WS transport，不连接生产仪器或写生产库。
async (page) => {
  page.setDefaultTimeout(5000);
  await page.context().setOffline(false);
  const labA = '11111111-1111-4111-8111-111111111111';
  const labB = '22222222-2222-4222-8222-222222222222';
  let mode = 'ok';
  const writes = [];
  const reads = [];
  const labs = [labA, labB].map((id, i) => ({ id, name: `实验室${i ? '乙' : '甲'}`,
    is_active: true, chamber_config_id: `chamber-${i}`, chamber_name: `暗室${i ? '乙' : '甲'}` }));
  const binding = (id, category) => ({ status: 'configured', binding_digest: `digest-${id}`,
    execution_mode: 'simulated', adapter_id: `adapter-${id}-${category}`, model_name: `型号-${category}`,
    category_id: category, instrument_model_id: null, instrument_connection_id: null,
    lab_profile_id: id, resolved_binding: null, runtime_driver: null, detail: '模拟诊断绑定',
    testcase_compatibility: null, selected_asset_id: null });
  const readiness = (id) => ({ available: false, drivers: [],
    lab_profile: { profile_id: id, profile_name: labs.find(l => l.id === id).name,
      is_active: true, status: 'ok', detail: '实验室配置已解析' },
    calibration: { certificate_number: null, valid_until_iso: null, status: 'missing', days_remaining: null, detail: '未校准' },
    dut_attach: { status: 'not_implemented', detail: '未实现' },
    base_station_binding: binding(id, 'baseStation'), channel_emulator_binding: binding(id, 'channelEmulator'),
    base_station_testcase_compatibility: { schema_version: 1, status: 'not_evaluated', compatible: null,
      test_case_id: null, lab_profile_id: id, binding_digest: null, execution_mode: null,
      requirements: null, verdict: null, reasons: [], detail: '未选择用例' },
    base_station_site_certification: null, base_station_site_certification_status: 'missing',
    base_station_site_certification_error: null, channel_emulator_site_certification_preview: null,
    cmw500_lte_2x2: null, generated_at_iso: '2026-10-06T11:00:00Z', subnets: [] });
  await page.unrouteAll();
  await page.routeWebSocket('**/api/v1/ws/**', () => {});
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() !== 'GET' && !path.endsWith('/system-logs/frontend')) writes.push(path);
    if (path.endsWith('/lab-profiles')) return route.fulfill({ json: labs });
    if (path.endsWith('/instruments/hal/readiness')) {
      const id = url.searchParams.get('lab_profile_id');
      reads.push(id);
      if (mode === 'error') return route.fulfill({ status: 503, json: { detail: '回归读取失败' } });
      const value = readiness(id || labA);
      if (mode === 'wrong') value.lab_profile.profile_id = labA;
      if (mode === 'nestedWrong') value.base_station_binding.lab_profile_id = labA;
      if (mode === 'missing') {
        value.base_station_binding = null;
        value.channel_emulator_binding = null;
      }
      return route.fulfill({ json: value });
    }
    if (path.endsWith('/rf-chains')) {
      const id = path.split('/').at(-2);
      if (mode === 'rfError') return route.fulfill({ status: 503, json: { detail: '链路读取失败' } });
      return route.fulfill({ json: { lab_profile_id: mode === 'rfWrong' ? labA : id, lab_name: '测试实验室',
        chamber_id: labs.find(l => l.id === id).chamber_config_id, chamber_name: '服务器暗室', topology_id: null,
        topology_name: null, operating_mode: 'mimo_ota', chains: [], warnings: ['拓扑尚未配置'], success: false } });
    }
    if (path.endsWith('/instruments/catalog')) return route.fulfill({ json: { categories: [{
      categoryId: '33333333-3333-4333-8333-333333333333', key: 'vna', label: '回归网络分析仪',
      description: '', tags: [], isActive: true, selectedModelId: null, usagePhase: [], driverMode: 'real', models: [],
      connection: { id: '44444444-4444-4444-8444-444444444444', endpoint: 'server-endpoint',
        controller: 'LAN', notes: '', connection_params: {}, invalid_fields: {},
        cmw500_lte_2x2_formal_enabled: false, cmw500_lte_2x2_formal_updated_at: null,
        base_station_site_certification: null, channel_emulator_site_certification: null,
        base_station_model_presets: {}, channel_emulator_model_presets: {} },
    }] } });
    if (path.endsWith('/system-logs/frontend')) return route.fulfill({ json: {} });
    return route.fulfill({ status: 503, json: { detail: '隔离测试未配置此只读接口' } });
  });
  await page.goto('http://127.0.0.1:5198');
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), labA);
  await page.reload();
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click({ timeout: 5000 });
  await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).waitFor();
  if (await page.locator('nav').getByRole('tab', { name: '仪器资源配置', exact: true }).count()) {
    throw new Error('旧主入口仍重复展示');
  }
  await page.getByText('仅诊断', { exact: true }).first().waitFor();
  await page.getByText('HAL尚未初始化', { exact: true }).waitFor();
  await page.getByText('用例兼容性未评估', { exact: false }).waitFor();
  await page.context().setOffline(true);
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText('配置快照读取暂停', { exact: false }).waitFor();
  if (await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).count()) throw new Error('离线暂停时仍展示旧成功快照');
  await page.getByText('射频链路读取暂停', { exact: false }).waitFor();
  await page.context().setOffline(false);
  await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).waitFor();
  mode = 'error';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText('配置快照读取失败', { exact: false }).waitFor();
  if (await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).count()) throw new Error('失败后仍展示旧成功快照');
  mode = 'ok';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).waitFor();
  await page.getByRole('textbox', { name: '当前 LabProfile', exact: true }).click();
  await page.getByRole('option').filter({ hasText: '实验室乙' }).click();
  await page.getByText(`adapter-${labB}-baseStation`, { exact: true }).waitFor();
  if (await page.getByText(`adapter-${labA}-baseStation`, { exact: true }).count()) throw new Error('切换实验室保留错误数据');
  for (const invalidMode of ['wrong', 'nestedWrong']) {
    mode = invalidMode;
    await page.getByRole('button', { name: '刷新总览', exact: true }).click();
    await page.getByText('响应实验室身份不一致', { exact: false }).waitFor();
    if (await page.getByText(`adapter-${labB}-baseStation`, { exact: true }).count()) throw new Error('响应分叉仍展示成功');
  }
  mode = 'ok';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText(`adapter-${labB}-baseStation`, { exact: true }).waitFor();
  mode = 'rfWrong';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText('射频响应实验室身份不一致', { exact: false }).waitFor();
  mode = 'rfError';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText('射频链路读取失败', { exact: false }).waitFor();
  mode = 'missing';
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await page.getByText('服务器未返回绑定投影', { exact: true }).first().waitFor();
  mode = 'ok';
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).waitFor();
  await page.getByRole('tab', { name: '探头与暗室', exact: true }).click();
  await page.getByRole('tab', { name: '射频拓扑', exact: true }).click();
  await page.getByRole('heading', { name: '射频开关矩阵拓扑', exact: true }).waitFor();
  await page.getByText('或在「实验室配置 → 仪器资源」中添加 RF Switch 类别。', { exact: false }).waitFor();
  await page.getByRole('tab', { name: '总览', exact: true }).click();
  await page.getByText(`adapter-${labB}-baseStation`, { exact: true }).waitFor();
  if (writes.length) throw new Error(`工作台产生非预期写入: ${writes}`);
  if (!reads.includes(labA) || !reads.includes(labB)) throw new Error('请求未带显式Lab上下文');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  await page.getByText('未选择时不读取实验室总览', { exact: false }).waitFor();
  const readCount = reads.length;
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).waitFor();
  await page.getByRole('tab', { name: '总览', exact: true }).click();
  await page.getByText('未选择时不读取实验室总览', { exact: false }).waitFor();
  if (reads.length !== readCount) throw new Error('未选择实验室时发出了readiness请求');
  console.log('PASS: 统一导航、模拟诊断、HAL缺失、未评估、刷新失败、Lab切换、顶层/嵌套身份拒绝、零配置写入');
  return { passed: 14, reads, writes };
}
