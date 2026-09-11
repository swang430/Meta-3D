import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// P2-68：后端把损坏字段标进 connection.invalid_fields；抽屉必须把它显示出来，
// BS 认证徽标必须把「损坏」和「未认证」分开。这里是存在性门，行为门在后端
// tests/test_p2_68_catalog_invalid_stored_fields.py。
const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const generated = readFileSync(new URL('../src/types/api.generated.ts', import.meta.url), 'utf8')

test('equipment drawer renders every invalid stored field with its reason', () => {
  assert.match(appSource, /Object\.keys\(category\.connection\.invalid_fields\)\.length > 0 && \(/)
  assert.match(appSource, /Object\.entries\(category\.connection\.invalid_fields\)\.map\(\(\[field, reason\]\)/)
  assert.match(appSource, /服务器保存的配置有损坏字段/)
  // 提示按字段区分（Codex #471 R1 P2），不再对所有字段一概说「不能得到正式资格」
  assert.match(appSource, /invalidStoredFieldHint\(field\)/)
  assert.doesNotMatch(appSource, /这些字段已按「不可用」显示，不能得到正式资格/)
})

test('ordinary save routes the connection payload through withoutSynthesizedConnectionParams', () => {
  const start = appSource.indexOf('const handleSaveConnection = useCallback(')
  assert.ok(start > 0)
  const fn = appSource.slice(start, appSource.indexOf('[categories, drafts, instrumentMutation, showFeedback]', start))
  assert.match(fn, /withoutSynthesizedConnectionParams\(/)
  assert.match(fn, /category\?\.connection\.invalid_fields,\s*\n\s*draft\.connection_params,/)
  assert.match(fn, /connection: connectionPayload,/)
})

test('CE alignment input is disabled while stored connection_params is invalid', () => {
  const start = appSource.indexOf('label="F64 User Alignment 文件名"')
  assert.ok(start > 0)
  const block = appSource.slice(appSource.lastIndexOf('const connectionParamsInvalid', start), appSource.indexOf('<ChannelModelsCard', start))
  assert.match(block, /const connectionParamsInvalid = 'connection_params' in category\.connection\.invalid_fields/)
  assert.match(block, /disabled=\{connectionParamsInvalid\}/)
  assert.match(block, /error=\{connectionParamsInvalid \?/)
})

test('base station certification badge distinguishes corrupted from absent', () => {
  const start = appSource.indexOf('当前现场认证：')
  assert.ok(start > 0)
  const badge = appSource.slice(start, appSource.indexOf('服务器认证变化仅影响后续执行', start))
  assert.match(badge, /'base_station_site_certification' in category\.connection\.invalid_fields/)
  assert.match(badge, /认证数据损坏/)
  assert.match(badge, /未认证或已撤销，仅可诊断/)
  const colorExpr = appSource.slice(appSource.lastIndexOf('<Alert', start), start)
  assert.match(colorExpr, /'red' : 'yellow'/)
})

test('generated OpenAPI mirror carries invalid_fields on InstrumentConnection', () => {
  const start = generated.indexOf('InstrumentConnection: {')
  assert.ok(start > 0)
  const block = generated.slice(start, generated.indexOf('Cmw500FormalCapabilityUpdate: {', start))
  assert.match(block, /invalid_fields:\s*\{\s*\[key: string\]: string;?\s*\};?/)
})
