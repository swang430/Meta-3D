import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const serviceSource = readFileSync('src/api/service.ts', 'utf8')
const panelSource = readFileSync(
  'src/features/Diagnostics/PositionerControlPanel.tsx',
  'utf8',
)

test('positioner stop may succeed while encoder position remains unknown', () => {
  assert.match(serviceSource, /azimuth:\s*number\s*\|\s*null/)
  assert.match(serviceSource, /elevation:\s*number\s*\|\s*null/)
})

test('unknown encoder coordinates never replace the displayed position', () => {
  assert.match(panelSource, /typeof r\.azimuth === ['"]number['"]/)
  assert.match(panelSource, /typeof r\.elevation === ['"]number['"]/)
  assert.doesNotMatch(panelSource, /if \(r\.ok\) \{\s*setPos\(/)
})
