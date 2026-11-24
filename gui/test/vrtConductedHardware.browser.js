// 由浏览器测试运行器挂载传导执行窗口。所有请求均在浏览器内拦截。
export async function verifyConductedStart(page, openModal) {
  const snapshot = {
    calibration_id: 'cal-1', ready: true, reasons: [], scenario_id: 'scenario', scenario_version: '1',
    asset: { name: '测试工程', sha256: 'abc' }, binding: { execution_mode: 'real', real_preflight: { calibration: { id: 'cal-1', evidence_sha256: 'a'.repeat(64), applicable: true, ports: [], reasons: [] } } }, port_mapping: [],
  }
  let starts = 0
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data = {}
    if (path.endsWith('/options')) data = { labs: [], assets: [], topologies: [] }
    if (path.endsWith('/calibrations')) data = []
    if (path.endsWith('/executions/sample')) data = { mode: 'conducted', scenario_id: 'scenario', config: { conducted: snapshot } }
    if (path.endsWith('/status')) data = { status: 'idle', warnings: [] }
    if (path.endsWith('/control')) starts++
    await route.fulfill({ json: data })
  })
  await openModal()
  const button = page.getByRole('button', { name: '启动传导测试' })
  await page.getByText(/服务端状态 等待启动/).waitFor()
  await Promise.all([page.waitForResponse(r => r.url().endsWith('/control')), button.click({ timeout: 2000 })])
  if (starts !== 1) throw Error('准备通过的真实模式没有发起启动请求')
  for (const [ready, mode, applicable] of [[false, 'real', true], [true, null, true], [true, 'real', false]]) {
    snapshot.binding.real_preflight.calibration.applicable = applicable
    snapshot.ready = ready
    snapshot.binding.execution_mode = mode
    await openModal()
    await page.getByText(/服务端状态 等待启动/).waitFor()
    if (!await button.isDisabled()) throw Error('准备有缺项或模式未知时允许启动')
  }
}

export async function verifyCalibrationRegistration(page, openDraft) {
  const record = { id: 'cal-1', issuer: '现场测量室', evidence_sha256: '固定测试摘要', revoked_at: null, revocation_reason: null }
  const request = { report_file: '校准.json' }
  let registered = false
  await page.route('**/api/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    let data = {}
    if (path.endsWith('/options')) data = { labs: [], assets: [], topologies: [] }
    if (path.endsWith('/calibrations/cal-1')) data = { ...record, ...request, evidence_b64: 'e30=', readings_b64: 'YQ==' }
    if (path.endsWith('/calibrations')) {
      if (req.method() === 'POST') {
        if (JSON.stringify(req.postDataJSON()) !== JSON.stringify(request)) throw Error('登记请求与审核文件名不一致')
        registered = true
        data = record
      } else data = registered ? [record] : []
    }
    if (path.endsWith('/prepare')) {
      const selected = req.postDataJSON().calibration_id === record.id
      const reading = { peak_dbm: -20, uncertainty_db: 1, max_safe_input_dbm: -10 }
      const calibration = { applicable: selected, reasons: selected ? [] : ['请选择逐端口校准'], ports: selected ? [{
        tx: 1, rx: 2, input_port: 3, output_port: 4, emulator_input: reading, dut_input: reading,
        emulator_input_margin_db: 9, dut_input_margin_db: 9,
      }] : [] }
      data = { ready: false, scenario_version: '1', reasons: ['基站尚未就绪'], port_mapping: [],
        binding: { execution_mode: 'real', real_preflight: { calibration } } }
    }
    await route.fulfill({ json: data })
  })
  await openDraft()
  await page.getByText('请选择逐端口校准', { exact: true }).waitFor()
  const filename = page.getByRole('textbox', { name: '实验室已审核目录中的报告文件名' })
  const register = page.getByRole('button', { name: '登记逐端口校准' })
  await filename.fill('../校准.json')
  if (!await register.isDisabled()) throw Error('允许登记审核目录之外的文件')
  await filename.fill(request.report_file)
  await register.click()
  await page.getByText('逐端口校准适用于本次执行').waitFor()
  await page.getByRole('cell', { name: '仿真器输入 3' }).waitFor()
  await page.getByRole('cell', { name: '车载设备输入 2' }).waitFor()
  await page.getByRole('link', { name: '下载仪器原始读数' }).waitFor()
  await page.getByText('基站尚未就绪').waitFor()
  if (!await page.getByRole('button', { name: '启动传导测试' }).isDisabled()) throw Error('仍有缺项却允许启动')
}
