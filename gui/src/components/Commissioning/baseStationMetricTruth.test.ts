import assert from 'node:assert/strict'
import test from 'node:test'

import { describeBaseStationMetric } from './baseStationMetricTruth.ts'

const projection = [{
  position: { azimuth_deg: 0, elevation_deg: 0 },
  dl_throughput_mbps: {
    status: 'trusted',
    formal_value: 96.5,
    diagnostic_value: 96.5,
    unit: 'Mbps',
    reason: 'formal_metric_confirmed',
  },
  dl_bler_percent: {
    status: 'diagnostic',
    formal_value: null,
    diagnostic_value: 0.4,
    unit: '%',
    reason: 'current_attempt_not_completed',
  },
}]

test('trusted and diagnostic metrics stay in separate display lanes', () => {
  assert.deepEqual(
    describeBaseStationMetric(projection, 0, 'dl_throughput_mbps'),
    { text: '96.5', color: undefined, note: null },
  )
  assert.deepEqual(
    describeBaseStationMetric(projection, 0, 'dl_bler_percent'),
    { text: '0.4', color: 'yellow', note: '诊断值，非正式实测' },
  )
})

test('missing, malformed, or raw-only payloads render N/A', () => {
  assert.equal(
    describeBaseStationMetric(undefined, 0, 'dl_throughput_mbps').text,
    'N/A',
  )
  assert.equal(
    describeBaseStationMetric([{ ...projection[0], dl_throughput_mbps: {
      status: 'trusted', formal_value: null, diagnostic_value: 999, unit: 'Mbps', reason: 'bad',
    } }], 0, 'dl_throughput_mbps').text,
    'N/A',
  )
})

test('legacy UXM keeps only explicitly verified throughput when projection is absent', () => {
  assert.deepEqual(
    describeBaseStationMetric(
      undefined,
      0,
      'dl_throughput_mbps',
      { verified: true, value: 88.25 },
    ),
    { text: '88.3', color: undefined, note: null },
  )
  assert.equal(
    describeBaseStationMetric(
      [],
      0,
      'dl_throughput_mbps',
      { verified: true, value: 999 },
    ).text,
    'N/A',
  )
  assert.equal(
    describeBaseStationMetric(
      undefined,
      0,
      'dl_throughput_mbps',
      { verified: false, value: 88.25 },
    ).text,
    'N/A',
  )
})
