import test from 'node:test'
import assert from 'node:assert/strict'

import { buildLogFileCatalog } from '../src/features/Reports/logFileCatalog.ts'

const files = [
  {
    filename: 'app.log',
    size_bytes: 1024,
    size_human: '1.0 KB',
    last_modified: '2026-08-12 09:00:00',
    is_current: true,
  },
  {
    filename: 'app.log.2026-08-11',
    size_bytes: 2048,
    size_human: '2.0 KB',
    last_modified: '2026-08-12 00:00:01',
    is_current: false,
  },
  {
    filename: 'exec-848a0000-dead-beef.log',
    size_bytes: 4096,
    size_human: '4.0 KB',
    last_modified: '2026-08-11 13:21:09',
    is_current: false,
  },
  {
    filename: 'custom.log.1',
    size_bytes: 8192,
    size_human: '8.0 KB',
    last_modified: '2026-08-10 08:07:06',
    is_current: false,
  },
]

test('separates current, classified history, and execution history', () => {
  const catalog = buildLogFileCatalog(files)

  assert.deepEqual(catalog.current.map((option) => option.value), ['app.log'])
  assert.deepEqual(
    catalog.historyCategory.map((option) => option.value),
    ['app.log.2026-08-11', 'custom.log.1'],
  )
  assert.deepEqual(
    catalog.historyExecution.map((option) => option.value),
    ['exec-848a0000-dead-beef.log'],
  )
})

test('classified history labels contain searchable date, category, filename, and size', () => {
  const catalog = buildLogFileCatalog(files)

  assert.match(catalog.current[0].label, /应用日志.*app\.log.*1\.0 KB/)
  assert.match(
    catalog.historyCategory[0].label,
    /2026-08-11.*应用日志.*app\.log\.2026-08-11.*2\.0 KB/,
  )
  assert.match(
    catalog.historyCategory[1].label,
    /2026-08-10.*custom\.log\.1.*8\.0 KB/,
  )
})

test('execution history labels contain searchable time, full execution id, and filename', () => {
  const option = buildLogFileCatalog(files).historyExecution[0]

  assert.match(option.label, /2026-08-11 13:21/)
  assert.match(option.label, /848a0000-dead-beef/)
  assert.match(option.label, /exec-848a0000-dead-beef\.log/)
})
