import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8')

test('history and report surfaces consume server-owned completion semantics', () => {
  const history = read('../features/TestManagement/components/HistoryTab/HistoryTab.tsx')
  const selector = read('../features/Reports/components/ExecutionSelector.tsx')
  const reportList = read('../features/Reports/components/ReportList.tsx')
  const viewer = read('../components/Report/ReportViewer.tsx')

  for (const source of [history, selector, reportList, viewer]) {
    assert.match(source, /execution_evidence_outcome/)
    assert.match(source, /completion_semantic/)
  }
  assert.match(history, /valid_test_completed/)
  assert.match(history, /diagnostic_completed/)
  assert.match(history, /pipeline_completed/)
  const completionBadge = history
    .split('function getCompletionBadge', 2)[1]
    .split('// 来源链显示名', 1)[0]
  assert.doesNotMatch(
    completionBadge,
    /record\.status\s*===?\s*['"]completed['"]/,
  )
  assert.match(reportList, /证据无效/)
  assert.match(viewer, /仅审计/)
  assert.match(viewer, /report\?\.execution_evidence_outcome/)
  assert.match(viewer, /<ReportContent[^>]*outcome=/s)
})

test('API mirrors expose the immutable outcome instead of rebuilding it in GUI', () => {
  const generated = read('./api.generated.ts')
  const handwritten = read('./api.ts')
  const testPlan = read('../api/testPlanService.ts')
  const testManagement = read('../features/TestManagement/types/index.ts')
  const report = read('./report.ts')

  for (const source of [generated, handwritten]) {
    assert.match(source, /ExecutionEvidenceOutcome/)
    assert.match(source, /completion_semantic/)
  }
  for (const source of [testPlan, testManagement, report]) {
    assert.match(source, /ExecutionEvidenceOutcome/)
    assert.match(source, /execution_evidence_outcome/)
  }
})
