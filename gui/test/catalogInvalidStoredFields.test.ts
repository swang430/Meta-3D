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
  assert.match(fn, /category\?\.connection\.invalid_fields,\s*\n\s*draft\.connection_params_origin,/)
  assert.match(fn, /connection: connectionPayload,/)
  // 被守卫时不在客户端校验合成出来的空 profile（否则 CMW500 必填项会把保存拦下，且那份 profile 本来就不发）
  assert.match(fn, /const paramsGuarded = connectionParamsGuarded\(category\?\.connection\.invalid_fields, draft\.connection_params_origin\)/)
  assert.match(fn, /categoryKey === 'baseStation' && manifest && !paramsGuarded/)
})

test('BS adapter profile inputs are disabled while stored connection_params is guarded (Codex #471 R4)', () => {
  assert.match(appSource, /const bsParamsGuarded = connectionParamsGuarded\(category\.connection\.invalid_fields, draft\.connection_params_origin\)/)
  assert.match(appSource, /placeholder=\{field\.placeholder\}\s*\n\s*disabled=\{bsParamsGuarded\}/)
  // 守卫判据只有一个：保存路径 / CE alignment / BS profile 三处都调它
  assert.equal((appSource.match(/connectionParamsGuarded\(/g) ?? []).length, 3)
})

test('BS model change ignores deselect / same model like the CE planner does', () => {
  const start = appSource.indexOf('const handleModelChange = useCallback(')
  const bs = appSource.slice(appSource.indexOf("categoryKey === 'baseStation' && category", start), appSource.indexOf("categoryKey === 'channelEmulator' && category", start))
  assert.match(bs, /if \(!modelId \|\| drafts\[categoryKey\]\?\.modelId === modelId\) return/)
})

test('drafts carry connection_params provenance from every (re)hydration point (Codex #471 R2 P1)', () => {
  assert.match(appSource, /connection_params_origin\?: 'server' \| 'invalid'/)
  // 目录刷新 effect 与保存成功后的草稿更新都经 nextConnectionParamsDraft，不再直接 previous ?? server
  assert.equal((appSource.match(/nextConnectionParamsDraft\(/g) ?? []).length, 2)
  assert.doesNotMatch(appSource, /connection_params: previous\?\.connection_params \?\?/)
  assert.match(appSource, /connectionParamsGuarded\(category\.connection\.invalid_fields, draft\.connection_params_origin\)/)
  // 操作员动作（rfSwitch JSON / CE alignment / BS·CE 切型号）都把草稿标成 'operator'，四处缺一不可
  assert.equal((appSource.match(/connection_params_origin: 'operator'/g) ?? []).length, 5) // JsonInput / alignment / BS 切型号 / CE 切型号 / BS profile 字段
  assert.match(appSource, /connection_params_origin\?: 'server' \| 'invalid' \| 'operator'/)
  // 从同一坏字段派生的 BS profile 草稿随 rehydrate 一起重建（轻量内审 F1）
  assert.match(appSource, /const rehydrated = previous\?\.connection_params_origin === 'invalid'/)
  assert.match(appSource, /const resyncProfile = rehydrated \|\| paramsDraft\.origin === 'invalid'/)
  assert.match(appSource, /base_station_profile: resyncProfile \? serverProfile : \(previous\?\.base_station_profile \?\? serverProfile\)/)
})

test('CE alignment input is disabled while stored connection_params is invalid', () => {
  const start = appSource.indexOf('label="F64 User Alignment 文件名"')
  assert.ok(start > 0)
  const block = appSource.slice(appSource.lastIndexOf('const connectionParamsInvalid', start), appSource.indexOf('<ChannelModelsCard', start))
  assert.match(block, /const connectionParamsInvalid = connectionParamsGuarded\(category\.connection\.invalid_fields, draft\.connection_params_origin\)/)
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
