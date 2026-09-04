import MockAdapter from 'axios-mock-adapter'
import { Server as MockSocketServer, type Client as MockSocketClient } from 'mock-socket'
import client from './client'
import { mockDatabase } from './mockDatabase'
import type {
  CreatePlanPayload,
  UpdatePlanPayload,
  CreateTestCaseFromPlanPayload,
} from '../types/api'
import type { components as ApiComponents } from '../types/api.generated'
import type { TemplateListResponse } from '../features/Reports/types'

type ContractTestCase = ApiComponents['schemas']['TestCaseResponse']
type ContractTestCaseCreate = ApiComponents['schemas']['TestCaseCreate']
type ContractTestCaseUpdate = ApiComponents['schemas']['TestCaseUpdate']

let mock: MockAdapter | null = null
let monitoringSocket: MockSocketServer | null = null
const contractTestCases = new Map<string, ContractTestCase>()

const DELAY_MS = 300
const mockReportTemplates: TemplateListResponse['templates'] = [
  {
    id: 'mock-report-template-standard',
    name: '标准 MIMO OTA 报告模板（演示）',
    template_type: 'standard',
    is_active: true,
    is_default: true,
    usage_count: 0,
    created_by: 'mock-server',
    created_at: '2026-01-01T00:00:00Z',
  },
]
// Dynamically construct WebSocket URL based on current host
const MONITORING_WS_URL = typeof window !== 'undefined'
  ? `${window.location.origin.replace(/^http/, 'ws')}/api/v1/ws/monitoring`
  : 'ws://localhost:8000/api/v1/ws/monitoring'

export function setupMockServer() {
  if (mock) return

  mock = new MockAdapter(client, { delayResponse: DELAY_MS })

  // P2-24: TestCase CRUD 的 mock 与 live 契约使用同一 lab_profile_id 形态。
  // testPlanService 复用共享 client，mock 模式下创建/编辑也会走到这里。
  mock.onGet(/\/test-plans\/cases(?:\?.*)?$/).reply((config) => {
    const params = new URLSearchParams((config.url || '').split('?')[1] || '')
    let items = Array.from(contractTestCases.values())
    const testType = params.get('test_type')
    const isTemplate = params.get('is_template')
    if (testType) items = items.filter((item) => item.test_type === testType)
    if (isTemplate !== null) {
      items = items.filter((item) => item.is_template === (isTemplate === 'true'))
    }
    return [200, { total: items.length, items }]
  })

  mock.onPost('/test-plans/cases').reply((config) => {
    const payload = JSON.parse(config.data) as ContractTestCaseCreate
    const now = new Date().toISOString()
    const id = globalThis.crypto?.randomUUID?.()
      ?? `00000000-0000-4000-8000-${String(Date.now()).padStart(12, '0').slice(-12)}`
    const created: ContractTestCase = {
      id,
      name: payload.name,
      description: payload.description ?? null,
      test_type: payload.test_type,
      configuration: payload.configuration,
      pass_criteria: payload.pass_criteria ?? null,
      expected_results: payload.expected_results ?? null,
      probe_selection: payload.probe_selection ?? null,
      instrument_config: payload.instrument_config ?? null,
      channel_model: payload.channel_model ?? null,
      channel_parameters: payload.channel_parameters ?? null,
      frequency_mhz: payload.frequency_mhz ?? null,
      tx_power_dbm: payload.tx_power_dbm ?? null,
      bandwidth_mhz: payload.bandwidth_mhz ?? null,
      test_duration_sec: payload.test_duration_sec ?? null,
      lab_profile_id: payload.lab_profile_id ?? null,
      is_template: payload.is_template ?? false,
      template_category: payload.template_category ?? null,
      created_by: payload.created_by,
      created_at: now,
      updated_at: now,
      version: '1.0',
      parent_id: null,
      tags: payload.tags ?? [],
    }
    contractTestCases.set(id, created)
    return [201, created]
  })

  mock.onGet(/\/test-plans\/cases\/[^/]+$/).reply((config) => {
    const id = config.url?.split('/').pop() ?? ''
    const row = contractTestCases.get(id)
    return row ? [200, row] : [404, { detail: 'Test case not found' }]
  })

  mock.onPatch(/\/test-plans\/cases\/[^/]+$/).reply((config) => {
    const id = config.url?.split('/').pop() ?? ''
    const row = contractTestCases.get(id)
    if (!row) return [404, { detail: 'Test case not found' }]
    const payload = JSON.parse(config.data) as ContractTestCaseUpdate
    const nonNullPatch = Object.fromEntries(
      Object.entries(payload).filter(
        ([key, value]) => key === 'lab_profile_id' || value !== null,
      ),
    )
    const updated: ContractTestCase = {
      ...row,
      ...nonNullPatch,
      lab_profile_id:
        Object.prototype.hasOwnProperty.call(payload, 'lab_profile_id')
          ? payload.lab_profile_id ?? null
          : row.lab_profile_id,
      updated_at: new Date().toISOString(),
    } as ContractTestCase
    contractTestCases.set(id, updated)
    return [200, updated]
  })

  mock.onDelete(/\/test-plans\/cases\/[^/]+$/).reply((config) => {
    const id = config.url?.split('/').pop() ?? ''
    return contractTestCases.delete(id)
      ? [204]
      : [404, { detail: 'Test case not found' }]
  })

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

  mock.onGet('/tests/demo-run').reply(200, mockDatabase.getDemoRunPlan())

  // 报告模板页仍使用这条活动路径。复用 feature 的权威响应契约，避免旧 mock
  // {reportTemplates} 形态冒充 live 接口，也避免启用 Mock Server 后页面 404。
  mock.onGet('/reports/templates').reply((config) => {
    const templateType = config.params?.template_type
    const active = config.params?.is_active
    const templates = mockReportTemplates.filter((template) => (
      (templateType === undefined || template.template_type === templateType)
      && (active === undefined || template.is_active === active)
    ))
    const response: TemplateListResponse = {
      templates,
      total: templates.length,
      page: 1,
      page_size: 20,
    }
    return [200, response]
  })

  // ===== P2-8 Operational Cockpit =====
  mock.onGet('/instruments/hal/readiness').reply(200, mockDatabase.getReadiness())

  // P2-58 ①/②：channelEmulator binding 只读预览 —— 与 readiness 里的 channel_emulator_binding 同一夹具。
  mock
    .onGet(/\/lab-profiles\/[^/]+\/instrument-bindings\/channelEmulator\/preview$/)
    .reply(200, mockDatabase.getChannelEmulatorBindingPreview())

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
      params.filename,
      params.lines ? Number(params.lines) : undefined,
      params.level,
      params.keyword,
      params.session_id,
      params.execution_id,
    )]
  })

  mock.onGet('/system-logs/history').reply((config) => {
    const params = config.params || {}
    const result = mockDatabase.getSystemLogsHistory(
      params.cursor,
      params.filename,
      params.lines ? Number(params.lines) : undefined,
      params.level,
      params.keyword,
      params.session_id,
      params.execution_id,
    )
    return [result.status, result.body]
  })

  mock.onGet('/system-logs/files').reply(200, mockDatabase.getSystemLogFiles())

  mock.onGet('/dashboard/alerts/summary').reply(200, mockDatabase.getDashboardAlertSummary())

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
