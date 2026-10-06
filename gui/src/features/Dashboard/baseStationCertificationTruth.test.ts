import assert from 'node:assert/strict'
import test from 'node:test'
import { projectBaseStationCertificationTruth } from './baseStationBindingTruth.ts'

test('坏认证覆盖绿色和诊断 binding，但不会伪造资格', () => {
  for (const light of ['green', 'yellow'] as const) {
    const view = projectBaseStationCertificationTruth(
      { light, valueText: '已解析', detail: 'binding' },
      null, 'invalid', '存量认证无效', 'digest',
    )
    assert.equal(view.light, 'red')
    assert.match(view.valueText, /认证.*损坏/)
    assert.match(view.detail, /存量认证无效/)
  }
})

test('缺失仍是诊断态，不冒充损坏', () => {
  const view = projectBaseStationCertificationTruth(
    { light: 'green', valueText: '已解析', detail: 'binding' },
    null, 'missing', null, 'digest',
  )
  assert.equal(view.light, 'yellow')
  assert.match(view.detail, /尚无现场认证/)
})
