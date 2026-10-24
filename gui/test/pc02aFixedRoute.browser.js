// 真实App，隔离HTTP边界；不连接生产API或任何仪器。
async (page) => {
  page.setDefaultTimeout(4000);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const id = '11111111-1111-4111-8111-111111111111';
  let posts = 0;
  await page.routeWebSocket('**/api/v1/ws/**', () => {});
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/lab-profiles')) return route.fulfill({ json: [{ id, name: '固定通路实验室', is_active: true, chamber_config_id: 'chamber-1' }] });
    if (path.endsWith('/fixed-route/preview')) {
      const body = route.request().postDataJSON();
      if (body.lab_profile_id !== id || body.switch_mode !== 'fixed' || body.ce_output_power_dbm !== -20 || body.receive_cable_loss_db !== 2) throw new Error('提交值与人工填写不符');
      posts++;
      return route.fulfill({ json: { declaration: body, net_loss_db: -12, formal_eligible: false,
        input_provenance: 'operator_entered', method: 'fixed_route_port_to_reference_v1', warning: '仅按人工输入计算；不是实测校准。' } });
    }
    if (path.endsWith('/system-logs/frontend')) return route.fulfill({ json: {} });
    if (route.request().method() !== 'GET') throw new Error(`非预期写入：${path}`);
    return route.fulfill({ status: 503, json: { detail: '隔离非本片接口' } });
  });
  await page.goto('http://127.0.0.1:5187');
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), id);
  await page.reload();
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  const card = page.getByTestId('fixed-route-calibration');
  await card.waitFor();
  const fields = {
    '链编号': 'probe-0-v', 'F64输出口': 'B1.1', '射频开关身份': 'EMCenter-1',
    '开关固定通路': 'input1-output3', '参考天线及位置': 'reference-1，中心V', '工作频率（MHz）': '3500',
    'F64输出口功率（dBm）': '-20', '输出口功率来源': 'record-1',
    '分析仪输入口功率（dBm）': '-10', '分析仪读数来源': 'record-2',
    '接收线缆损耗（dB）': '2', '接收线缆记录来源': 'record-3',
  };
  for (const [label, value] of Object.entries(fields)) await card.getByLabel(`${label} *`, { exact: true }).fill(value);
  await card.getByRole('button', { name: '计算预览', exact: true }).click();
  await card.getByText('整条路径增益：12 dB', { exact: true }).waitFor();
  await card.getByText('不是实测校准', { exact: false }).waitFor();
  await card.getByLabel('F64输出口功率（dBm） *', { exact: true }).fill('-21');
  if (await card.getByText('整条路径增益：12 dB', { exact: true }).count()) throw new Error('修改输入后仍显示旧结果');
  if (posts !== 1) throw new Error('出现额外提交');
  return { passed: 3, previewPosts: posts };
}
