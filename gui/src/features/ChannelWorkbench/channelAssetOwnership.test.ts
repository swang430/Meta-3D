import assert from 'node:assert/strict'
import test from 'node:test'
import { savedChannelAssetOwner, ownershipConfirmationPayload } from './channelAssetOwnership.ts'

const category = {
  key: 'channelEmulator', selectedModelId: 'f64',
  connection: { id: 'ce', endpoint: 'test:3334' },
  models: [{ id: 'f64', vendor: 'Keysight', model: 'F64' }],
}

test('归属只使用已保存型号，缺失型号不能借草稿补真', () => {
  const owner = savedChannelAssetOwner(category)
  assert.equal(owner?.instrument_model_id, 'f64')
  assert.equal(owner?.instrument_connection_id, 'ce')
  assert.equal(savedChannelAssetOwner({ ...category, selectedModelId: null }), null)
})

test('批量确认单一请求包含全部显式选中资产和目标型号', () => {
  const owner = savedChannelAssetOwner(category)!
  assert.deepEqual(ownershipConfirmationPayload(['one', 'two'], owner), {
    asset_ids: ['one', 'two'], instrument_connection_id: 'ce', instrument_model_id: 'f64',
  })
  assert.throws(() => ownershipConfirmationPayload([], owner))
})
