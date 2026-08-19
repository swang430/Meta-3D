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
  /**
   * 外审 R3：登记一段**在途硬件工作**（一次 runPhase / attach / 自检…）。
   * 跟 registerSwitchGuard 的关键区别：**不随组件卸载消失** —— 请求发出后
   * 操作员切走页面，axios 仍在驱动旧会话，切 LabProfile 必须仍被挡住。
   * 只有返回的 release()（在请求的 finally 里调）才解除；请求必然落定，
   * 所以登记必然被释放。每次调用独立计数 —— 两个并发请求各自持有登记，
   * 先落定的那个不会提前放行（共享布尔就是这么漏的）。
   */
  beginWork: (key: string, reason: string) => () => void
  /** 当前在途工作的理由列表（空 = 无在途）。 */
  activeWork: string[]
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
    // 外审 R1：0 个活动 lab = 无可决策（首启向导流程中）——**不落闩**，
    // 也不动旧 key。等向导建出第一个 lab、invalidate 重拉后本 effect 重跑，
    // 「恰好 1 个 → 自动选择」才能生效；否则操作员建完 lab 仍要手选/刷新。
    if (activeLabs.length === 0) return
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

  // 在途工作登记：ref 是判定真值（同步、闭包安全），state 只为让消费者重渲染。
  const workRef = useRef(new Map<string, string>())
  const workSeq = useRef(0)
  const [activeWork, setActiveWork] = useState<string[]>([])
  const beginWork = useCallback((key: string, reason: string) => {
    const id = `${key}#${++workSeq.current}`
    workRef.current.set(id, reason)
    setActiveWork(Array.from(workRef.current.values()))
    let released = false
    return () => {
      if (released) return
      released = true
      workRef.current.delete(id)
      setActiveWork(Array.from(workRef.current.values()))
    }
  }, [])

  const requestLabChange = useCallback(
    (nextId: string): LabChangeResult => {
      const blockers = [
        ...guards.current.values(),
        ...workRef.current.values(),   // 在途硬件工作 —— 页面卸载也挡
      ]
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
      beginWork,
      activeWork,
    }),
    [activeLabs, query.isLoading, query.isError, query.error, selectedLabProfile, requestLabChange, registerSwitchGuard, beginWork, activeWork],
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
