// 真实页面与隔离Mock API；不伪造响应、不直接调用React handler。
// 由持久Playwright会话调用导出函数；普通布局、专注和展开都消费真实DOM。
export default async function verifyWorkspace(page, {baselineHeight, red=false}={}) {
  page.setDefaultTimeout(3000);
  const checks=[];
  const check=async(name,fn)=>{try{await fn();checks.push({name,passed:true})}catch(error){checks.push({name,passed:false,error:String(error)});if(!red)throw error}};
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  const canvas=page.getByTestId('topology-canvas'),panel=page.getByTestId('route-calibration-panel');
  const height=async()=>canvas.evaluate(el=>el.getBoundingClientRect().height);
  await check('普通画布和校准栏至少为原编辑高度3倍',async()=>{
    assert(baselineHeight>0,'须先在BASE测量原高度');
    assert(await height()>=baselineHeight*3,`现${await height()}，原${baselineHeight}`);
    assert(await panel.evaluate(el=>el.getBoundingClientRect().height)>=baselineHeight*3,'校准栏未同步增高');
  });
  await check('专注保留可见校准栏且返回不重建实例',async()=>{
    const node=await panel.elementHandle();
    await page.getByRole('button',{name:'专注编辑',exact:true}).click();
    const visible=await panel.isVisible();
    await page.getByRole('button',{name:'退出专注编辑',exact:true}).click();
    assert(visible,'专注隐藏了校准栏');
    assert(await panel.evaluate((el,before)=>el===before,node),'专注重建了校准栏');
    await node.dispose();
  });
  if(await page.getByRole('button',{name:'展开辅助区',exact:true}).isVisible())await page.getByRole('button',{name:'展开辅助区',exact:true}).click();
  await check('校准展开及返回保留同一实例和输入',async()=>{
    const node=await panel.elementHandle();
    const input=panel.getByLabel(/^采集频率（MHz）/);
    await input.fill('2595');
    await page.getByRole('button',{name:'展开校准面板',exact:true}).click();
    const box=await panel.boundingBox();assert(box.width>page.viewportSize().width*.8,'展开未利用窗口宽度');
    await page.getByRole('button',{name:'返回拓扑与校准',exact:true}).click();
    assert(await input.inputValue()==='2595','输入丢失');
    assert(await panel.evaluate((el,before)=>el===before,node),'展开重建了校准栏');
    await node.dispose();
  });
  return checks;
}
