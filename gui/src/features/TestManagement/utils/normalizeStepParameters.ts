/**
 * Normalize TestStep.parameters into the StepParameter shape the editor expects.
 *
 * Backstory: After Phase 1 the MIMO_OTA seed upgrade, TestCase.configuration
 * is a 27-field flat JSON (cdl_model_name, frequency_hz, azimuths_deg,
 * pass_criteria, …) — values are raw str/float/int/bool/list/dict. The
 * `add_test_step` endpoint copies this dict directly into TestStep.parameters,
 * but StepEditor's `renderParameterInput` reads `param.type`, `param.label`,
 * `param.value` etc., assuming each entry is a wrapped `StepParameter`. With
 * raw values those reads return undefined and Mantine's render pipeline
 * crashes.
 *
 * Fix: when fetched parameters look raw (any value is not an object with both
 * `.type` and `.value`), wrap each entry into a synthetic StepParameter whose
 * `type` is inferred from the JS typeof. Once the user saves, the wrapped
 * shape is persisted and subsequent fetches won't need normalization.
 */
import type { ParametersMap, StepParameter, ParameterType } from '../types'

function isStepParameter(value: unknown): value is StepParameter {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    'type' in value &&
    'value' in value
  )
}

function inferParameterType(value: unknown): ParameterType {
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return 'number'
  if (Array.isArray(value)) return 'json'
  if (value !== null && typeof value === 'object') return 'json'
  // string + null + undefined fall through to text
  return 'text'
}

function wrapAsStepParameter(key: string, value: unknown): StepParameter {
  return {
    type: inferParameterType(value),
    label: key,
    value: value as StepParameter['value'],
    required: false,
  }
}

/**
 * Returns a ParametersMap where every entry is a valid StepParameter.
 *
 * - Already-wrapped entries pass through unchanged.
 * - Raw scalar/array/object values are auto-wrapped with a type inferred from
 *   their JS runtime type and `label = key`.
 * - Falsy / non-object inputs return an empty map rather than throwing.
 */
export function normalizeStepParameters(
  raw: Record<string, unknown> | null | undefined,
): ParametersMap {
  if (!raw || typeof raw !== 'object') return {}

  const out: ParametersMap = {}
  for (const [key, value] of Object.entries(raw)) {
    out[key] = isStepParameter(value) ? value : wrapAsStepParameter(key, value)
  }
  return out
}
