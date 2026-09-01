import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8')

test('all API mirrors expose policy, certification and frozen qualification', () => {
  const generated = read('./api.generated.ts')
  const handwritten = read('./api.ts')
  const testPlan = read('../api/testPlanService.ts')
  const commissioningApi = read('../components/Commissioning/api.ts')
  const manifest = read('./baseStationManifest.ts')
  for (const token of [
    'TestCaseExecutionPolicy',
    'BaseStationSiteCertification',
    'ExecutionQualification',
    'execution_classification',
  ]) {
    assert.match(generated, new RegExp(token))
    assert.match(handwritten + testPlan + commissioningApi, new RegExp(token))
  }
  assert.match(manifest, /formal_gate: 'site_certification'/)
})

test('TestCase editor uses dedicated audited policy and commissioning sends no raw cal authority', () => {
  const editor = read('../components/TestPlanManagement/TestCaseEditModal.tsx')
  const service = read('../api/testPlanService.ts')
  const sessionBody = read('../components/Commissioning/sessionBody.ts')
  const commissioning = read('../components/Commissioning/index.tsx')
  assert.match(editor, /Diagnostic/)
  assert.match(editor, /Formal/)
  assert.match(editor, /policyReason/)
  assert.match(editor, /policyUpdatedBy/)
  assert.match(service, /updateTestCaseExecutionPolicy/)
  assert.doesNotMatch(sessionBody, /precheck_strict_cal/)
  assert.doesNotMatch(commissioning, /calBypass/)
})

test('GUI visibly distinguishes diagnostic snapshots from formal results', () => {
  const commissioning = read('../components/Commissioning/index.tsx')
  const app = read('../App.tsx')
  const history = read('../features/TestManagement/components/HistoryTab/HistoryTab.tsx')
  const selector = read('../features/Reports/components/ExecutionSelector.tsx')
  const readiness = read('../features/Dashboard/ZoneReadiness.tsx')
  const mimoConfig = read('../components/TestCaseConfig/MIMOOTAConfigForm.tsx')
  assert.match(commissioning, /execution_qualification/)
  assert.match(commissioning, /仅可诊断/)
  assert.match(app, /base_station_site_certification/)
  assert.match(app, /撤销现场认证/)
  assert.match(app, /source_execution_id/)
  assert.match(history, /execution_evidence_outcome/)
  assert.match(history, /diagnostic_completed/)
  assert.match(history, /不形成正式判定/)
  assert.match(selector, /execution_evidence_outcome/)
  assert.match(selector, /仅诊断/)
  assert.match(readiness, /base_station_site_certification/)
  assert.match(readiness, /未取得匹配现场认证/)
  assert.match(mimoConfig, /历史兼容快照，不授予本次执行正式资格/)
})
