async page => {
  const requireValue = (ok, message) => { if (!ok) throw new Error(message) };
  // 只对明确建立的新库 / 全 HAL Mock 隔离环境执行；不伪造 HTTP 响应。
  const base = 'http://127.0.0.1:5190';
  const hal = await page.request.get(`${base}/api/v1/instruments/hal/status`);
  requireValue(hal.ok() && (await hal.json()).mode === 'mock', '必须使用全 HAL Mock 环境');
  const certificate = await page.request.get(`${base}/api/v1/calibration/certificate`);
  requireValue(certificate.status() === 200 && (await certificate.json()).length === 0, '隔离库证书必须为空');
  const calibrationRequests = [];
  const onRequest = request => {
    if (request.url().includes('/calibration/')) calibrationRequests.push({ method: request.method(), url: request.url() });
  };
  page.on('request', onRequest);
  await page.goto(base);
  await page.getByRole('tab', { name: '系统校准', exact: true }).click();
  await page.getByRole('heading', { name: '系统校准', exact: true }).last().waitFor();
  // 旧页面的可见假状态让 RED 失败，而非等待尚不存在的测试标记。
  requireValue(!await page.getByText('±0.12 dB', { exact: true }).first().isVisible(), '无证据仍展示 TRP 精度');
  const summary = page.getByTestId('system-calibration-summary');
  const overview = page.getByTestId('system-calibration-overview');
  requireValue(await summary.getByText('未知', { exact: true }).count() === 4, '四项状态必须未知');
  const text = await summary.innerText();
  requireValue(!/2026-11-16|±\d|σ\s*=|有效期至:/.test(text), '顶部存在无来源数值或日期');
  requireValue(!await summary.getByText('有效', { exact: true }).count(), '证书不得宣称有效');
  const body = await overview.innerText();
  requireValue(!/93\.3|过去 4 个月|所有校准参数均在标准范围内|需重新校准|32\/32|25\.3|30\.1/.test(body), '概览仍有固定成果');
  for (const name of ['TRP 精度趋势', 'TIS 精度趋势', '可重复性趋势', '校准时间线', '校准依赖关系', '路径校准状态 (DL/UL Path Calibration)']) {
    requireValue(!await overview.getByText(name, { exact: true }).count(), `仍挂载示例面板: ${name}`);
  }
  await overview.getByText('基线状态不代表系统证书或 TRP/TIS 验证', { exact: true }).waitFor();
  // Tab 保留仅验证可达，不把这些遗留页面内容当作本片可信状态验收。
  for (const name of ['校准记录', '证书管理', '概览']) {
    await page.getByRole('tab', { name, exact: true }).click();
  }
  await page.getByRole('button', { name: '新建校准', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await page.keyboard.press('Escape');
  page.off('request', onRequest);
  requireValue(calibrationRequests.every(request => request.method === 'GET' && /\/calibration\/(?:baseline\/status\/[0-9a-f-]+|trp|tis|repeatability|certificate(?:\/[0-9a-f-]+)?)(?:\?|$)/i.test(request.url)), '管理页产生非白名单只读校准请求');
  return { checks: ['四项未知', '无固定成果', '移除示例状态挂载', '旧入口保留'], summary: text, overview: body, calibrationRequests, formal_acceptance: false };
}
