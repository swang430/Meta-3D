import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const sourceText = readFileSync(
  new URL('../src/types/api.ts', import.meta.url),
  'utf8',
)
function typeBlock(name: string): string {
  const start = sourceText.indexOf(`export type ${name} =`)
  assert.ok(start >= 0, `${name} must exist`)
  const next = sourceText.indexOf('\nexport type ', start + 1)
  return sourceText.slice(start, next === -1 ? sourceText.length : next)
}

test('live response envelopes and nested view models expose their required fields', () => {
  assert.match(typeBlock('ProbesResponse'), /\n\s*total:\s*number/)
  assert.match(typeBlock('InstrumentCategory'), /\n\s*usagePhase:\s*string\[\]/)
  assert.match(typeBlock('InstrumentCategory'), /\n\s*driverMode:/)
  assert.match(
    typeBlock('ChamberConfiguration'),
    /\n\s*probe_distribution:\s*'ring'\s*\|\s*'multi-ring'\s*\|\s*'custom'/,
  )
})

test('chamber create payload only requires the two live request fields', () => {
  const aliasText = typeBlock('CreateChamberPayload')
  assert.match(aliasText, /Pick<ChamberWritableFields,\s*'name'\s*\|\s*'chamber_radius_m'>/)
  assert.match(
    aliasText,
    /Partial<\s*Omit<ChamberWritableFields,\s*'name'\s*\|\s*'chamber_radius_m'>\s*>/,
  )
  assert.doesNotMatch(aliasText, /Omit<\s*ChamberConfiguration/)
})
