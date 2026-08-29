import assert from 'node:assert/strict'
import test from 'node:test'

import {
  describeBaseStationMetric,
  describeRegisteredBaseStationMetrics,
} from './baseStationMetricTruth.ts'

const projection = [{
  position: { azimuth_deg: 0, elevation_deg: 0 },
  metrics: {
    dl_throughput_mbps: {
      status: 'trusted', formal_value: 96.5, diagnostic_value: 96.5,
      unit: 'mbps', reason: 'formal_metric_confirmed',
    },
    dl_bler_ratio: {
      status: 'trusted', formal_value: 0.125, diagnostic_value: 0.125,
      unit: 'ratio', reason: 'formal_metric_confirmed',
    },
    rsrp_raw: {
      status: 'diagnostic', formal_value: null, diagnostic_value: 42,
      unit: 'raw', reason: 'metric_semantics_not_authoritative',
    },
  },
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

test('generic metrics preserve ratio and raw semantics without fake units', () => {
  assert.deepEqual(describeRegisteredBaseStationMetrics(projection, 0), [
    {
      key: 'dl_bler_ratio', text: '0.1250', color: undefined,
      note: null, unitLabel: 'ratio',
    },
    {
      key: 'dl_throughput_mbps', text: '96.5', color: undefined,
      note: null, unitLabel: 'Mbps',
    },
    {
      key: 'rsrp_raw', text: '42.0000', color: 'yellow',
      note: '诊断值，非正式实测', unitLabel: 'raw',
    },
  ])
})

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
    describeBaseStationMetric([{ ...projection[0], metrics: {
      ...projection[0].metrics,
      dl_throughput_mbps: {
        status: 'trusted', formal_value: null, diagnostic_value: 999, unit: 'mbps', reason: 'bad',
      },
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
