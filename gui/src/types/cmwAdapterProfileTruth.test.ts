import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCmw500AdapterProfile,
  emptyCmw500Route,
  readCmw500Route,
} from './cmwAdapterProfile.ts'

const complete = {
  pcc_bb_board: 'BB1',
  rx_connector: 'RF1C',
  rx_converter: 'RX1',
  tx1_connector: 'RF1C',
  tx1_converter: 'TX1',
  tx2_connector: 'RF2C',
  tx2_converter: 'TX2',
}

test('seven explicit fields build the only typed CMW500 route payload', () => {
  assert.deepEqual(buildCmw500AdapterProfile(complete), {
    schema_version: 1,
    adapter: 'cmw500',
    lte_2x2_internal_route: complete,
  })
  assert.deepEqual(
    readCmw500Route({
      schema_version: 1,
      adapter: 'cmw500',
      lte_2x2_internal_route: complete,
    }),
    complete,
  )
})

test('blank profile clears, partial or reused TX paths fail loud', () => {
  assert.equal(buildCmw500AdapterProfile(emptyCmw500Route()), null)
  assert.throws(
    () => buildCmw500AdapterProfile({ ...complete, tx2_converter: '' }),
    /七个字段/,
  )
  assert.throws(
    () => buildCmw500AdapterProfile({ ...complete, tx2_connector: 'RF1C' }),
    /TX1\/TX2 connector/,
  )
  assert.throws(
    () => buildCmw500AdapterProfile({ ...complete, tx2_converter: 'TX1' }),
    /TX1\/TX2 converter/,
  )
})

test('legacy or malformed free JSON never becomes an editable trusted route', () => {
  assert.deepEqual(readCmw500Route({ adapter: 'cmw500' }), emptyCmw500Route())
  assert.deepEqual(readCmw500Route({ ...complete }), emptyCmw500Route())
})
