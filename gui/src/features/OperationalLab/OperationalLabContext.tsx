/**
 * P1-57：浏览器级「当前 LabProfile / 暗室」唯一上下文。
 *
 * 真值链：显式选择的 LabProfile → LabProfile.chamber_config_id → 暗室。
 * 页面不再各自选暗室；需要另一个暗室时先切到绑定它的 LabProfile。
 *
 * 这是**当前浏览器工作区**的上下文，不是数据库全局单例 —— 每个请求仍显式携带
 * lab_profile_id，服务端用 resolve_current_chamber() 解析，不依赖 is_active。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchLabProfiles, type LabProfileSummary } from '../../api/labProfileService'
import { decideOperationalLabSelection } from './operationalLabSelection'

export const OPERATIONAL_LAB_LS_KEY = 'mimo.operationalLabProfileId'
/** 迁移全集（2026-08-19 rg 实证）：只有 Commissioning 落过盘，ProbeManager 是纯内存。 */
const LEGACY_LAB_LS_KEYS = ['mimo.commissioning.lastLabId']

export interface LabChangeResult {
  ok: boolean
  /** 阻断原因（人话），空数组 = 切换成功。 */
  blockers: string[]
}

export interface OperationalLabContextValue {
  activeLabs: LabProfileSummary[]
  loading: boolean
  /** 列表加载失败：保留已解析上下文但禁止切换（设计 §8），不当成 0 个。 */
  error: string | null
  selectedLabProfileId: string | null
  selectedLabProfile: LabProfileSummary | null
  /** 从选中 LabProfile 派生；无绑定时为 null —— 暗室消费者必须 fail-closed。 */
  chamberId: string | null
  chamberName: string | null
  requestLabChange: (nextId: string) => LabChangeResult
  /** 危险页面只上报阻断理由（reason=null 即解除），不自动保存/丢弃。 */
  registerSwitchGuard: (key: string, reason: string | null) => void
}

const Ctx = createContext<OperationalLabContextValue | null>(null)

export function OperationalLabProvider({ children }: { children: ReactNode }) {
  const [selectedLabProfileId, setSelectedLabProfileId] = useState<string | null>(null)
  const initialized = useRef(false)
  const guards = useRef(new Map<string, string>())

  const query = useQuery({
    queryKey: ['lab-profiles', 'operational-context'],
    queryFn: () => fetchLabProfiles(true),
    staleTime: 60_000,
  })

  const activeLabs = useMemo(() => query.data ?? [], [query.data])

  // 一次性初始化：白名单恢复 / 旧 key 迁移。决策在纯函数里，这儿只做 IO。
  useEffect(() => {
    if (initialized.current || !query.isSuccess) return
    initialized.current = true
    const decision = decideOperationalLabSelection({
      activeLabs,
      persistedId: localStorage.getItem(OPERATIONAL_LAB_LS_KEY),
      legacyIds: LEGACY_LAB_LS_KEYS.map((k) => localStorage.getItem(k)),
    })
    if (decision.selectedId) {
      setSelectedLabProfileId(decision.selectedId)
      localStorage.setItem(OPERATIONAL_LAB_LS_KEY, decision.selectedId)
    }
    // 迁移尝试之后（成功或失败）删除旧 key —— 不再双读
    for (const k of LEGACY_LAB_LS_KEYS) localStorage.removeItem(k)
  }, [query.isSuccess, activeLabs])

  const registerSwitchGuard = useCallback((key: string, reason: string | null) => {
    if (reason === null) guards.current.delete(key)
    else guards.current.set(key, reason)
  }, [])

  const requestLabChange = useCallback(
    (nextId: string): LabChangeResult => {
      const blockers = Array.from(guards.current.values())
      if (blockers.length > 0) return { ok: false, blockers }
      const hit = activeLabs.find((l) => l.id === nextId && l.is_active)
      if (!hit) return { ok: false, blockers: ['目标 LabProfile 不在活动列表里'] }
      setSelectedLabProfileId(nextId)
      localStorage.setItem(OPERATIONAL_LAB_LS_KEY, nextId)
      return { ok: true, blockers: [] }
    },
    [activeLabs],
  )

  const selectedLabProfile = useMemo(
    () => activeLabs.find((l) => l.id === selectedLabProfileId) ?? null,
    [activeLabs, selectedLabProfileId],
  )

  const value = useMemo<OperationalLabContextValue>(
    () => ({
      activeLabs,
      loading: query.isLoading,
      error: query.isError ? String(query.error) : null,
      selectedLabProfileId: selectedLabProfile ? selectedLabProfile.id : null,
      selectedLabProfile,
      chamberId: selectedLabProfile?.chamber_config_id ?? null,
      chamberName: selectedLabProfile?.chamber_name ?? null,
      requestLabChange,
      registerSwitchGuard,
    }),
    [activeLabs, query.isLoading, query.isError, query.error, selectedLabProfile, requestLabChange, registerSwitchGuard],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useOperationalLab(): OperationalLabContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useOperationalLab 必须在 OperationalLabProvider 内使用')
  return v
}

/** 声明式 guard：reason 非 null 时阻断 LabProfile 切换；卸载自动解除。 */
export function useOperationalLabSwitchGuard(key: string, reason: string | null) {
  const { registerSwitchGuard } = useOperationalLab()
  useEffect(() => {
    registerSwitchGuard(key, reason)
    return () => registerSwitchGuard(key, null)
  }, [key, reason, registerSwitchGuard])
}
