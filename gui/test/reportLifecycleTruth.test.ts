import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const reportTypes = readFileSync(
  new URL('../src/types/report.ts', import.meta.url),
  'utf8',
)
const roadTestTypes = readFileSync(
  new URL('../src/types/roadTest.ts', import.meta.url),
  'utf8',
)
const viewer = readFileSync(
  new URL('../src/components/Report/ReportViewer.tsx', import.meta.url),
  'utf8',
)

test('pending report lifecycle remains distinct in both type mirrors', () => {
  assert.match(reportTypes, /overall_result:\s*'passed'\s*\|\s*'failed'\s*\|\s*'pending'/)
  assert.match(roadTestTypes, /overall_result:\s*'passed'\s*\|\s*'failed'\s*\|\s*'pending'/)
})

test('pending report lifecycle is displayed as waiting, not incomplete', () => {
  assert.match(viewer, /pending:\s*\{[^}]*label:\s*'等待中'/s)
})
