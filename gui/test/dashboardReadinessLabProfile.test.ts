import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const read = (rel: string) =>
  readFileSync(join(import.meta.dirname, '..', rel), 'utf8')

test('readiness API 只在显式选择 LabProfile 时发送 lab_profile_id', () => {
  const source = read('src/api/service.ts')
  const start = source.indexOf('export const fetchReadiness')
  const end = source.indexOf('/**', start + 1)
  const fn = source.slice(start, end)

  assert.match(fn, /fetchReadiness\s*=\s*async\s*\(labProfileId\?:\s*string\)/)
  assert.match(fn, /lab_profile_id\s*:\s*labProfileId/)
  assert.match(fn, /labProfileId\s*\?[^:]+lab_profile_id/s)
})

test('Dashboard readiness 消费顶部唯一 LabProfile 真源并按选择隔离缓存', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')

  assert.match(source, /useOperationalLab/)
  assert.match(source, /const\s*\{[^}]*selectedLabProfileId[^}]*loading[^}]*\}\s*=\s*useOperationalLab\(\)/s)
  assert.match(source, /queryKey:\s*\['cockpit',\s*'readiness',\s*selectedLabProfileId/)
  assert.match(source, /queryFn:\s*\(\)\s*=>\s*fetchReadiness\(selectedLabProfileId!\)/)
  assert.match(source, /enabled:\s*!labLoading\s*&&\s*Boolean\(selectedLabProfileId\)/)
  assert.doesNotMatch(source, /fetchLabProfiles|useState\([^)]*LabProfile/)
})

test('HAL unavailable 只把 HAL-owned 区域标为不可用，不否定实时 Lab 与校准', () => {
  const dashboard = read('src/features/Dashboard/ZoneReadiness.tsx')
  const service = read('src/api/service.ts')

  assert.match(dashboard, /仪表驱动和子网状态暂不可用/)
  assert.match(dashboard, /LabProfile 与校准状态仍来自实时配置/)
  assert.doesNotMatch(dashboard, /以下为占位状态，不代表实时设备/)
  assert.doesNotMatch(service, /sub-sections carry\s+\* placeholder values/)
})

test('HAL unavailable 必须进入总判阻塞，不能只显示提示后仍发布可开测', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')
  const verdict = source.slice(
    source.indexOf('function buildVerdict'),
    source.indexOf('function SubnetSection'),
  )

  assert.match(verdict, /available:\s*boolean/)
  assert.match(verdict, /if\s*\(!available\)[\s\S]*canStart:\s*false/)
  assert.match(source, /buildVerdict\(buildCells\(readiness\),\s*readiness\.available\)/)
})

test('顶部没有显式 LabProfile 时不发隐式请求并显示阻断', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')

  assert.match(source, /enabled:\s*!labLoading\s*&&\s*Boolean\(selectedLabProfileId\)/)
  assert.match(source, /queryFn:\s*\(\)\s*=>\s*fetchReadiness\(selectedLabProfileId!\)/)
  assert.match(source, /请先在顶部选择当前 LabProfile/)
  assert.doesNotMatch(source, /selectedLabProfileId\s*\?\?\s*undefined/)
})

test('轮询错误时不发布缓存中的旧 readiness 绿灯', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')
  const component = source.slice(source.indexOf('export function ZoneReadiness'))
  const render = component.slice(component.indexOf('return ('))

  assert.match(component, /const readiness\s*=\s*!isFetching\s*&&\s*!error\s*&&\s*selectedLabProfileId\s*\?\s*data\s*:\s*undefined/)
  assert.doesNotMatch(render, /\{data\s*&&/)
  assert.match(source, /就绪状态读取失败 · 不可开测/)
})

test('切回已有缓存的 LabProfile 时必须等本次刷新完成后才发布', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')

  assert.match(source, /const\s*\{[^}]*isFetching[^}]*\}\s*=\s*useQuery\(/s)
  assert.match(source, /const readiness\s*=\s*!isFetching\s*&&/)
  assert.match(source, /正在确认所选 LabProfile 的最新就绪状态/)
})
