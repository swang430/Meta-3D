import assert from 'node:assert/strict'
import test from 'node:test'

import {
  initialSequenceParamValues,
  sequenceParamSelectData,
} from '../src/features/Diagnostics/diagnosticSequenceParams.ts'


test('choice parameter keeps an explicit blank default instead of inventing a choice', () => {
  const values = initialSequenceParamValues([
    {
      name: 'operator_local_state',
      label: '交还状态',
      type: 'string',
      default: '',
      choices: [
        { value: 'local', label: '已回 Local' },
        { value: 'remote', label: '仍为 Remote' },
      ],
    },
  ])

  assert.deepEqual(values, { operator_local_state: '' })
})

test('choice parameter exposes server labels and values verbatim', () => {
  const data = sequenceParamSelectData({
    name: 'sample',
    label: '样本',
    type: 'string',
    default: 'tm1_one',
    choices: [
      { value: 'tm1_one', label: 'TM1 + 1 TX（SIMO 1x2）' },
      { value: 'tm3_two', label: 'TM3 + 2 TX（MIMO 2x2）' },
    ],
  })

  assert.deepEqual(data, [
    { value: 'tm1_one', label: 'TM1 + 1 TX（SIMO 1x2）' },
    { value: 'tm3_two', label: 'TM3 + 2 TX（MIMO 2x2）' },
  ])
})

test('legacy parameter initialization remains type-compatible', () => {
  const values = initialSequenceParamValues([
    { name: 'count', label: '次数', type: 'number' },
    { name: 'enabled', label: '启用', type: 'boolean' },
    { name: 'note', label: '备注', type: 'string' },
  ])

  assert.deepEqual(values, { count: 0, enabled: false, note: '' })
  assert.equal(sequenceParamSelectData({
    name: 'note', label: '备注', type: 'string',
  }), null)
})
