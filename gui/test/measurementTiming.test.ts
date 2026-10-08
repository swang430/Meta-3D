import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('有效测量控件不再声称未生效的时长和间隔', () => {
  const source = readFileSync(new URL('../src/components/TestCaseConfig/MIMOOTAConfigForm.tsx', import.meta.url), 'utf8')
  assert.ok(!source.includes('label="单方位测量时长"'))
  assert.ok(!source.includes('label="采样间隔"'))
  assert.ok(source.includes('label="每方位请求窗口数"'))
  assert.ok(source.includes('统计长度不是实际墙钟时间'))
})

test('历史 MIMO 行的旧时长不能继续显示为有效预计时长', () => {
  const source = readFileSync(new URL('../src/components/TestPlanManagement/TestCaseLibrary.tsx', import.meta.url), 'utf8')
  assert.ok(source.includes("tc.test_type !== 'MIMO_OTA' && tc.test_duration_sec"))
})
