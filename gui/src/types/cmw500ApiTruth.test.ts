import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const generated = readFileSync(
  new URL('./api.generated.ts', import.meta.url),
  'utf8',
)
const handwritten = readFileSync(
  new URL('./api.ts', import.meta.url),
  'utf8',
)
const formalPathStart = generated.indexOf(
  '"/api/v1/instruments/connections/{connection_id}/formal-capabilities/cmw500-lte-2x2"',
)
const formalPathEnd = generated.indexOf('\n    "/api/v1/', formalPathStart + 1)
const formalPath = generated.slice(formalPathStart, formalPathEnd)

test('generated readiness exposes the complete CMW500 warning snapshot', () => {
  assert.match(
    generated,
    /Cmw500Lte2x2Readiness:[\s\S]*status: "ready" \| "warning" \| "diagnostic" \| "not_applicable";[\s\S]*adapter_registered: boolean;[\s\S]*connection_id: string \| null;[\s\S]*firmware_version: string \| null;[\s\S]*options: string\[\];[\s\S]*formal_enabled: boolean;[\s\S]*formal_updated_at: string \| null;[\s\S]*fdd_ready: boolean;[\s\S]*tdd_ready: boolean;/,
  )
  assert.match(
    generated,
    /HALReadinessResponse:[\s\S]*cmw500_lte_2x2: components\["schemas"\]\["Cmw500Lte2x2Readiness"\] \| null;/,
  )
  assert.match(
    handwritten,
    /HALReadinessResponse = \{[\s\S]*cmw500_lte_2x2: Cmw500Lte2x2Readiness \| null/,
  )
  assert.doesNotMatch(handwritten, /cmw500_lte_2x2\?:/)
})

test('generated formal approval remains a dedicated PUT contract', () => {
  assert.notEqual(formalPathStart, -1)
  assert.match(
    formalPath,
    /put: \{[\s\S]*Cmw500FormalCapabilityUpdate[\s\S]*Cmw500FormalCapabilityResponse/,
  )
})
