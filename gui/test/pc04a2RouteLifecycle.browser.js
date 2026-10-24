// 真实隔离API/全HAL Mock；只注入网络在途/失败，不伪造响应或持久化记录。
async page=>{
  await page.evaluate(()=>{window.__routeLifecycleResult=null});
  page.setDefaultTimeout(15000);
  const api='http://127.0.0.1:18080/api/v1';
  const status=await(await page.request.get(`${api}/instruments/hal/status`)).json();
  if(status.mode!=='mock')throw new Error('仅允许隔离全Mock环境');
  await page.goto('http://127.0.0.1:5187');
  await page.getByRole('textbox',{name:'当前 LabProfile',exact:true}).click();
  await page.getByRole('option').filter({hasText:'PC04自动采集甲'}).click();
  await page.getByRole('tab',{name:'实验室配置',exact:true}).click();
  const open=async()=>{await page.getByRole('tab',{name:'射频拓扑',exact:true}).click();await page.getByTestId('route-calibration-panel').waitFor()};
  await open();
  const panel=page.getByTestId('route-calibration-panel');
  await panel.getByRole('textbox',{name:'完整校准通路',exact:true}).click();
  await page.getByRole('option').filter({hasText:'fixed-v'}).click();
  for(const [label,value] of [['采集频率','2595'],['允许的单音设置功率','-30'],['参考天线身份','生命周期网络故障验证 V'],['接收线缆损耗','2'],['接收线缆记录来源','隔离测试@2595MHz']])
    await panel.getByLabel(label,{exact:false}).fill(value);
  await panel.getByRole('checkbox',{name:'我已核对所选链',exact:false}).check();
  await panel.getByRole('checkbox',{name:'我已确认专用校准仿真',exact:false}).check();
  let holdStart=true,failReads=true,release;
  const gate=new Promise(resolve=>{release=resolve});
  const reads=async route=>{
    // A failed assertion may already have detached this held request during cleanup.
    if(route.request().method()==='POST'&&holdStart){await gate;if(holdStart)return route.abort('failed').catch(()=>{});return route.continue()}
    if(route.request().method()==='GET'&&failReads)return route.abort('failed');
    return route.continue();
  };
  await page.route('**/fixed-route-acquisitions**',reads);
  const checkLocked=async(label)=>{
    // Give the actual failed history query time to settle; never use a fixed sleep.
    await panel.getByText('历史读取失败：',{exact:false}).waitFor();
    if(!await page.getByRole('button',{name:'添加器件',exact:true}).isDisabled()||
       !await page.getByRole('button',{name:'保存拓扑',exact:true}).isDisabled()||
       !await page.getByRole('textbox',{name:'操作模式',exact:true}).isDisabled()||
       !await page.getByRole('textbox',{name:'射频开关设备',exact:false}).isDisabled())
      throw new Error(`${label}：返回页面且历史失败时原画布错误解锁`);
    await panel.getByText('采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。',{exact:true}).waitFor();
  };
  try{
    await panel.getByRole('button',{name:'开始自动采集',exact:true}).click();
    await page.getByRole('tab',{name:'总览',exact:true}).click();await open();
    await checkLocked('开始请求pending');
    const cancel=panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true});
    if(!await cancel.isDisabled())throw new Error('未知run身份不应假装可以取消');
    await panel.getByText('开始回执未知时，空历史不能证明未启动。',{exact:false}).waitFor();
    const response=page.waitForResponse(r=>r.url().endsWith('/fixed-route-acquisitions')&&r.request().method()==='POST');
    holdStart=false;release();
    const started=await response;if(started.status()!==202)throw new Error(await started.text());
    const record=await started.json();
    await page.getByRole('tab',{name:'总览',exact:true}).click();await open();
    await checkLocked('已收到running回执');
    await page.screenshot({path:'output/playwright/pc04a2-task6-lifecycle-locked.png'});
    failReads=false;
    await panel.getByRole('button',{name:'读取历史／恢复采集状态',exact:true}).click();
    await page.waitForFunction(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent==='取消采集并停止本次单音');return b&&!b.disabled});
    const stopped=page.waitForResponse(r=>r.url().endsWith(`/${record.run_id}/cancel`)&&r.request().method()==='POST');
    await panel.getByRole('button',{name:'取消采集并停止本次单音',exact:true}).click();
    const cancelled=await stopped;if(!cancelled.ok())throw new Error(await cancelled.text());
    await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(b=>b.textContent==='添加器件')?.disabled);
    const persisted=await(await page.request.get(`${api}/lab-profiles/${record.lab_profile_id}/fixed-route-acquisitions/${record.run_id}`)).json();
    if(persisted.status!=='cancelled')throw new Error(`未真实持久化取消：${persisted.status}`);
    await page.screenshot({path:'output/playwright/pc04a2-task6-lifecycle.png'});
    const result={passed:3,checks:['pending离开返回且历史失败保持图/模式/设备锁','running离开返回且历史失败保持锁','恢复真实run后POST取消、持久化cancelled且终态解锁'],run_id:record.run_id};
    await page.evaluate(result=>{window.__routeLifecycleResult=result},result);return result;
  }finally{release();await page.unroute('**/fixed-route-acquisitions**',reads)}
}
