// Run with playwright-cli run-code --filename gui/test/instrumentCatalogError.browser.js
// Only HTTP transport is replaced; the real App, query and draft consumers run.
async (page) => {
  const refocus = () => page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    window.dispatchEvent(new Event('visibilitychange'));
    delete document.visibilityState;
    window.dispatchEvent(new Event('visibilitychange'));
  });
  let mode = 'error';
  const catalog = { categories: [{
    categoryId: '22222222-2222-4222-8222-222222222222', key: 'vna', label: '回归网络分析仪',
    description: '目录错误态回归', tags: [], isActive: true, selectedModelId: null,
    usagePhase: [], driverMode: 'real', models: [],
    connection: { id: '33333333-3333-4333-8333-333333333333', endpoint: 'server-endpoint',
      controller: 'LAN', notes: '', connection_params: {}, invalid_fields: {},
      cmw500_lte_2x2_formal_enabled: false, cmw500_lte_2x2_formal_updated_at: null,
      base_station_site_certification: null, channel_emulator_site_certification: null,
      base_station_model_presets: {}, channel_emulator_model_presets: {} },
  }] };
  await page.unrouteAll();
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/lab-profiles')) {
      await route.fulfill({ status: 200, json: [{ id: '11111111-1111-4111-8111-111111111111', name: '回归测试暗室', is_active: true }] });
    } else if (path.endsWith('/instruments/catalog')) {
      await route.fulfill(mode === 'error'
        ? { status: 503, json: { detail: '目录服务暂不可用' } }
        : { status: 200, json: mode === 'empty' ? { categories: [] } : catalog });
    } else {
      await route.fulfill({ status: 503, json: { detail: '测试未使用此接口' } });
    }
  });
  await page.goto('http://127.0.0.1:5198');
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  await page.getByRole('tab', { name: '仪器资源', exact: true }).click();
  await page.getByText('目录服务暂不可用', { exact: false }).waitFor({ timeout: 15000 });
  if (await page.getByText('暂无仪器信息，请在后端添加型号。').count()) {
    throw new Error('请求失败被误报为成功空目录');
  }
  await page.getByRole('button', { name: '重试加载目录', exact: true }).waitFor();
  console.log('PASS: failed catalog is visible and retryable, not an empty catalog');
  mode = 'empty';
  await page.getByRole('button', { name: '重试加载目录', exact: true }).click();
  await page.getByText('暂无仪器信息，请在后端添加型号。').waitFor();
  if (await page.getByRole('alert', { name: '仪器目录加载失败', exact: true }).count()) throw new Error('成功空目录仍显示失败');
  console.log('PASS: successful empty catalog has the empty state');

  mode = 'catalog';
  await refocus();
  await page.getByRole('heading', { name: '回归网络分析仪', exact: true }).waitFor();
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).click();
  await page.getByRole('textbox', { name: '控制端点', exact: true }).fill('operator-unsaved-endpoint');
  mode = 'error';
  await refocus();
  await page.getByText('目录服务暂不可用', { exact: false }).waitFor({ timeout: 15000 });
  if (await page.getByRole('textbox', { name: '控制端点', exact: true }).inputValue() !== 'operator-unsaved-endpoint') {
    throw new Error('刷新失败覆盖了用户草稿');
  }
  // Close only the editor; do not navigate away and unmount the draft owner.
  await page.keyboard.press('Escape');
  mode = 'catalog';
  await page.getByRole('button', { name: '重试加载目录', exact: true }).click();
  await page.getByRole('alert', { name: '仪器目录加载失败', exact: true }).waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '替换 / 配置实装', exact: true }).click();
  if (await page.getByRole('textbox', { name: '控制端点', exact: true }).inputValue() !== 'operator-unsaved-endpoint') {
    throw new Error('重试成功覆盖了用户草稿');
  }
  console.log('PASS: cached catalog and operator draft survive failed refresh and successful retry');
  return { passed: 3, scenarios: ['initial failure', 'successful empty response', 'cached draft across failure and retry'] };
}
