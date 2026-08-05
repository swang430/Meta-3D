import MockAdapter from 'axios-mock-adapter'
import { Server as MockSocketServer, type Client as MockSocketClient } from 'mock-socket'
import client from './client'
import { mockDatabase } from './mockDatabase'
import type {
  CreatePlanPayload,
  UpdatePlanPayload,
  CreateTestCaseFromPlanPayload,
  CreateTestCasePayload,
} from '../types/api'

let mock: MockAdapter | null = null
let monitoringSocket: MockSocketServer | null = null

const DELAY_MS = 300
// Dynamically construct WebSocket URL based on current host
const MONITORING_WS_URL = typeof window !== 'undefined'
  ? `${window.location.origin.replace(/^http/, 'ws')}/api/v1/ws/monitoring`
  : 'ws://localhost:8000/api/v1/ws/monitoring'

export function setupMockServer() {
  if (mock) return

  mock = new MockAdapter(client, { delayResponse: DELAY_MS })

  mock.onGet('/tests/cases').reply(200, mockDatabase.getTestCases())
  // ⚠️ 上面这条是**用例**端点 (保留集)。S4c 清计划处理器时曾被一个过宽的判据
  // ("往后 8 行出现 savePlanAsTestCase") 连坐误删 —— 而编译门抓不到, mock
  // 处理器是运行时注册的。POST /tests/cases 走的是 savePlanAsTestCase
  // (从计划存为用例), 随计划链删除是对的。

  mock.onGet('/dashboard').reply(200, mockDatabase.getDashboard())

  mock.onGet('/probes').reply(200, mockDatabase.getProbes())

  mock.onGet('/instruments/catalog').reply(200, mockDatabase.getInstrumentCatalog())

  mock.onPost('/probes').reply((config) => {
    try {
      const payload = JSON.parse(config.data)
      const created = mockDatabase.createProbe(payload)
      return [201, { probe: created }]
    } catch {
      return [400, { message: '无效的探头数据' }]
    }
  })

  mock.onPut(/\/probes\/[^/]+$/).reply((config) => {
    try {
      const id = config.url?.split('/').pop() ?? ''
      const payload = JSON.parse(config.data)
      const updated = mockDatabase.updateProbe(id, payload)
      if (!updated) return [404, { message: '未找到探头' }]
      return [200, { probe: updated }]
    } catch {
      return [400, { message: '更新探头失败' }]
    }
  })

  mock.onPut('/probes/bulk').reply((config) => {
    try {
      const payload = JSON.parse(config.data)
      if (!Array.isArray(payload?.probes)) {
        return [400, { message: '缺少有效的探头列表' }]
      }
      const result = mockDatabase.setProbes(payload.probes)
      return [200, result]
    } catch {
      return [400, { message: '导入探头配置失败' }]
    }
  })

  mock.onDelete(/\/probes\/[^/]+$/).reply((config) => {
    const id = config.url?.split('/').pop() ?? ''
    const success = mockDatabase.deleteProbe(id)
    return success ? [200, { success: true }] : [404, { message: '未找到探头' }]
  })

  mock.onGet('/sequence/library').reply(200, mockDatabase.getSequenceLibrary())

  // ===== Test Management API - Sequence Library =====
  // Note: API client uses baseURL '/api/v1', so we need to match the full path
  mock.onGet('/api/v1/test-sequences').reply((config) => {
    const library = mockDatabase.getSequenceLibrary().library
    // Transform to match SequenceLibraryItem type
    // Categorize by ID prefix: vrt-* = 虚拟路测, lib-* = 通用测试
    let items = library.map((item, index) => ({
      id: item.id,
      name: item.title,
      description: item.description || null,
      category: item.id.startsWith('vrt-') ? '虚拟路测' : '通用测试',
      steps: [],
      parameters: null,
      default_values: null,
      validation_rules: null,
      is_public: true,
      usage_count: 10 + index * 5,
      created_by: 'system',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      tags: item.meta?.split('·').map(t => t.trim()) || [],
    }))

    // Apply filters from query params
    const params = config.params || {}
    if (params.category) {
      items = items.filter(item => item.category === params.category)
    }
    if (params.search) {
      const search = params.search.toLowerCase()
      items = items.filter(item =>
        item.name.toLowerCase().includes(search) ||
        (item.description && item.description.toLowerCase().includes(search))
      )
    }

    console.log('[MockServer] /test-sequences returning', items.length, 'items (total in db:', library.length, ')')
    return [200, { items }]
  })

  mock.onGet('/api/v1/test-sequences/categories').reply(() => {
    // Extract categories from vrt-* steps and lib-* steps
    const categories = ['通用测试', '虚拟路测']
    return [200, { categories }]
  })

  mock.onGet('/api/v1/test-sequences/popular').reply(() => {
    const library = mockDatabase.getSequenceLibrary().library
    const items = library.slice(0, 10).map((item, index) => ({
      id: item.id,
      name: item.title,
      description: item.description || null,
      category: item.id.startsWith('vrt-') ? '虚拟路测' : '通用测试',
      steps: [],
      parameters: null,
      default_values: null,
      validation_rules: null,
      is_public: true,
      usage_count: 50 - index * 3,
      created_by: 'system',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      tags: item.meta?.split('·').map(t => t.trim()) || [],
    }))
    return [200, { items }]
  })

  mock.onGet(/\/api\/v1\/test-sequences\/[^/]+$/).reply((config) => {
    const itemId = config.url?.split('/').pop() ?? ''
    const library = mockDatabase.getSequenceLibrary().library
    const item = library.find(s => s.id === itemId)
    if (!item) return [404, { message: '未找到序列' }]
    return [200, {
      id: item.id,
      name: item.title,
      description: item.description || null,
      category: item.id.startsWith('vrt-') ? '虚拟路测' : '通用测试',
      steps: [],
      parameters: null,
      default_values: null,
      validation_rules: null,
      is_public: true,
      usage_count: 20,
      created_by: 'system',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      tags: item.meta?.split('·').map(t => t.trim()) || [],
    }]
  })

  mock.onGet('/tests/templates').reply(200, mockDatabase.getTestTemplates())

  mock.onPost('/tests/cases/new').reply((config) => {
    try {
      const payload = JSON.parse(config.data) as CreateTestCasePayload
      const created = mockDatabase.createTestCase(payload)
      if (!created) return [400, { message: '创建测试例失败' }]
      return [201, created]
    } catch {
      return [400, { message: '创建测试例失败' }]
    }
  })

  mock.onDelete(/\/tests\/cases\/[^/]+$/).reply((config) => {
    const caseId = config.url?.split('/').pop() ?? ''
    const result = mockDatabase.deleteTestCase(caseId)
    if (!result.success) return [404, { message: '未找到测试例' }]
    return [200, result]
  })


  mock.onGet(/\/tests\/cases\/[^/]+$/).reply((config) => {
    const caseId = config.url?.split('/').pop() ?? ''
    const result = mockDatabase.getTestCaseDetail(caseId)
    if (!result) return [404, { message: '未找到测试例' }]
    return [200, result]
  })

  mock.onGet('/tests/recent').reply(200, mockDatabase.getRecentTests())

  mock.onGet('/tests/demo-run').reply(200, mockDatabase.getDemoRunPlan())

  mock.onGet('/reports/templates').reply(200, mockDatabase.getReportTemplates())

  mock.onGet('/monitoring/feeds').reply(200, mockDatabase.getMonitoringFeeds())

  // ===== P2-8 Operational Cockpit =====
  mock.onGet('/instruments/hal/readiness').reply(200, mockDatabase.getReadiness())

  mock.onGet('/test-executions').reply((config) => {
    const limit = config.params?.limit ? Number(config.params.limit) : undefined
    const status = config.params?.status ? String(config.params.status) : undefined
    // executed_by 是可重复参数 (数组); 单值也归一成数组
    const rawChains = config.params?.executed_by
    const executedBy = rawChains === undefined || rawChains === null
      ? undefined
      : (Array.isArray(rawChains) ? rawChains.map(String) : [String(rawChains)])
    return [200, mockDatabase.getTestExecutions(limit, status, executedBy)]
  })

  mock.onGet('/system-logs/tail').reply((config) => {
    const params = config.params || {}
    return [200, mockDatabase.getSystemLogsTail(
      params.filename, params.level, params.keyword, params.session_id, params.execution_id)]
  })

  // /dashboard/alerts/summary registered before /dashboard/alerts so the
  // exact-string summary route isn't shadowed by the list route.
  mock.onGet('/dashboard/alerts/summary').reply(200, mockDatabase.getDashboardAlertSummary())
  mock.onGet('/dashboard/alerts').reply(200, mockDatabase.getDashboardAlerts())

  mock.onPut(/\/instruments\/[^/]+$/).reply((config) => {
    try {
      const categoryKey = config.url?.split('/').pop() ?? ''
      const payload = config.data ? JSON.parse(config.data) : {}
      const updated = mockDatabase.updateInstrumentCategory(categoryKey, payload)
      if (!updated) return [404, { message: '未找到仪器类别' }]
      return [200, { category: updated }]
    } catch {
      return [400, { message: '更新仪器配置失败' }]
    }
  })

  if (!monitoringSocket) {
    monitoringSocket = new MockSocketServer(MONITORING_WS_URL)
    monitoringSocket.on('connection', (socket) => handleMonitoringConnection(socket))
  }
}

