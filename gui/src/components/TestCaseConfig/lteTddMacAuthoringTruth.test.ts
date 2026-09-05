import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(
  new URL('./MIMOOTAConfigForm.tsx', import.meta.url),
  'utf8',
)

test('LTE TDD form exposes typed frame controls and routes edits through canonical draft', () => {
  for (const token of [
    "{ value: 'tdd', label: 'TDD' }",
    'updateLteDuplex',
    'LTE_TDD_ULDL_CONFIGURATION_VALUES',
    'LTE_TDD_SPECIAL_SUBFRAME_VALUES',
    'LTE_TDD_RMC_VERSION_VALUES',
    'lte_tdd_frame_structure',
  ]) {
    assert.match(source, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  }
  assert.match(source, /label="UL\/DL 配置"/)
  assert.match(source, /label="特殊子帧配置"/)
  assert.match(source, /label="RMC 版本"/)
})
