import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const typeSource = readFileSync(
  new URL('../src/features/Reports/types/index.ts', import.meta.url),
  'utf8',
)
const apiSource = readFileSync(
  new URL('../src/features/Reports/api/reportsAPI.ts', import.meta.url),
  'utf8',
)
const listSource = readFileSync(
  new URL('../src/features/Reports/components/ReportList.tsx', import.meta.url),
  'utf8',
)
const generationHookSource = readFileSync(
  new URL('../src/features/Reports/hooks/useReportGeneration.ts', import.meta.url),
  'utf8',
)

test('report summaries expose the backend recovery truth', () => {
  assert.match(typeSource, /requires_regeneration:\s*boolean/)
  assert.match(typeSource, /regeneration_available:\s*boolean/)
  assert.match(typeSource, /regeneration_reason\?:\s*string/)
})

test('completed legacy reports offer recovery instead of unsafe download', () => {
  assert.match(listSource, /report\.requires_regeneration/)
  assert.match(listSource, /report\.regeneration_available/)
  assert.match(listSource, /report\.regeneration_reason/)
  assert.match(
    listSource,
    /report\.status === 'completed'\s*&&\s*!report\.requires_regeneration/,
  )
  assert.match(listSource, /重生成安全报告/)
  assert.match(listSource, /不可安全恢复/)
})

test('legacy recovery is the only available report action until regeneration', () => {
  assert.match(
    listSource,
    /onView\s*&&\s*!report\.requires_regeneration/,
  )
  assert.match(
    listSource,
    /!report\.requires_regeneration\s*&&\s*\(report\.status === 'pending' \|\| report\.status === 'failed'\)/,
  )
})

test('report API errors preserve JSON and Blob response detail', () => {
  assert.match(apiSource, /export async function reportApiErrorMessage/)
  assert.match(apiSource, /data instanceof Blob/)
  assert.match(apiSource, /await data\.text\(\)/)
  assert.match(apiSource, /payload\.detail/)
  assert.equal(
    (apiSource.match(/reportApiErrorMessage\(error\)/g) ?? []).length,
    2,
  )
})

test('VRT recovery uses the server-owned terminal archive path', () => {
  assert.match(generationHookSource, /RoadTestAPI\.archiveExecutionReport\(record\.execution_id\)/)
  const vrtMutation = generationHookSource.slice(
    generationHookSource.indexOf('const vrtMutation'),
    generationHookSource.indexOf('// Generate report for a test execution'),
  )
  assert.doesNotMatch(vrtMutation, /road_test_execution_id:/)
  assert.doesNotMatch(vrtMutation, /content_data:/)
  assert.match(vrtMutation, /ReportsAPI\.reportApiErrorMessage\(error\)/)
})
