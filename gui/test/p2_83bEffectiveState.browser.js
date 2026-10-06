// Real App flow; only HTTP/WS transport is substituted, never hardware.
async (page) => {
  page.setDefaultTimeout(15000);
  await page.context().setOffline(false);
  let saveFails = true;
  let activationStatus = 'error';
  let activations = 0;
  let catalogFails = false;
  let holdActivation = false;
  let releaseActivation;
  let runtimeMode = 'real';
  const reviewFailures = [];
  const reviewCheck = async (name, check) => {
    try { await check(); } catch (error) { reviewFailures.push(`${name}: ${error.message}`); }
  };
  const labId = '11111111-1111-4111-8111-111111111111';
  const category = {
    categoryId: '22222222-2222-4222-8222-222222222222', key: 'vna', label: '阶段测试仪器',
    description: '', tags: [], isActive: true, selectedModelId: null,
    usagePhase: [], driverMode: 'real', models: [],
    connection: { id: '33333333-3333-4333-8333-333333333333', endpoint: 'saved-endpoint',
      controller: 'LAN', notes: '', connection_params: {}, invalid_fields: {},
      cmw500_lte_2x2_formal_enabled: false, base_station_site_certification: null,
      channel_emulator_site_certification: null, base_station_model_presets: {}, channel_emulator_model_presets: {} },
  };
  const simulatedCategory = { ...category, key: 'baseStation', label: '模拟基站',
    categoryId: '55555555-5555-4555-8555-555555555555',
    connection: { ...category.connection, id: '66666666-6666-4666-8666-666666666666', endpoint: 'simulated-endpoint' } };
  await page.unrouteAll();
  await page.routeWebSocket('**/api/v1/ws/**', socket => socket.close());
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/lab-profiles')) return route.fulfill({ json: [{ id: '11111111-1111-4111-8111-111111111111', name: '阶段测试实验室', is_active: true }] });
    if (path.endsWith('/instruments/hal/status')) return route.fulfill({ json: { mode: runtimeMode, driver_count: 1, active_drivers: ['vna'] } });
    if (path.endsWith('/instruments/hal/switch')) {
      runtimeMode = request.postDataJSON().mode;
      return route.fulfill({ json: { success: true, message: '模式已切换' } });
    }
    if (path.endsWith('/instruments/hal/readiness')) return route.fulfill({ json: {
      available: true, drivers: [{ category: 'vna', model: '测试仪器', endpoint: `runtime-${runtimeMode}`, status: 'configured', detail: '服务器运行快照' }],
      lab_profile: { profile_id: labId, profile_name: '阶段测试实验室', status: 'ok', detail: '', is_active: true },
      base_station_binding: { status: 'configured', execution_mode: 'simulated', lab_profile_id: labId,
        model_name: '模拟基站', adapter_id: 'cmw500_lte', binding_digest: 'diagnostic-binding', detail: '绑定已配置' },
      channel_emulator_binding: null,
      base_station_testcase_compatibility: { schema_version: 1, status: 'not_evaluated', compatible: null,
        test_case_id: null, lab_profile_id: labId, binding_digest: null, execution_mode: null,
        requirements: null, verdict: null, reasons: [], detail: '未选择用例' },
      calibration: { certificate_number: null, valid_until_iso: null, status: 'missing', days_remaining: null, detail: '未校准' },
      dut_attach: { status: 'not_implemented', detail: '未实现' },
      base_station_site_certification: null, base_station_site_certification_status: 'missing',
      base_station_site_certification_error: null, cmw500_lte_2x2: null, subnets: [],
      generated_at_iso: '2026-10-06T12:00:00Z', channel_emulator_site_certification_preview: null,
    } });
    if (path.endsWith('/instruments/catalog')) return route.fulfill(catalogFails
      ? { status: 503, json: { detail: '保存目录刷新失败' } } : { json: { categories: [category, simulatedCategory] } });
    if (path.endsWith('/instruments/vna') && request.method() === 'PUT') {
      if (saveFails) return route.fulfill({ status: 422, json: { detail: '保存拒绝' } });
      Object.assign(category.connection, request.postDataJSON().connection);
      category.connection.controller = category.connection.controller.trim();
      return route.fulfill({ json: category });
    }
    if (path.includes('/activate') && request.method() === 'POST') {
      activations++;
      if (holdActivation) await new Promise(resolve => { releaseActivation = resolve; });
      if (activationStatus === 'error') return route.fulfill({ status: 409, json: { detail: '租约占用' } });
      return route.fulfill({ json: { category_key: 'vna', status: 'inactive', driver_class: null, instrument_id: null, simulated: null, message: '类别未启用' } });
    }
    return route.fulfill({ status: 503, json: { detail: '未使用接口' } });
  });
  await page.goto('http://127.0.0.1:5198');
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).last().click();
  const panel = page.getByTestId('equipment-effective-state');
  await reviewCheck('simulated binding disclosure', () => panel.getByText('LabProfile绑定：configured · simulated · 仅诊断 · 绑定已配置', { exact: true }).waitFor({ timeout: 5000 }));
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).first().click();
  await panel.getByText('已保存端点：saved-endpoint', { exact: true }).waitFor();
  await page.getByRole('textbox', { name: '控制端点', exact: true }).fill('new-endpoint');
  await page.getByRole('textbox', { name: '控制方式', exact: true }).fill(' LAN ');
  await panel.getByText('草稿尚未保存', { exact: true }).waitFor();
  await panel.getByText('已保存端点：saved-endpoint', { exact: true }).waitFor();
  await page.getByRole('button', { name: '保存配置', exact: true }).click();
  await panel.getByText('保存失败；未尝试HAL激活', { exact: true }).waitFor();
  if (activations) throw new Error('保存失败仍激活');
  saveFails = false;
  holdActivation = true;
  await page.getByRole('button', { name: '保存配置', exact: true }).click();
  try {
    await panel.getByText('已保存；正在激活HAL', { exact: true }).waitFor();
    await panel.getByText('已保存端点：new-endpoint', { exact: true }).waitFor({ timeout: 5000 });
    await reviewCheck('canonical draft at commit boundary', () => panel.getByText('草稿与当前保存值一致', { exact: true }).waitFor({ timeout: 5000 }));
  } finally {
    holdActivation = false;
    releaseActivation?.();
  }
  await panel.getByText('已保存，但HAL激活失败', { exact: true }).waitFor();
  await panel.getByText('已保存端点：new-endpoint', { exact: true }).waitFor();
  activationStatus = 'inactive';
  await page.getByRole('button', { name: '保存配置', exact: true }).click();
  await panel.getByText('已保存；类别未启用，未加载驱动', { exact: true }).waitFor();
  await panel.getByText('LabProfile绑定：未取得该类别权威投影', { exact: true }).waitFor();
  holdActivation = true;
  const lateResponse = page.waitForResponse(response => response.url().endsWith('/instruments/vna/hal/activate'));
  await page.getByRole('button', { name: '保存配置', exact: true }).click();
  await panel.getByText('已保存；正在激活HAL', { exact: true }).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).first().click();
  await panel.getByText('尚未取得本页操作回执', { exact: true }).waitFor();
  holdActivation = false;
  releaseActivation?.();
  await lateResponse;
  await page.waitForTimeout(100); // Let the real App consume the late transport response.
  await reviewCheck('old request cannot revive receipt in new editor', () => panel.getByText('尚未取得本页操作回执', { exact: true }).waitFor({ timeout: 5000 }));
  await panel.getByText('HAL当前快照：configured · runtime-real · 服务器运行快照', { exact: true }).waitFor();
  await page.keyboard.press('Escape');
  await page.getByText('🔌 Real', { exact: true }).first().click();
  await page.getByText('🧪 Mock', { exact: true }).first().click();
  if (runtimeMode !== 'mock') throw new Error('测试未触发全局Mock模式切换');
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).first().click();
  await reviewCheck('receipt cleared on editor exit', () => panel.getByText('尚未取得本页操作回执', { exact: true }).waitFor({ timeout: 5000 }));
  await panel.getByText('HAL当前快照：configured · runtime-mock · 服务器运行快照', { exact: true }).waitFor({ timeout: 5000 });
  await page.keyboard.press('Escape');
  await page.getByRole('tab', { name: '总览', exact: true }).click();
  const resources = page.getByTestId('lab-saved-resources');
  await resources.getByText('new-endpoint', { exact: false }).waitFor();
  catalogFails = true;
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await resources.getByText('保存资源读取失败', { exact: false }).waitFor({ timeout: 15000 });
  if (await resources.getByText('new-endpoint', { exact: false }).count()) throw new Error('目录刷新失败仍展示旧保存成功');
  catalogFails = false;
  await page.getByRole('button', { name: '刷新总览', exact: true }).click();
  await resources.getByText('new-endpoint', { exact: false }).waitFor();
  if (reviewFailures.length) throw new Error(reviewFailures.join('\n'));
  return { passed: 12, activations, scenarios: ['simulated binding disclosure', 'dirty versus saved', 'save refused', 'saved while activating', 'canonical draft at commit boundary', 'activation refused', 'inactive receipt', 'receipt cleared on editor exit', 'old request cannot revive receipt in new editor', 'global HAL change refreshes snapshot', 'overview saved resources', 'catalog failure and recovery'] };
}
