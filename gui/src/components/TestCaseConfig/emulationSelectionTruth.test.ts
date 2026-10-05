import assert from 'node:assert/strict'
import test from 'node:test'
import { selectEmulationFile, selectedEmulationFilename } from './emulationSelectionTruth.ts'

const items = [
  { filename: 'scanned.smu', channel_asset_id: 'modern', scd_id: 'old-twin' },
  { filename: 'legacy.smu', scd_id: 'legacy' },
  { filename: 'manual.smu' },
]

test('扫描投影选择保存现代资产身份，不降级为裸文件或旧 twin', () => {
  const next = selectEmulationFile({ scd_id: 'old', emulation_file: 'old.smu' }, items, 'scanned.smu')
  assert.equal(next.channel_asset_id, 'modern')
  assert.equal(next.scd_id, undefined)
  assert.equal(next.emulation_file, undefined)
  assert.equal(selectedEmulationFilename(next, items), 'scanned.smu')
  assert.equal(selectedEmulationFilename(next, []), null)
})

test('legacy、手工与清空选择互斥，不保留上一份资产身份', () => {
  const prior = { channel_asset_id: 'modern', scd_id: 'old', emulation_file: 'old.smu' }
  assert.deepEqual(selectEmulationFile(prior, items, 'legacy.smu'), {
    channel_asset_id: undefined, scd_id: 'legacy', emulation_file: undefined,
  })
  assert.deepEqual(selectEmulationFile(prior, items, 'manual.smu'), {
    channel_asset_id: undefined, scd_id: undefined, emulation_file: 'manual.smu',
  })
  assert.deepEqual(selectEmulationFile(prior, items, null), {
    channel_asset_id: undefined, scd_id: undefined, emulation_file: undefined,
  })
})
