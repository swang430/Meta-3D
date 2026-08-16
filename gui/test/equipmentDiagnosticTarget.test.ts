import test from 'node:test'
import assert from 'node:assert/strict'

import { buildDiagnosticTarget } from '../src/features/Equipment/diagnosticTarget.ts'

test('single-session categories use saved HAL session without address override', () => {
  for (const categoryKey of ['baseStation', 'channelEmulator']) {
    assert.deepEqual(
      buildDiagnosticTarget(categoryKey, '10.20.30.40:5025', '10.20.30.40:5025'),
      { payload: {} },
    )
  }
})

test('single-session categories block unsaved endpoint edits', () => {
  const result = buildDiagnosticTarget(
    'baseStation',
    '10.20.30.99:5025',
    '10.20.30.40:5025',
  )

  assert.equal(result.payload, undefined)
  assert.match(result.error ?? '', /先保存配置并重新加载 HAL/)
})

test('other categories keep one-time endpoint override', () => {
  assert.deepEqual(
    buildDiagnosticTarget('vna', '10.20.30.50:5025', '10.20.30.40:5025'),
    { payload: { ip: '10.20.30.50', port: 5025 } },
  )
})
