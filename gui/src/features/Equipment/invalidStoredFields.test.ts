import assert from 'node:assert/strict'
import test from 'node:test'

import {
  INVALID_STORED_FIELD_HINTS,
  invalidStoredFieldHint,
  withoutSynthesizedConnectionParams,
} from './invalidStoredFields.ts'

const PROJECTED_STORED_FIELDS = [
  'base_station_site_certification',
  'channel_emulator_site_certification',
  'base_station_model_presets',
  'channel_emulator_model_presets',
  'connection_params',
]

test('every projected stored field has a hint, and only certification hints talk about formal qualification', () => {
  assert.deepEqual(Object.keys(INVALID_STORED_FIELD_HINTS).sort(), [...PROJECTED_STORED_FIELDS].sort())
  for (const field of PROJECTED_STORED_FIELDS) {
    const hint = invalidStoredFieldHint(field)
    const aboutQualification = /不能获得资格/.test(hint)
    const isCertification = field.endsWith('_site_certification')
    assert.equal(aboutQualification, isCertification, `${field}: ${hint}`)
    if (!isCertification) assert.match(hint, /不影响现场认证与正式资格|不再把空草稿当作新值发送/)
  }
  assert.match(invalidStoredFieldHint('something_else'), /不可用/)
})

test('an invalid stored connection_params with an empty draft is not sent as {}', () => {
  const payload = { endpoint: '1.2.3.4', controller: 'LAN', notes: '', connection_params: {} }
  const out = withoutSynthesizedConnectionParams(
    payload,
    { connection_params: 'connection_params must be a JSON object' },
    '',
  )
  assert.equal('connection_params' in out, false)
  assert.deepEqual(out, { endpoint: '1.2.3.4', controller: 'LAN', notes: '' })
  assert.deepEqual(payload.connection_params, {}) // 不改入参
})

test('operator-typed JSON still wins even when the stored value is invalid', () => {
  const payload = { endpoint: '1.2.3.4', controller: 'LAN', notes: '', connection_params: { a: 1 } }
  const out = withoutSynthesizedConnectionParams(payload, { connection_params: 'bad' }, '{"a": 1}')
  assert.deepEqual(out, payload)
})

test('a healthy connection keeps the explicit full-field semantics (empty object is sent as-is)', () => {
  const payload = { endpoint: '1.2.3.4', controller: 'LAN', notes: '', connection_params: {} }
  assert.deepEqual(withoutSynthesizedConnectionParams(payload, {}, ''), payload)
  assert.deepEqual(withoutSynthesizedConnectionParams(payload, undefined, ''), payload)
  assert.deepEqual(
    withoutSynthesizedConnectionParams(payload, { base_station_model_presets: 'bad' }, ''),
    payload,
  )
})
