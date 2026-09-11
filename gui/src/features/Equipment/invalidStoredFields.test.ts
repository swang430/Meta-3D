import assert from 'node:assert/strict'
import test from 'node:test'

import {
  INVALID_STORED_FIELD_HINTS,
  connectionParamsGuarded,
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

const BAD = { connection_params: 'connection_params must be a JSON object' }

test('guard matrix: invalid-origin drafts never send; while the marker is present only operator edits send; healthy drafts send as-is', () => {
  // (marker, origin) → guarded?
  const cases: Array<[Record<string, string> | undefined, 'server' | 'invalid' | 'operator' | undefined, boolean]> = [
    [BAD, 'server', true],       // 服务器说坏了，灌入的旧文本不可信（R3 P1）
    [BAD, 'invalid', true],
    [BAD, 'operator', false],    // 操作员明确改过 → 填了照发
    [BAD, undefined, true],
    [{}, 'invalid', true],       // 标记消失但草稿尚未重建（R2 P1）
    [{}, 'server', false],
    [{}, 'operator', false],
    [undefined, undefined, false],
    [{ base_station_model_presets: 'bad' }, 'server', false], // 别的字段坏不影响
  ]
  for (const [marker, origin, expected] of cases) {
    assert.equal(connectionParamsGuarded(marker, origin), expected, `${JSON.stringify(marker)} / ${origin}`)
  }
  const payload = { endpoint: '1.2.3.4', controller: 'LAN', notes: '', connection_params: { stale: 1 } }
  const dropped = withoutSynthesizedConnectionParams(payload, BAD, 'server')
  assert.equal('connection_params' in dropped, false)
  assert.deepEqual(dropped, { endpoint: '1.2.3.4', controller: 'LAN', notes: '' })
  assert.deepEqual(payload.connection_params, { stale: 1 }) // 不改入参
  assert.deepEqual(withoutSynthesizedConnectionParams(payload, BAD, 'operator'), payload)
  assert.deepEqual(withoutSynthesizedConnectionParams(payload, {}, 'server'), payload)
})

test('BS adapter profile is derived from the same stored field and leaves the payload together with it', () => {
  const bs = { endpoint: 'x', controller: 'LAN', notes: '', connection_params: { stale: 1 }, base_station_adapter_profile: { pcc_bb_board: 'stale' } }
  const dropped = withoutSynthesizedConnectionParams(bs, BAD, 'server')
  assert.deepEqual(dropped, { endpoint: 'x', controller: 'LAN', notes: '' })
  assert.deepEqual(withoutSynthesizedConnectionParams(bs, BAD, 'operator'), bs)
  assert.deepEqual(withoutSynthesizedConnectionParams(bs, {}, 'server'), bs)
})

test('nextConnectionParamsDraft: server text is dropped when the row turns invalid, operator text survives, repair rehydrates', () => {
  const invalid = { text: '', invalid: true }
  const repaired = { text: '{\n  "port": 3334\n}', invalid: false }
  // 首次看到坏值 / 坏值期间刷新
  assert.deepEqual(nextConnectionParamsDraft(undefined, invalid), { text: '', origin: 'invalid' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'invalid' }, invalid), { text: '', origin: 'invalid' })
  // 健康草稿所在的行变坏：从服务器灌入的旧 JSON 不可信 → 清空并标 invalid（R3 P1）
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"stale": 1}', origin: 'server' }, invalid), { text: '', origin: 'invalid' })
  // 操作员改过的文本（rfSwitch JsonInput / 切型号选的 preset）在坏值期间保留
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"a":1}', origin: 'operator' }, invalid), { text: '{"a":1}', origin: 'operator' })
  // 修好：invalid 草稿用服务器值重建；operator / server 草稿沿用（不重刷未保存编辑、不跨型号重建）
  assert.deepEqual(nextConnectionParamsDraft({ text: '', origin: 'invalid' }, repaired), { text: repaired.text, origin: 'server' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"a":1}', origin: 'operator' }, repaired), { text: '{"a":1}', origin: 'operator' })
  assert.deepEqual(nextConnectionParamsDraft({ text: '{"b":2}', origin: 'server' }, repaired), { text: '{"b":2}', origin: 'server' })
  assert.deepEqual(nextConnectionParamsDraft(undefined, repaired), { text: repaired.text, origin: 'server' })
})

test('R3 scenario end to end: healthy draft → row corrupted → unrelated save must not send the stale JSON', () => {
  const hydrated = nextConnectionParamsDraft(undefined, { text: '{"port": 3334}', invalid: false })
  const afterCorruption = nextConnectionParamsDraft(hydrated, { text: '', invalid: true })
  const payload = { endpoint: 'x', controller: 'LAN', notes: '改备注', connection_params: JSON.parse(hydrated.text) }
  assert.equal('connection_params' in withoutSynthesizedConnectionParams(payload, BAD, afterCorruption.origin), false)
  // 即使刷新还没跑到（草稿仍是 server 来源），标记一到就已经守住
  assert.equal('connection_params' in withoutSynthesizedConnectionParams(payload, BAD, hydrated.origin), false)
})
