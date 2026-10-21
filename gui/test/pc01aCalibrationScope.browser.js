// 真实 App + HTTP/WS 边界隔离。只读快照/比较，不接生产服务。
async (page) => {
  page.setDefaultTimeout(6000);
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const ids = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'];
  const labs = ids.map((id, i) => ({ id, name: `范围实验室${i ? '乙' : '甲'}`, is_active: true,
    chamber_config_id: `chamber-${i}`, chamber_name: `范围暗室${i}` }));
  let changed = false;
  let failure = false;
  let hold = false;
  let release;
  const posts = [];
  const make = id => ({ payload: { version: 1, lab_profile_id: id,
    chamber_id: labs.find(l => l.id === id).chamber_config_id, operating_mode: 'mimo_ota', lab_active: true,
    chamber: { chamber_radius_m: 4 }, resources: [], topology: {}, probes: [],
    chains: [{ chain_id: `chain-${id}`, ce_port: changed ? 'B9' : 'B1', probe_id: 0, polarization: 'V', cable_loss_db: 0.5 }] },
    digest: (changed ? 'b' : 'a').repeat(64), physical_identity: 'unverified', formal_eligible: false,
    configuration_complete: false, warnings: ['声明配置，尚未现场核验'] });
  await page.routeWebSocket('**/api/v1/ws/**', () => {});
  await page.route('**/api/v1/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path.endsWith('/lab-profiles')) return route.fulfill({ json: labs });
    if (path.includes('/calibration-scope')) {
      const id = path.split('/')[4];
      if (failure) return route.fulfill({ status: 503, json: { detail: '范围服务不可用' } });
      if (req.method() === 'POST') {
        posts.push({ path, body: req.postDataJSON() });
        const json = { current: make(id), changed_sections: ['chains'],
          affected_chain_ids: [`chain-${id}`], requires_review: true, formal_eligible: false };
        if (hold) await new Promise(resolve => { release = resolve; });
        return route.fulfill({ json });
      }
      return route.fulfill({ json: make(id) });
    }
    if (path.endsWith('/instruments/catalog')) return route.fulfill({ json: { categories: [] } });
    if (path.endsWith('/system-logs/frontend')) return route.fulfill({ json: {} });
    if (req.method() !== 'GET') throw new Error(`非预期写入 ${path}`);
    return route.fulfill({ status: 503, json: { detail: '隔离的非本片接口' } });
  });
  await page.goto('http://127.0.0.1:5187');
  await page.evaluate(id => localStorage.setItem('mimo.operationalLabProfileId', id), ids[0]);
  await page.reload();
  await page.getByRole('tab', { name: '实验室配置', exact: true }).click();
  const card = page.getByTestId('calibration-scope');
  await card.getByText('B1', { exact: true }).waitFor();
  await card.getByRole('button', { name: '保留当前范围快照', exact: true }).click();
  changed = true;
  await card.getByRole('button', { name: '与保留快照比较', exact: true }).click();
  await card.getByText('B9', { exact: true }).waitFor();
  await card.getByText('配置变化，需复核', { exact: false }).waitFor();
  if (posts.length !== 1 || posts[0].body.baseline.digest !== 'a'.repeat(64)) throw new Error('比较未使用所保留快照');
  hold = true;
  await card.getByRole('button', { name: '与保留快照比较', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="calibration-scope"] button')?.disabled);
  if (!await card.getByRole('button', { name: '刷新范围', exact: true }).isDisabled()) throw new Error('比较时仍可并发手动刷新');
  changed = false;
  while (!release) await page.waitForTimeout(10);
  release();
  await card.getByRole('button', { name: '刷新范围', exact: true }).waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.querySelector('[data-testid="calibration-scope"] button')?.disabled);
  await card.getByText('B1', { exact: true }).waitFor();
  if (await card.getByText('B9', { exact: true }).count()) throw new Error('旧比较覆盖新GET范围');
  hold = false;
  failure = true;
  await card.getByRole('button', { name: '刷新范围', exact: true }).click();
  await card.getByText('范围读取失败', { exact: false }).waitFor();
  if (await card.getByText('B1', { exact: true }).count()) throw new Error('失败后仍显示旧成功链');
  failure = false;
  await page.getByRole('textbox', { name: '当前 LabProfile', exact: true }).click();
  await page.getByRole('option').filter({ hasText: '范围实验室乙' }).click();
  await card.getByText(`chain-${ids[1]}`, { exact: true }).waitFor();
  if (await card.getByText('保留摘要', { exact: false }).count()) throw new Error('保留快照跨实验室残留');
  if (!await card.getByRole('button', { name: '与保留快照比较', exact: true }).isDisabled()) throw new Error('未保留快照仍允许比较');
  await page.screenshot({ path: 'output/playwright/pc01a-scope.png', fullPage: true });
  return { passed: 8, comparePosts: posts.length };
}