type MonitoringSocketMessage =
  | { type: 'metrics'; data: ReturnType<typeof mockDatabase.getMonitoringFeeds>['feeds'] }
  | { type: 'log'; data: { id: string; timestamp: string; level: 'INFO' | 'WARN' | 'DEBUG'; message: string } }
  | { type: 'waveform'; data: number[] }
  | { type: 'status'; data: { execStatus: 'running' | 'paused' | 'idle'; powerLevel: number; interferenceMode: 'off' | 'awgn' | 'co-channel' } }

function handleMonitoringConnection(socket: MockSocketClient) {
  let metricsTimer: number | null = null
  let waveformTimer: number | null = null
  let logTimer: number | null = null

  const send = (message: MonitoringSocketMessage) => {
    socket.send(JSON.stringify(message))
  }

  const sendInitial = () => {
    const { feeds } = mockDatabase.getMonitoringFeeds()
    send({ type: 'metrics', data: feeds })
    send({
      type: 'status',
      data: { execStatus: 'running', powerLevel: -20, interferenceMode: 'off' },
    })
    send({ type: 'waveform', data: generateWaveSamples(60) })
  }

  sendInitial()

  metricsTimer = window.setInterval(() => {
    const { feeds } = mockDatabase.getMonitoringFeeds()
    const nextFeeds = feeds.map((item) => {
      const jitter = (Math.random() - 0.5) * 5
      return {
        ...item,
        value: item.value.replace(/[-+]?\d+(\.\d+)?/, (match) => {
          const numeric = Number.parseFloat(match)
          if (Number.isNaN(numeric)) return match
          const next = numeric + jitter
          return next.toFixed(1)
        }),
        trend: Math.random() > 0.5 ? '↑' : Math.random() > 0.5 ? '↓' : '→',
      }
    })
    send({ type: 'metrics', data: nextFeeds })
  }, 5000)

  waveformTimer = window.setInterval(() => {
    send({ type: 'waveform', data: generateWaveSamples(5) })
  }, 1200)

  logTimer = window.setInterval(() => {
    send({ type: 'log', data: createLogEntry() })
  }, 4000)

  socket.on('message', (raw) => {
    if (typeof raw !== 'string') return
    try {
      const payload = JSON.parse(raw)
      if (payload?.action === 'pause') {
        if (metricsTimer !== null) window.clearInterval(metricsTimer)
        if (waveformTimer !== null) window.clearInterval(waveformTimer)
        if (logTimer !== null) window.clearInterval(logTimer)
        send({
          type: 'status',
          data: { execStatus: 'paused', powerLevel: -20, interferenceMode: 'off' },
        })
        metricsTimer = null
        waveformTimer = null
        logTimer = null
      }
      if (payload?.action === 'resume' && metricsTimer === null) {
        send({
          type: 'status',
          data: { execStatus: 'running', powerLevel: -20, interferenceMode: 'off' },
        })
        metricsTimer = window.setInterval(() => {
          const { feeds } = mockDatabase.getMonitoringFeeds()
          send({ type: 'metrics', data: feeds })
        }, 5000)
        waveformTimer = window.setInterval(() => {
          send({ type: 'waveform', data: generateWaveSamples(5) })
        }, 1200)
        logTimer = window.setInterval(() => {
          send({ type: 'log', data: createLogEntry() })
        }, 4000)
      }
    } catch {
      // ignore invalid payloads
    }
  })

  socket.on('close', () => {
    if (metricsTimer !== null) window.clearInterval(metricsTimer)
    if (waveformTimer !== null) window.clearInterval(waveformTimer)
    if (logTimer !== null) window.clearInterval(logTimer)
  })
}

