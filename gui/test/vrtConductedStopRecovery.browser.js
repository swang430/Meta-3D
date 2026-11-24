// 每次重新打开窗口都从状态接口读取原执行的持久化复核标志。
export async function verifyConductedStopRecovery(page, openModal) {
  let pending = true
  let attempts = 0
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let json = {}
    let status = 200
    if (path.endsWith('/executions/sample')) json = { mode: 'conducted', scenario_id: 'scenario', config: {} }
    if (path.endsWith('/executions/sample/status')) json = { status: 'failed', warnings: [], conducted_stop_pending: pending }
    if (path.endsWith('/executions/sample/control')) {
      if (route.request().postDataJSON().action !== 'stop') throw Error('恢复操作未请求停止原执行')
      if (++attempts === 1) {
        status = 409
        json = { detail: '设备尚未确认停止' }
      } else pending = false
    }
    await route.fulfill({ status, json })
  })
  const retry = page.getByRole('button', { name: '重新停止并核对设备状态' })
  await openModal()
  await retry.waitFor({ timeout: 3000 })
  if (await page.getByRole('button', { name: '重新准备一次执行' }).count()) throw Error('停止待复核时允许切换执行')
  await retry.click()
  await page.getByText('设备尚未确认停止', { exact: true }).waitFor()
  if (!await retry.isEnabled()) throw Error('设备拒绝后无法再次请求停止')
  await openModal()
  await retry.click()
  await retry.waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: '重新准备一次执行' }).waitFor()
  await openModal()
  await page.getByText(/服务端状态 执行失败/).waitFor()
  if (await retry.count() || attempts !== 2) throw Error('确认停止后仍显示复核入口或重复发出指令')
}
