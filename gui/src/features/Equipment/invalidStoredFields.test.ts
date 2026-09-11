import assert from 'node:assert/strict'
import test from 'node:test'

import {
  INVALID_STORED_FIELD_HINTS,
  invalidStoredFieldHint,
  nextConnectionParamsDraft,
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

test('guard survives the invalid→valid refetch until the draft is rehydrated (Codex #471 R2 P1)', () => {
  const payload = { endpoint: '1.2.3.4', controller: 'LAN', notes: '', connection_params: {} }
  // 标记已消失，但草稿仍是无效来源的空文本 → 仍不能发 {}
  const out = withoutSynthesizedConnectionParams(payload, {}, '', 'invalid')
  assert.equal('connection_params' in out, false)
  // 重建之后（origin 回 server）恢复显式全字段语义
  assert.deepEqual(withoutSynthesizedConnectionParams(payload, {}, '', 'server'), payload)
})

test('nextConnectionParamsDraft: invalid keeps an empty invalid-origin draft, repair rehydrates it, edits survive', () => {
  const invalid = { text: '', invalid: true }
  const repaired = { text: '{\n  "port": 3334\n}', invalid: false }
  // 第一次看到坏值
  assert.deepEqual(nextConnectionParamsDraft(undefined, invalid), { text: '', origin: 'invalid' })
  // 坏值期间刷新：仍是 invalid 来源，操作员若输入了文本（rfSwitch JsonInput）也保留；
  // 切型号 / preset 来的草稿（origin 'server'）在坏值期间保持自己的来源，修好后不做跨型号重建（内审 F2）
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'server' }, invalid), { text: '', origin: 'server' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'server' }, repaired), { text: '', origin: 'server' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'invalid' }, invalid), { text: '', origin: 'invalid' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"a":1}', origin: 'invalid' }, invalid), { text: '{"a":1}', origin: 'invalid' })
  // 管理员修好库 → 标记消失：未动的空草稿用服务器值重建
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'invalid' }, repaired), { text: repaired.text, origin: 'server' })
  // 操作员在坏值期间输入过的文本不被服务器值覆盖
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"a":1}', origin: 'invalid' }, repaired), { text: '{"a":1}', origin: 'server' })
  // 健康连接：沿用旧草稿（未保存编辑不丢）；没有旧草稿取服务器值
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"b":2}', origin: 'server' }, repaired), { text: '{"b":2}', origin: 'server' })
  assert.deepEqual(nextConnectionParamsDraft(undefined, repaired), { text: repaired.text, origin: 'server' })
})
