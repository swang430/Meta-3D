import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


function section(source: string, start: RegExp, end: RegExp): string {
  const startMatch = start.exec(source)
  assert.ok(startMatch, `missing section start: ${start}`)
  const tail = source.slice(startMatch.index)
  const endMatch = end.exec(tail.slice(startMatch[0].length))
  assert.ok(endMatch, `missing section end: ${end}`)
  return tail.slice(0, startMatch[0].length + endMatch.index)
}


test('checked OpenAPI, generated TypeScript and handwritten types preserve job provenance', () => {
  const yaml = readFileSync(new URL('../../api/openapi.yaml', import.meta.url), 'utf8')
  const generated = readFileSync(
    new URL('../src/types/api.generated.ts', import.meta.url),
    'utf8',
  )
  const handwritten = readFileSync(
    new URL('../src/types/probeCalibration.ts', import.meta.url),
    'utf8',
  )
  const generatedParameterReference = readFileSync(
    new URL(
      '../../docs/features/virtual-road-test/parameter-reference-generated.md',
      import.meta.url,
    ),
    'utf8',
  )

  const yamlJob = section(yaml, /^    CalibrationJobResponse:/m, /^    CreateSessionRequest:/m)
  assert.match(yamlJob, /use_mock:/)
  assert.match(yamlJob, /warnings:/)

  const generatedJob = section(
    generated,
    /^        CalibrationJobResponse: \{/m,
    /^        CreateSessionRequest: \{/m,
  )
  assert.match(generatedJob, /use_mock\?: boolean \| null;/)
  assert.match(generatedJob, /warnings\?: string\[\];/)

  const handwrittenJob = section(
    handwritten,
    /^export interface CalibrationJobResponse \{/m,
    /^export interface CalibrationProgress \{/m,
  )
  assert.match(handwrittenJob, /use_mock\?: boolean \| null/)
  assert.match(handwrittenJob, /warnings\?: string\[\]/)
  assert.doesNotMatch(generatedParameterReference, /MultiFrequencyCalibrationRequest/)
  assert.doesNotMatch(generatedParameterReference, /FrequencyCalibrationResult/)
})


test('multi-frequency request mirrors preserve the required LabProfile topology scope', () => {
  const yaml = readFileSync(new URL('../../api/openapi.yaml', import.meta.url), 'utf8')
  const generated = readFileSync(
    new URL('../src/types/api.generated.ts', import.meta.url),
    'utf8',
  )

  const yamlRequest = section(
    yaml,
    /^    StartMultiFrequencyPathLossRequest:/m,
    /^    CalibrationJobResponse:/m,
  )
  assert.match(yamlRequest, /required: \[lab_profile_id, chamber_id,/)
  assert.match(yamlRequest, /lab_profile_id:/)
  assert.match(yamlRequest, /operating_mode:/)

  const generatedRequest = section(
    generated,
    /^        StartMultiFrequencyPathLossRequest: \{/m,
    /^        CalibrationJobResponse: \{/m,
  )
  assert.match(generatedRequest, /lab_profile_id: string;/)
  assert.match(generatedRequest, /operating_mode: string;/)
})
