import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { dashboardMainZones } from './dashboardCockpitLayout.ts'

test('cockpit places live logs beside recent executions and excludes live metrics', () => {
  const cockpitSource = readFileSync(
    new URL('./DashboardCockpit.tsx', import.meta.url),
    'utf8',
  )

  assert.deepEqual(dashboardMainZones(), [
    'recentExecutions',
    'liveLogs',
  ])
  assert.match(cockpitSource, /dashboardMainZones\(\)\.map/)
  assert.doesNotMatch(cockpitSource, /ZoneLiveMetrics/)
})
