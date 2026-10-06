// 真实 App，仅替换 HTTP/WS；刷新失败不得继续展示旧缓存。
async (page) => {
  let reads = 0;
  let fail = false;
  let runtimeMode = 'real';
  let holdFirstRead = false;
  let releaseOld;
  let signalHeld;
  let signalOldFinished;
  await page.unrouteAll();
  await page.routeWebSocket('**/api/v1/ws/**', socket => socket.close());
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/instruments/catalog')) return route.fulfill({ json: { categories: [{
      categoryId: '22222222-2222-4222-8222-222222222222', key: 'channelEmulator', label: '信道仿真器',
      description: '', tags: [], isActive: true, selectedModelId: 'model-id', savedConfigurationDigest: 'a'.repeat(64), usagePhase: [], driverMode: 'real',
      models: [{ id: 'model-id', model: 'F64', vendor: 'Keysight', status: 'available', interfaces: [], capabilities: [] }],
      connection: { id: '33333333-3333-4333-8333-333333333333', endpoint: 'saved-endpoint', controller: 'LAN', notes: '',
        connection_params: {}, invalid_fields: {}, cmw500_lte_2x2_formal_enabled: false,
        base_station_site_certification: null, channel_emulator_site_certification: null,
        base_station_model_presets: {}, channel_emulator_model_presets: {} },
    }] } });
    if (path.endsWith('/lab-profiles')) return route.fulfill({ json: [{ id: '11111111-1111-4111-8111-111111111111', name: '诊断测试 Lab', is_active: true }] });
    if (path.endsWith('/instruments/hal/status')) return route.fulfill({ json: { mode: runtimeMode, driver_count: 1, active_drivers: ['channelEmulator'] } });
    if (path.endsWith('/activate')) {
      runtimeMode = 'mock';
      return route.fulfill({ json: { category_key: 'channelEmulator', status: 'activated', driver_class: 'MockChannelEmulator', instrument_id: 'mock-ce', simulated: true, message: '已激活' } });
    }
    if (path.endsWith('/runtime-snapshot')) {
      reads++;
      const modeAtRequest = runtimeMode;
      const held = holdFirstRead && reads === 1;
      if (held) { signalHeld(); await new Promise(resolve => { releaseOld = resolve; }); }
      await route.fulfill(fail ? { status: 503, json: { detail: '测试刷新失败' } } : { json: {
        generated_at: '2026-10-06T12:00:00Z', diagnostic_only: true, availability: modeAtRequest === 'mock' ? 'simulated' : 'available',
        instrument_id: 'f64-test', driver_status: 'ready', local_control_reserved: true,
        fields: [{ key: 'loaded_emulation_file', value: 'example.smu', source: 'requested_project_cache',
          freshness: 'unknown', observed_at: null, execution_id: null, session_id: null },
          { key: 'output_power', value: null, source: 'unknown', freshness: 'unknown', observed_at: null, execution_id: null, session_id: null }],
      } });
      if (held) signalOldFinished();
      return;
    }
    return route.fulfill({ status: 503, json: { detail: '未使用接口' } });
  });
  await page.goto('http://127.0.0.1:45484');
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).click();
  const card = page.getByTestId('f64-runtime-snapshot');
  await card.getByText('example.smu', { exact: true }).waitFor({ timeout: 5000 });
  await card.getByText('缓存时效与执行/会话归属未知；不是实时采样，也不是历史冻结证据。', { exact: true }).waitFor();
  await card.getByText('未知（无可信缓存）', { exact: true }).waitFor();
  if (reads !== 1) throw new Error(`非人工刷新请求数 ${reads}`);
  await page.getByRole('button', { name: '仅重试该类别 HAL 激活', exact: true }).click();
  await card.getByText('当前是模拟驱动，不展示为真实 F64 运行态', { exact: true }).waitFor({ timeout: 5000 });
  if (await card.getByText('example.smu', { exact: true }).count()) throw new Error('HAL换模式仍显示旧工程');
  fail = true;
  await card.getByRole('button', { name: '刷新内存快照', exact: true }).click();
  await card.getByText('刷新失败；旧快照不再展示。', { exact: true }).waitFor();
  if (await card.getByText('example.smu', { exact: true }).count()) throw new Error('失败仍显示旧快照');
  // 首次响应仍在途中时切换 HAL，旧响应不能覆盖新的驱动。
  fail = false; runtimeMode = 'real'; reads = 0; holdFirstRead = true;
  const heldStarted = new Promise(resolve => { signalHeld = resolve; });
  const oldFinished = new Promise(resolve => { signalOldFinished = resolve; });
  await page.reload();
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).click();
  await heldStarted;
  await page.getByRole('button', { name: '仅重试该类别 HAL 激活', exact: true }).click();
  try { await card.getByText('当前是模拟驱动，不展示为真实 F64 运行态', { exact: true }).waitFor({ timeout: 5000 }); }
  finally { releaseOld(); }
  await oldFinished;
  if (reads !== 2) throw new Error(`首次请求未作废/重读：${reads}`);
  await card.getByText('当前是模拟驱动，不展示为真实 F64 运行态', { exact: true }).waitFor();
  console.log('P2-84 real App: cache/unknown/source/manual refresh/failure passed');
}
