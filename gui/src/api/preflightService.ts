/**
 * P1-1 PR B — plan-level pre-flight validation client.
 *
 * Wraps POST /api/v1/test-plans/{id}/preflight (added in PR #22; scoped
 * to lab.instrument_bindings category in commit 4daf3d0; further scoped
 * to per-binding endpoint match in 4e3f835 — both fixing Codex P1s).
 * The endpoint deliberately requires `lab_profile_id` as a query param —
 * it does NOT auto-resolve "the single active lab" (that path tripped
 * the commissioning factory during P2-2 smoke). The GUI is responsible
 * for asking the operator which lab to validate against.
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
   * `not_loaded_categories` or `mismatched_drivers` is non-empty the
   * reason calls those out too. */
  reason: string
}

/** A bound category has a driver loaded for a DIFFERENT physical unit
 * (different endpoint) than this lab declares. The operator hint is
 * "reload HAL with this lab's config" or "fix the lab binding's
 * endpoint" — distinct from `not_loaded_categories` ("driver isn't
 * up at all"). Pairs with the backend's DriverMismatch dataclass. */
export interface PreflightDriverMismatch {
  category: string
  expected_endpoint: string
  loaded_endpoint: string
}

/** P3-3: per-binding STATIC capability declaration read from the
 * driver class's `model_capabilities` ClassVar (P2-3). Independent
 * of HAL load state — answers "what does the model claim it CAN
 * expose?" without needing to connect. PreflightModal renders this
 * alongside the LIVE `lab_capabilities` so the operator can see
 * declared-vs-live mismatches at binding-edit time.
 *
 * `model_name === null` means the binding row had no
 * `instrument_model_id` (operator picked endpoint without picking a
 * model yet). `model_capabilities === []` either because the driver
 * intentionally declared empty (e.g. FS16) OR because the model has
 * no real driver class registered (catalog `status: pending_dev`).
 * The GUI uses `model_name === null` to differentiate "pick a model"
 * from "this model declares nothing".
 */
export interface PreflightBoundModel {
  category: string
  model_name: string | null
  model_capabilities: string[]
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
  /** Sorted union of tokens exposed by drivers scoped per-binding
   * (category + endpoint) to this lab. Does NOT include capabilities
   * from drivers HAL loaded for other labs even if the category
   * matches. */
  lab_capabilities: string[]
  /** Categories the lab binds but HAL hasn't loaded any driver for.
   * Surfacing this separately lets the GUI direct the operator to
   * "reload HAL / check connection" instead of "buy a license". */
  not_loaded_categories: string[]
  /** Categories where HAL has a driver loaded, but for a different
   * physical unit (endpoint mismatch). Different remediation hint
   * from `not_loaded_categories` — usually "reload HAL with this
   * lab's config" or "fix the binding endpoint to match".
   *
   * **Optional** because this field landed on the backend in
   * commit 4e3f835 (Codex P1 iter 2 on PR #22) AFTER PR #22 was
   * already squash-merged. Until that follow-up PR lands in main,
   * the response from a running API won't include this key, so
   * callers must tolerate `undefined`. Once the backend follow-up
   * is in main, treating this as required becomes safe (consider
   * dropping the `?` in a future cleanup PR). */
  mismatched_drivers?: PreflightDriverMismatch[]
  /** P3-3: per-binding STATIC capability declarations (one entry per
   * lab binding). Sorted by category. **Optional** for the same
   * cross-PR-coupling reason as `mismatched_drivers`: backend
   * support lands in the P3-3 PR; consumers must tolerate
   * `undefined` until that PR is in main. */
  bound_models?: PreflightBoundModel[]
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
