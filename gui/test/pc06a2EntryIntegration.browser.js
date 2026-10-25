// 真实隔离API，不拦截响应；管理入口不得执行旧校准。
async page => {
  const ensure = (ok, message) => { if (!ok) throw new Error(message) };
  const legacyPhase = new URL(page.url()).searchParams.get('legacy');
  const base = legacyPhase ? new URL(page.url()).origin : 'http://127.0.0.1:5190';
  page.setDefaultTimeout(15000);
  const hal = await page.request.get(`${base}/api/v1/instruments/hal/status`);
  ensure(hal.ok() && (await hal.json()).mode === 'mock', '必须使用全 HAL Mock 环境');
  const labsResponse = await page.request.get(`${base}/api/v1/lab-profiles`);
  ensure(labsResponse.ok(), '隔离实验室读取失败');
  const labs = await labsResponse.json();
  const a = labs.find(row => row.name === 'PC06A2入口甲');
  const b = labs.find(row => row.name === 'PC06A2入口乙');
  const unbound = labs.find(row => row.name === 'PC06A2入口无暗室');
  ensure(labs.length === 3 && a && b && unbound, '必须使用本片专用隔离fixture');
  const requests = [], topologyResponses = [], pending = [];
  const onRequest = request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) requests.push({method:request.method(),url:request.url()});
  };
  const onResponse = response => {
    if (/\/switch-topologies\?/.test(response.url())) pending.push(response.json().then(body => topologyResponses.push({url:response.url(),body})));
  };
  page.on('request', onRequest); page.on('response', onResponse);
  try {
  if (legacyPhase) {
    const read = async path => {
      const response = await page.request.get(`${base}/api/v1${path}`);
      ensure(response.ok(), `真实读取失败：${path}`);
      return response.json();
    };
    const trp = await read('/calibration/trp?skip=0&limit=20');
    const certificates = await read('/calibration/certificate?skip=0&limit=20');
    ensure(Array.isArray(trp) && Array.isArray(certificates), '真实列表不是数组');
    ensure(legacyPhase === 'empty' ? trp.length === 0 && certificates.length === 0 : trp.length === 20 && certificates.length > 0,
      '数据库与本次empty/seeded验收阶段不一致');
    await page.goto(`${base}/?legacy=${legacyPhase}`);
    await page.getByRole('tab', {name:'系统校准',exact:true}).click();
    await page.getByRole('tab', {name:'校准记录',exact:true}).click();
    ensure(!await page.getByText('Engineer A',{exact:true}).count()
      && !await page.getByText('Standard Dipole λ/2',{exact:true}).count(), '真实空库仍显示固定演示校准记录');
    const history = page.getByTestId('legacy-system-history');
    await history.waitFor();
    const boundary = '旧系统记录（全局、实验室归属未知）。仅回放原字段，来源与当前正式资格未知，不计入当前实验室校准状态。';
    await history.getByText(boundary,{exact:true}).waitFor();
    const checks = [], reads = {trp,certificates};
    if (legacyPhase === 'empty') {
      await history.getByText('暂无旧记录',{exact:true}).waitFor();
      ensure(await history.getByRole('button',{name:'上一页',exact:true}).isDisabled(), '空库上一页未禁用');
      ensure(await history.getByRole('button',{name:'下一页',exact:true}).isDisabled(), '空库下一页未禁用');
      checks.push('真实空库无固定校准记录');
    } else {
      await history.getByText('本页 20 条',{exact:true}).waitFor();
      const assertRows = async expected => {
        const ids = await history.locator('tbody tr').evaluateAll(rows => rows.map(row => row.getAttribute('data-record-id')));
        ensure(JSON.stringify(ids) === JSON.stringify(expected.map(row => row.id)), '当前页ID/顺序与真实JSON不一致');
      };
      await assertRows(trp);
      ensure(await history.getByRole('cell',{name:'10.20 dBm',exact:true}).count() === 20
        && await history.getByRole('cell',{name:'0.20 dB',exact:true}).count() === 20
        && await history.getByRole('cell',{name:'原记录：通过',exact:true}).count() === 20, 'TRP原数值/判词与fixture不一致');
      await history.getByRole('button',{name:`查看原记录 ${trp[0].id}`,exact:true}).click();
      const original = history.getByTestId('legacy-record-json');
      ensure(JSON.stringify(JSON.parse(await original.innerText())) === JSON.stringify(trp[0]), '记录详情没有原样保留当前页JSON');
      await history.getByText(`来源：/api/v1/calibration/trp；原 ID：${trp[0].id}`,{exact:true}).waitFor();
      await history.getByRole('button',{name:'下一页',exact:true}).click();
      await history.getByText('本页 2 条',{exact:true}).waitFor();
      const second = await read('/calibration/trp?skip=20&limit=20'); reads.second = second;
      await assertRows(second);
      ensure(!await original.count(), '翻页仍显示前页选中详情');
      ensure(await history.getByRole('button',{name:'下一页',exact:true}).isDisabled(), '不足20条仍可下一页');
      await history.getByRole('button',{name:'上一页',exact:true}).click();
      await history.getByText('本页 20 条',{exact:true}).waitFor();
      await history.getByRole('textbox',{name:'按原 ID 检索当前页',exact:true}).fill(trp[0].id);
      await assertRows([trp[0]]);
      await history.getByRole('textbox',{name:'按原 ID 检索当前页',exact:true}).fill('');
      for (const [kind,label] of [['tis','TIS'],['repeatability','重复性']]) {
        await history.getByRole('textbox',{name:'旧记录类型',exact:true}).click();
        await page.getByRole('option',{name:label,exact:true}).click();
        const expected = await read(`/calibration/${kind}?skip=0&limit=20`); reads[kind] = expected;
        await history.getByText(`本页 ${expected.length} 条`,{exact:true}).waitFor();
        await assertRows(expected);
        ensure(await history.getByRole('button',{name:'上一页',exact:true}).isDisabled(), '切换类型未归零');
        await history.getByRole('button',{name:`查看原记录 ${expected[0].id}`,exact:true}).click();
        ensure(JSON.stringify(JSON.parse(await original.innerText())) === JSON.stringify(expected[0]), '切换类型详情JSON不一致');
        if (kind === 'tis') {
          await history.getByRole('cell',{name:'原记录：未通过',exact:true}).waitFor();
          await history.getByRole('cell',{name:'-88.00 dBm',exact:true}).waitFor();
          await history.getByRole('cell',{name:'2.00 dB',exact:true}).waitFor();
        }
        else {
          await history.getByRole('cell',{name:'执行指标对齐（非TRP/TIS校准）',exact:true}).waitFor();
          await history.getByRole('cell',{name:'原记录：未知',exact:true}).waitFor();
          ensure(await history.getByRole('cell',{name:'未知',exact:true}).count() === 2, 'nullable测量变成0或衍生值');
        }
      }
      await page.screenshot({path:'output/playwright/pc06a2-task2-history.png',fullPage:true});
      try {
        await page.context().setOffline(true);
        await history.getByRole('button',{name:'刷新',exact:true}).click();
        await history.getByText('旧记录读取已暂停；当前没有本次成功结果。',{exact:true}).waitFor();
        ensure(!await history.locator('tbody').count() && !await original.count(), '离线刷新仍显示旧成功数据/详情');
        await page.screenshot({path:'output/playwright/pc06a2-task2-history-offline.png',fullPage:true});
      } finally { await page.context().setOffline(false); }
      await history.getByRole('button',{name:'刷新',exact:true}).click();
      await history.getByText('本页 1 条',{exact:true}).waitFor();
      checks.push('真实分页/类型归零/ID检索/原字段JSON', 'null未知与执行指标边界', '历史真实离线隐藏旧数据并恢复');
    }
    await page.getByRole('tab',{name:'证书管理',exact:true}).click();
    ensure(!await page.getByText('MPAC-SYS-CAL-2025-11-16-1200',{exact:false}).count(), '证书仍显示固定演示证书');
    const viewer = page.getByTestId('legacy-system-certificates');
    await viewer.getByText(boundary,{exact:true}).waitFor();
    await viewer.getByText('仅原记录详情；此入口不生成、认证或下载证书。已有文件未删除',{exact:true}).waitFor();
    ensure(!await viewer.getByRole('button',{name:/下载|生成|应用/}).count(), '证书存在生成或下载入口');
    if (legacyPhase === 'empty') {
      await viewer.getByText('暂无旧证书',{exact:true}).waitFor();
      checks.push('真实空库无演示证书和下载');
    } else {
      const selected = certificates[0];
      await viewer.getByRole('cell',{name:selected.certificate_number,exact:true}).waitFor();
      await viewer.getByRole('button',{name:`查看原证书 ${selected.id}`,exact:true}).click();
      const raw = viewer.getByTestId('legacy-certificate-json');
      await raw.waitFor();
      const detail = await read(`/calibration/certificate/${selected.id}`); reads.detail = detail;
      ensure(JSON.stringify(JSON.parse(await raw.innerText())) === JSON.stringify(detail), '证书详情不等于真实API原字段');
      await viewer.getByText(`原截止日期：${detail.valid_until}`,{exact:true}).waitFor();
      ensure(!/当前有效|已过期|签名验证成功/.test(await viewer.innerText()), '原日期/签名被升级为资格');
      await page.screenshot({path:'output/playwright/pc06a2-task2-certificate.png',fullPage:true});
      try {
        await page.context().setOffline(true);
        await viewer.getByRole('button',{name:'刷新详情',exact:true}).click();
        await viewer.getByText('证书详情读取已暂停；当前没有本次成功结果。',{exact:true}).waitFor();
        ensure(!await raw.count(), '证书离线详情仍展示旧成功');
        await viewer.getByRole('button',{name:'刷新',exact:true}).click();
        await viewer.getByText('旧证书读取已暂停；当前没有本次成功结果。',{exact:true}).waitFor();
        ensure(!await viewer.locator('tbody').count(), '证书列表离线仍显示旧成功');
      } finally { await page.context().setOffline(false); }
      await viewer.getByRole('button',{name:'刷新',exact:true}).click();
      await viewer.getByRole('cell',{name:selected.certificate_number,exact:true}).waitFor();
      await viewer.getByRole('button',{name:`查看原证书 ${selected.id}`,exact:true}).click();
      await raw.waitFor();
      checks.push('证书真实详情JSON/原日期/无PDF生成', '证书列表与详情真实离线隐藏旧数据并恢复');
    }
    ensure(await page.getByTestId('system-calibration-summary').getByText('未知',{exact:true}).count() === 4, '旧记录升级了顶部正式资格');
    ensure(requests.every(row => row.method === 'GET'), '管理读取期间出现写请求');
    ensure(!requests.some(row => /\/download|\/calibration\/(?:history|stats)/.test(row.url)), '调用了下载或虚构接口');
    await page.screenshot({path:`output/playwright/pc06a2-task2-${legacyPhase}.png`,fullPage:true});
    return {checks,requests,reads,formal_acceptance:false};
  }
  await page.goto(base);
  await page.evaluate(() => {
    localStorage.removeItem('mimo.operationalLabProfileId');
    localStorage.removeItem('mimo.commissioning.lastLabId');
  });
  await page.reload();
  await page.getByRole('tab', {name:'系统校准',exact:true}).click();
  await page.getByRole('button',{name:'新建校准',exact:true}).click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  ensure(await dialog.getByRole('button',{name:'进入当前实验室射频拓扑',exact:true}).count() === 1,
    '系统校准仍是独立执行向导，没有唯一拓扑入口');
  ensure(await dialog.getByRole('button',{name:'开始校准',exact:true}).count() === 0,
    '管理向导仍可执行旧校准');
  await dialog.getByText('TRP/TIS：本入口没有可验证真实测量链', {exact:true}).waitFor();
  for (const text of [
    '路径损耗/增益、上下行链、多频点：在当前实验室拓扑核对接线并选择已有通路；只开放该工作台已支持的范围',
    '重复性：旧测量入口未开放；执行指标对齐不等于 TRP/TIS 重复性验证',
    '静区/相位/互耦：需要独立方法和已验证现场条件，路径损耗不能替代',
    '相对基线：仅保留原记录查询，不执行旧模拟 quick/drift',
    '参考件：参考天线/接收线缆来源在原拓扑填写；证书有效性、适用频率和不确定度仍需独立核验',
  ]) await dialog.getByText(text,{exact:true}).waitFor();
  const checks = ['唯一拓扑入口', '无旧执行', '独立方法边界'];
  const entry = root => root.getByRole('button',{name:'进入当前实验室射频拓扑',exact:true});
  ensure(await entry(dialog).isDisabled(), '没有选择Lab仍能导航');
  await dialog.getByText('请先选择当前 LabProfile',{exact:true}).waitFor();
  await page.keyboard.press('Escape');
  await dialog.waitFor({state:'hidden'});
  ensure(await entry(page).isDisabled(), '管理页无Lab未拒绝');
  const choose = async lab => {
    await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
    await page.getByRole('option').filter({hasText:lab.name}).click();
  };
  await choose(unbound);
  ensure(await entry(page).isDisabled(), '无暗室仍能导航');
  await page.getByRole('button',{name:'新建校准',exact:true}).click();
  await dialog.waitFor(); ensure(await entry(dialog).isDisabled(), 'Modal无暗室仍能导航');
  await dialog.getByText('当前 LabProfile 未绑定暗室',{exact:true}).waitFor();
  await page.keyboard.press('Escape'); await dialog.waitFor({state:'hidden'});
  checks.push('未选择Lab/未绑定暗室两入口均禁用');
  const baseline = page.getByTestId('legacy-calibration-baselines');
  const baselineReads = [];
  for (const [lab, modal] of [[a,false],[b,true],[a,true]]) {
    await choose(lab);
    const response = await page.request.get(`${base}/api/v1/calibration/baseline/status/${lab.chamber_config_id}`);
    ensure(response.ok(), '基线真实读取失败');
    const body = await response.json();
    ensure(body.chamber_id === lab.chamber_config_id, '基线归属错误');
    if (body.baselines.length) {
      const frequency = lab.id === a.id ? 2595 : 3500;
      await baseline.getByRole('cell',{name:`${frequency} MHz`,exact:true}).waitFor();
      ensure(!await baseline.getByRole('cell',{name:`${frequency === 2595 ? 3500 : 2595} MHz`,exact:true}).count(), '跨Lab泄漏基线');
      await baseline.getByRole('columnheader',{name:'原状态',exact:true}).waitFor();
      await baseline.getByText('valid',{exact:true}).waitFor();
      ensure(!await baseline.getByText('有效',{exact:true}).count(), '原valid被升级当前有效');
    } else await baseline.getByText('暂无原基线记录',{exact:true}).waitFor();
    baselineReads.push({lab_id:lab.id,chamber_id:lab.chamber_config_id,body});
    ensure(!await page.getByRole('button',{name:/^(快速校准|漂移检测|开始校准)$/}).count(), '管理页仍有旧执行按钮');
    if (modal) {
      await page.getByRole('button',{name:'新建校准',exact:true}).click();
      await dialog.waitFor(); await entry(dialog).click(); await dialog.waitFor({state:'hidden'});
    } else await entry(page).click();
    await page.getByTestId('route-calibration-panel').waitFor();
    await page.getByText(`PC06A2入口显式路径${lab.id === a.id ? '甲' : '乙'}`,{exact:true}).waitFor();
    ensure(await page.evaluate(()=>localStorage.getItem('mimo.operationalLabProfileId')) === lab.id, '导航改了全局Lab');
    ensure(!await page.getByTestId('selected-calibration-path').count(), '导航伪选了候选路径');
    ensure(await page.getByRole('textbox',{name:'完整校准通路',exact:true}).inputValue() === '', '导航伪填了链');
    await page.getByRole('button',{name:'预览完整批清单',exact:true}).waitFor();
    await page.getByRole('tab',{name:'系统校准',exact:true}).click();
    checks.push(`${lab.name}由${modal ? '方法对话框' : '管理页'}进入原图，无伪选链/采集`);
  }
  await baseline.getByRole('button',{name:'刷新',exact:true}).click();
  await baseline.getByText('来源与当前正式资格未知；仅保留原记录查询，不执行旧模拟 quick/drift。',{exact:true}).waitFor();
  await page.screenshot({path:'output/playwright/pc06a2-entry-baseline.png',fullPage:true});
  try {
    await page.context().setOffline(true);
    await baseline.getByRole('button',{name:'刷新',exact:true}).click();
    await baseline.getByText('基线读取已暂停；当前没有本次成功结果。',{exact:true}).waitFor();
    ensure(!await baseline.getByRole('cell').count(), '离线刷新仍展示旧成功行');
    checks.push('真实离线刷新显示paused，不展示旧成功行');
  } finally {
    await page.context().setOffline(false);
  }
  await baseline.getByRole('button',{name:'刷新',exact:true}).click();
  if (baselineReads[0].body.baselines.length)
    await baseline.getByRole('cell',{name:'2595 MHz',exact:true}).waitFor();
  else await baseline.getByText('暂无原基线记录',{exact:true}).waitFor();
  checks.push('恢复后重新真实读取当前暗室');
  await Promise.all(pending);
  for (const lab of [a,b]) {
    ensure(topologyResponses.some(row => new URL(row.url).searchParams.get('lab_profile_id') === lab.id && row.body.items.some(item => item.chamber_id === lab.chamber_config_id)), '拓扑GET未携带同Lab或返回错误暗室');
    ensure(requests.some(row => row.url.includes(`/lab-profiles/${lab.id}/route-calibration-paths?`)), '原图路径请求缺少同Lab ID');
  }
  ensure(requests.every(row => row.method === 'GET'), '入口只读/导航期间出现写请求');
  ensure(!requests.some(row => /\/calibration\/(?:history|stats)|\/download/.test(row.url)), '出现虚构历史/统计或下载请求');
  return { checks, requests, topologyResponses, baselineReads, lab_ids:[a.id,b.id,unbound.id], formal_acceptance: false };
  } finally {
    page.off('request',onRequest); page.off('response',onResponse);
  }
}
