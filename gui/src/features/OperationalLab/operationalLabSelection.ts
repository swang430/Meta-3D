/**
 * P1-57：全局运行态 LabProfile 选择的白名单决策（纯函数）。
 *
 * 只做决策，不碰 React / localStorage / 网络。规则来自设计稿 §4：
 * - 0 个活动项 → 无选择；
 * - 恰好 1 个 → 自动选它（无 chamber 绑定也选 —— fail-closed 由消费端做，
 *   否则唯一的上下文会变成"永远选不上"）；
 * - 多个 → 只接受「仍在活动集合 + 未停用 + 有 chamber 绑定」的持久化 / 旧 key 值；
 *   两者都不合格就**不选**，绝不猜第一项 / 最新 topology / legacy is_active。
 */

export interface OperationalLabCandidate {
  id: string
  name: string
  is_active: boolean
  chamber_config_id?: string | null
  chamber_name?: string | null
}

export type SelectionSource = 'persisted' | 'legacy' | 'single'

export interface OperationalLabSelectionInput {
  /** fetchLabProfiles(true) 的返回 —— 服务端已过滤 is_active，这里再守一遍。 */
  activeLabs: OperationalLabCandidate[]
  /** 新 key `mimo.operationalLabProfileId` 里的值。 */
  persistedId: string | null
  /** 旧 key 候选（今天只有 `mimo.commissioning.lastLabId`），按序尝试。 */
  legacyIds: Array<string | null>
}

export interface OperationalLabSelectionResult {
  selectedId: string | null
  source: SelectionSource | null
}

/** 恢复 / 迁移的合格判据：仍活动 + 有 chamber 绑定。比自动单选严 —— 恢复错上下文比要求重选贵。 */
function eligibleForRestore(
  labs: OperationalLabCandidate[],
  id: string | null,
): boolean {
  if (!id) return false
  const hit = labs.find((l) => l.id === id)
  return Boolean(hit && hit.is_active && hit.chamber_config_id)
}

export function decideOperationalLabSelection(
  input: OperationalLabSelectionInput,
): OperationalLabSelectionResult {
  const active = input.activeLabs.filter((l) => l.is_active)

  if (active.length === 0) return { selectedId: null, source: null }
  if (active.length === 1) return { selectedId: active[0].id, source: 'single' }

  if (eligibleForRestore(active, input.persistedId)) {
    return { selectedId: input.persistedId, source: 'persisted' }
  }
  for (const legacy of input.legacyIds) {
    if (eligibleForRestore(active, legacy)) {
      return { selectedId: legacy, source: 'legacy' }
    }
  }
  return { selectedId: null, source: null }
}
