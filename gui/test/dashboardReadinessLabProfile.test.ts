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
  assert.match(source, /queryFn:\s*\(\)\s*=>\s*fetchReadiness\(selectedLabProfileId\s*\?\?\s*undefined\)/)
  assert.match(source, /enabled:\s*!labLoading/)
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
