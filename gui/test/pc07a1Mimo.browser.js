// Task3 补验：真实 MIMO OTA 启动入口，全 Mock；遇既有门保留阻塞，不改 policy 绕过。
async page => {
  const api = 'http://127.0.0.1:18089/api/v1';
  const records = [];
  const call = async (method, path, data) => {
    const response = await page.request[method](api + path, data ? {data} : undefined);
    const body = await response.json();
    const result = {method, path, request: data ?? null, status: response.status(), body};
    records.push(result);
    return result;
  };
  const hal = await call('get', '/instruments/hal/status');
  if (hal.body.mode !== 'mock' || hal.body.driver_count !== 4) throw Error('必须为隔离四类全Mock HAL');
  const labs = await call('get', '/lab-profiles');
  const lab = labs.body.find(row => row.instrument_bindings.length === 4);
  if (!lab) throw Error('必须先运行专属 prepare-mimo 夹具');
  const created = await call('post', '/test-plans/cases', {
    name: 'PC07A1 实际全Mock MIMO OTA（非真机认证）', test_type: 'MIMO_OTA',
    lab_profile_id: lab.id, created_by: 'PC07A1-browser',
    configuration: {frequency_hz:2595e6, bandwidth_mhz:100, azimuths_deg:[0],
      settling_time_s:0, num_samples_per_azimuth:1, switch_mode_id:'mimo_ota',
      base_station_config_mode:'dispatch'},
  });
  if (created.status !== 201) throw Error(JSON.stringify(created));
  const launch = await call('post', `/test-plans/cases/${created.body.id}/execute`);
  if (launch.status !== 202) return {blocked:true, stage:'launch_freeze', case_id:created.body.id, records};
  const id = launch.body.execution_id;
  let terminal;
  for (let i = 0; i < 240; i++) {
    terminal = await call('get', `/test-plans/cases/executions/${id}`);
    if (terminal.body.status !== 'running') break;
    await page.waitForTimeout(250);
  }
  if (terminal.body.status === 'running') return {blocked:true, stage:'terminal_timeout', execution_id:id, records};
  const report = await call('post', '/reports', {title:'PC07A1 实际全Mock MIMO OTA审计',
    report_type:'single_execution',format:'pdf',generated_by:'PC07A1-browser',test_execution_ids:[id]});
  if (report.status !== 201) throw Error(JSON.stringify(report));
  const generated = await call('post', `/reports/${report.body.id}/generate`);
  if (generated.status !== 200) return {blocked:true, stage:'report_generation', execution_id:id, records};
  const detail = await call('get', `/reports/${report.body.id}`);
  const content = detail.body.content_data;
  if (detail.status !== 200 || content.overall_result === 'passed' || content.formal_rf_kpi_verified ||
      content.formal_quiet_zone_verified || content.formal_path_loss_verified)
    throw Error('Mock不得形成正式PASS/正式量值');
  return {blocked:false, execution_id:id, terminal:terminal.body.status, records};
}
