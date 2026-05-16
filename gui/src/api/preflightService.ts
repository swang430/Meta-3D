/**
 * P1-1 PR B — plan-level pre-flight validation client.
 *
 * Wraps POST /api/v1/test-plans/{id}/preflight (added in PR #22, scoped
 * to lab.instrument_bindings in PR #23). The endpoint deliberately
 * requires `lab_profile_id` as a query param — it does NOT auto-resolve
 * "the single active lab" (that path tripped the commissioning factory
 * during P2-2 smoke). The GUI is responsible for asking the operator
 * which lab to validate against.
 */
import apiClient from './client'

/** One unmet capability requirement on a specific plan step. */
export interface PreflightGap {
  step_id: string
  step_name: string
  step_order: number
  missing_token: string
  /** Human-readable, names both the missing token and the loaded-in-scope
   * categories so the operator can correlate without reading code. When
   * `not_loaded_categories` is non-empty the reason also calls that out. */
  reason: string
}

export interface PreflightResult {
  plan_id: string
  lab_profile_id: string
  /** True iff `gaps` is empty. Unknown tokens warn but don't block. */
  ready: boolean
  gaps: PreflightGap[]
  /** Tokens in some step's `needs` that aren't in KNOWN_CAPABILITIES —
   * almost always typos. Surfaced so the dev can fix without losing the
   * green light on the rest of the plan. */
  unknown_tokens: string[]
  /** Sorted union of tokens exposed by drivers SCOPED to this lab's
   * `instrument_bindings`. Does NOT include capabilities from drivers
   * HAL loaded for other labs. */
  lab_capabilities: string[]
  /** Categories the lab binds but HAL hasn't loaded a driver for.
   * Surfacing this separately lets the GUI direct the operator to
   * "reload HAL / check connection" instead of "buy a license". */
  not_loaded_categories: string[]
}

/**
 * Run pre-flight validation for a plan against a specific lab. The
 * backend returns a typed gap list; callers render it without further
 * derivation (`ready`, `gaps`, `not_loaded_categories`, and
 * `unknown_tokens` are all pre-computed).
 *
 * Throws on 4xx/5xx — the caller's react-query `onError` is expected
 * to surface a notification. The two non-2xx paths the endpoint
 * defines are 404 (plan not found) and 422 (lab_profile_id missing
 * or unknown).
 */
export async function runPreflight(
  planId: string,
  labProfileId: string,
): Promise<PreflightResult> {
  const res = await apiClient.post<PreflightResult>(
    `/test-plans/${planId}/preflight`,
    null,
    { params: { lab_profile_id: labProfileId } },
  )
  return res.data
}
