import type { HALCategoryActivationResult } from '../../types/api.ts'

export type CategoryActivationCommit<T> = {
  committed: T
  activation?: HALCategoryActivationResult
  activationError?: unknown
}

/**
 * Persist first, then activate the same category from server-committed truth.
 * Activation is deliberately a second transaction: a refusal must not make a
 * successful configuration save look rolled back.
 */
export async function commitThenActivateCategory<T>(
  categoryKey: string,
  commit: () => Promise<T>,
  activate: (categoryKey: string) => Promise<HALCategoryActivationResult>,
): Promise<CategoryActivationCommit<T>> {
  const committed = await commit()
  try {
    return {
      committed,
      activation: await activate(categoryKey),
    }
  } catch (activationError) {
    return { committed, activationError }
  }
}
