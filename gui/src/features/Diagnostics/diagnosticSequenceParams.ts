import type { SequenceParamSpec } from '../../api/diagnosticService'

export type ParamValue = number | string | boolean

export function initialSequenceParamValues(
  specs: SequenceParamSpec[],
): Record<string, ParamValue> {
  const values: Record<string, ParamValue> = {}
  for (const spec of specs) {
    if (spec.default !== undefined && spec.default !== null) {
      values[spec.name] = spec.default
    } else if (spec.type === 'number') {
      values[spec.name] = 0
    } else if (spec.type === 'boolean') {
      values[spec.name] = false
    } else {
      values[spec.name] = ''
    }
  }
  return values
}

export function sequenceParamSelectData(
  spec: SequenceParamSpec,
): SequenceParamSpec['choices'] | null {
  return spec.choices && spec.choices.length > 0 ? spec.choices : null
}
