import assert from 'node:assert/strict'
import test from 'node:test'
import { projectMacStatisticalWindow } from './macStatisticalWindow.ts'

test('GUI uses the server supplied range rather than CMW constants', () => {
  const view = projectMacStatisticalWindow({ mac_profiles: [{
    kind: 'lte_rmc', profile_version: 1, rat: 'lte',
    statistical_window: { unit: 'subframes', minimum: 123, maximum: 456, source_reference: 'Manual §1' },
  }] }, 'lte_rmc')
  assert.equal(view.minimum, 123)
  assert.equal(view.maximum, 456)
  assert.equal(view.status, 'known')
  assert.match(view.description, /123.*456/)
})

test('unknown NR range does not inherit LTE range', () => {
  const view = projectMacStatisticalWindow({ mac_profiles: [{
    kind: 'lte_rmc', profile_version: 1, rat: 'lte',
    statistical_window: { unit: 'subframes', minimum: 100, maximum: 400000, source_reference: 'Manual' },
  }] }, 'nr_throughput')
  assert.equal(view.status, 'unknown')
  assert.equal(view.minimum, 1)
  assert.equal(view.maximum, undefined)
  assert.match(view.description, /unknown/)
})

test('missing or malformed declaration remains unknown', () => {
  for (const manifest of [null, {}, {mac_profiles: [{kind: 'lte_rmc', profile_version: 1, rat: 'lte', statistical_window: null}]}]) {
    assert.equal(projectMacStatisticalWindow(manifest, 'lte_rmc').status, 'unknown')
  }
})
