import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CMW500_ROUTE_EXAMPLES,
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

test('blank, partial or reused TX paths fail loud', () => {
  assert.throws(
    () => buildCmw500AdapterProfile(emptyCmw500Route()),
    /必须完整填写七个字段/,
  )
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

test('numeric hardware indices are rejected in favor of manual route tokens', () => {
  assert.throws(
    () => buildCmw500AdapterProfile({
      pcc_bb_board: '0',
      rx_connector: '3',
      rx_converter: '3',
      tx1_connector: '1',
      tx1_converter: '1',
      tx2_connector: '2',
      tx2_converter: '2',
    }),
    /SUA1.*RF3C.*RX3.*RF1C.*TX1.*RF2C.*TX2/,
  )
  assert.deepEqual(CMW500_ROUTE_EXAMPLES, {
    pcc_bb_board: 'SUA1',
    rx_connector: 'RF3C',
    rx_converter: 'RX3',
    tx1_connector: 'RF1C',
    tx1_converter: 'TX1',
    tx2_connector: 'RF2C',
    tx2_converter: 'TX2',
  })
  assert.deepEqual(
    readCmw500Route({
      schema_version: 1,
      adapter: 'cmw500',
      lte_2x2_internal_route: {
        pcc_bb_board: '0',
        rx_connector: '3',
        rx_converter: '3',
        tx1_connector: '1',
        tx1_converter: '1',
        tx2_connector: '2',
        tx2_converter: '2',
      },
    }),
    emptyCmw500Route(),
  )
})

test('legacy or malformed free JSON never becomes an editable trusted route', () => {
  assert.deepEqual(readCmw500Route({ adapter: 'cmw500' }), emptyCmw500Route())
  assert.deepEqual(readCmw500Route({ ...complete }), emptyCmw500Route())
})
