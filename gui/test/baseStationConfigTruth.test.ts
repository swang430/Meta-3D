import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  resolveBaseStationConfigMode,
  updateBaseStationConfigMode,
} from '../src/components/TestCaseConfig/baseStationConfigTruth.ts'

test('new field is authoritative and legacy-only payload remains readable', () => {
  assert.deepEqual(
    resolveBaseStationConfigMode({ base_station_config_mode: 'inherit' }),
    { mode: 'inherit', conflict: false },
  )
  assert.deepEqual(
    resolveBaseStationConfigMode({ uxm_config_mode: 'inherit' }),
    { mode: 'inherit', conflict: false },
  )
})

test('conflicting dual-write is surfaced instead of silently choosing one side', () => {
  assert.deepEqual(
    resolveBaseStationConfigMode({
      base_station_config_mode: 'dispatch',
      uxm_config_mode: 'inherit',
    }),
    { mode: 'dispatch', conflict: true },
  )
})

test('form writes only the generic field and removes a legacy writer key', () => {
  assert.deepEqual(
    updateBaseStationConfigMode(
      { name: 'legacy', uxm_config_mode: 'inherit' },
      'dispatch',
    ),
    { name: 'legacy', base_station_config_mode: 'dispatch' },
  )
})

test('commissioning request emits only the generic config-mode key', () => {
  const source = readFileSync(
    new URL('../src/components/Commissioning/api.ts', import.meta.url),
    'utf8',
  )
  assert.match(source, /body\.base_station_config_mode\s*=\s*baseStationConfigMode/)
  assert.doesNotMatch(source, /body\.uxm_config_mode\s*=/)
})