function generateWaveSamples(length: number): number[] {
  const baseFrequency = 0.3 + Math.random() * 0.2
  const amplitude = 0.6 + Math.random() * 0.3
  return Array.from({ length }, (_, index) => {
    const phase = index * baseFrequency
    const noise = (Math.random() - 0.5) * 0.2
    return Math.sin(phase) * amplitude + noise
  })
}

function createLogEntry(): { id: string; timestamp: string; level: 'INFO' | 'WARN' | 'DEBUG'; message: string } {
  const sampleMessages = [
    '信道仿真器刷新多径权重。',
    'DUT 回传 ACK 丢失，准备重传。',
    '静区探测器返回幅度波纹 1.1 dB。',
    '转台保持 45°，等待下一步指令。',
    'PWG 平面波模式保持稳定。',
  ]
  const sampleLevels: Array<'INFO' | 'WARN' | 'DEBUG'> = ['INFO', 'DEBUG', 'WARN']
  const now = new Date()
  return {
    id: `log-${Date.now()}`,
    timestamp: now.toLocaleTimeString('zh-CN', { hour12: false }),
    level: sampleLevels[Math.floor(Math.random() * sampleLevels.length)],
    message: sampleMessages[Math.floor(Math.random() * sampleMessages.length)],
  }
}
