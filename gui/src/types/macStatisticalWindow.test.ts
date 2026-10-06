import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { projectMacStatisticalWindow } from './macStatisticalWindow.ts'

test('successful binding sync invalidates the server statistical window declaration', () => {
  const app = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
  const sync = app.slice(app.indexOf('const syncLabBindingMutation'), app.indexOf('const handleModelChange'))
  assert.match(sync, /invalidateQueries\(\{ queryKey: \['base-station-window-binding'\]/)
})

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
