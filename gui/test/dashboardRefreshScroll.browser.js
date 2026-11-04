// 启动隔离GUI 5181后：playwright-cli run-code --filename gui/test/dashboardRefreshScroll.browser.js
// 只替换HTTP，真实App/主滚动区/Query/实验室切换均保留；不接触仪器。
async page => {
  let mode = 'ok', calls = 0;
  const check = (condition, message) => { if (!condition) throw Error(message); };
  await page.unrouteAll();
  await page.context().setOffline(false);
  await page.addInitScript(() => localStorage.setItem('mimo.operationalLabProfileId', '11111111-1111-4111-8111-111111111111'));
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    let body = {};
    if (url.pathname.endsWith('/lab-profiles')) body = [
      {id:'11111111-1111-4111-8111-111111111111',name:'回归实验室一',is_active:true,chamber_config_id:'33333333-3333-4333-8333-333333333333'}, {id:'22222222-2222-4222-8222-222222222222',name:'回归实验室二',is_active:true,chamber_config_id:'33333333-3333-4333-8333-333333333333'},
    ];
    else if (url.pathname.endsWith('/hal/readiness')) {
      calls++;
      await new Promise(resolve => setTimeout(resolve, 700));
      if (mode === 'error') return route.fulfill({status:503,json:{detail:'回归刷新失败'}});
      body = {available:true,generated_at_iso:'回归快照',drivers:[],
        calibration:{status:'missing',detail:'缺证书'},
        lab_profile:{status:'ok',profile_name:url.searchParams.get('lab_profile_id'),detail:'已选择'},
        dut_attach:{detail:'未实现'},subnets:[]};
    } else if (url.pathname.endsWith('/system-logs/tail')) body = {
      entries:url.searchParams.has('level') ? [] : Array.from({length:100},(_,i)=>({
        ts:'2026-11-04T00:00:01Z',level:'INFO',logger:'test',msg:'日志 '+i})),total_lines_read:100};
    else if (url.pathname.endsWith('/alerts/summary')) body = {total_active:0,by_severity:{},by_category:{}};
    else if (url.pathname.includes('test-executions')) body = {items:[],total:0};
    await route.fulfill({status:200,json:body});
  });
  await page.setViewportSize({width:1280,height:720});
  await page.goto('http://127.0.0.1:5181/');
  const snapshot = page.getByText('服务器快照时间：',{exact:false});
  const pending = page.getByText('正在确认所选 LabProfile 的最新就绪状态……',{exact:true});
  const main = page.locator('.app-main');
  const card = page.locator('.mantine-Card-root').filter({has:page.getByText('系统就绪',{exact:true})});
  const scroll = () => main.evaluate(el => el.scrollTop);
  const settle = async () => { await snapshot.waitFor(); await page.waitForTimeout(150); };
  const refocus = () => page.evaluate(() => {
    Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
    window.dispatchEvent(new Event('visibilitychange'));
    delete document.visibilityState;
    window.dispatchEvent(new Event('visibilitychange'));
  });
  await settle();
  await main.evaluate(el => {el.scrollTop=el.scrollHeight});
  const start = await scroll();
  check(start>100,'未构造可滚动主页面');
  // 真实10秒轮询，不用手动刷新替代故障触发。
  await pending.waitFor({timeout:15000});
  check(await snapshot.count()===0,'刷新时仍显示旧就绪快照');
  check(Math.abs(await scroll()-start)<2,'周期刷新使整页阅读位置跳动');
  await settle();
  check(Math.abs(await scroll()-start)<2,'刷新结束后整页跳动');
  mode='error'; await refocus();
  await page.getByText('就绪状态读取失败 · 不可开测',{exact:true}).waitFor({timeout:25000});
  check(await snapshot.count()===0,'失败仍发布旧结论');
  check(Math.abs(await scroll()-start)<2,'失败时页面高度塌缩');
  mode='ok'; await refocus(); await settle();
  await page.context().setOffline(true); await refocus();
  await page.getByText('网络不可用，无法确认最新就绪状态 · 不可开测',{exact:true}).waitFor({timeout:15000});
  check(await snapshot.count()===0,'离线仍发布旧结论');
  check(Math.abs(await scroll()-start)<2,'离线时页面高度塌缩');
  await page.context().setOffline(false); await settle();
  await page.setViewportSize({width:800,height:720}); await page.waitForTimeout(250);
  await main.evaluate(el=>{el.scrollTop=el.scrollHeight}); const narrow=await scroll();
  await refocus(); await pending.waitFor();
  check(Math.abs(await scroll()-narrow)<2,'尺寸变化后刷新仍跳动');
  await settle();
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option',{name:/回归实验室二/}).click();
  await page.getByText('就绪状态读取中……',{exact:true}).waitFor();
  check(await card.evaluate(el=>el.style.minHeight)==='', '切实验室继承了旧布局高度');
  check(await snapshot.count()===0,'切实验室显示旧快照');
  await settle();
  return {passed:['周期刷新','失败与恢复','离线与恢复','响应式高度','切实验室'],start,narrow,calls};
}
