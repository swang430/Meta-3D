import type {
  AlertItem,
  DashboardResponse,
  DemoRunPlan,
  DemoRunPlanResponse,
  DemoRunResult,
  InstrumentCategory,
  InstrumentsResponse,
  MetricItem,
  MonitoringFeedsResponse,
  Probe,
  ProbesResponse,
  RecentTest,
  RecentTestsResponse,
  ReportTemplate,
  ReportTemplatesResponse,
  SequenceLibraryItem,
  SequenceLibraryResponse,
  SequenceStep,
  TestCase,
  TestCaseDetail,
  TestCaseResponse,
  TestCasesResponse,
  TestPlanDetail,
  TestPlanListResponse,
  TestPlanResponse,
  TestPlanSummary,
  TestTemplate,
  TestTemplatesResponse,
  UpdateInstrumentPayload,
  CreatePlanPayload,
  UpdatePlanPayload,
  CreateTestCaseFromPlanPayload,
  CreateTestCasePayload,
  CreateTestCaseResponse,
  DeleteTestCaseResponse,
} from '../types/api'

const systemStatus = [
  { label: '信道仿真器', value: '在线', detail: 'PROPSIM F64 #01' },
  { label: '基站仿真器', value: '空闲', detail: 'CMX500, NR-SA 3.5 GHz' },
  { label: '转台', value: '定位完成', detail: '方位 45°' },
  { label: '探头阵列', value: '校准通过', detail: '幅度波纹 0.8 dB' },
]

const activeAlerts: AlertItem[] = [
  { id: 'AL-1024', title: '放大器温度接近上限', severity: 'warning', timestamp: '10:21' },
  { id: 'AL-1026', title: '探头#17反馈延迟偏差', severity: 'info', timestamp: '09:58' },
]

const liveMetrics: MetricItem[] = [
  { label: '当前测试', value: 'NR UMi 城市路测回放' },
  { label: '时间戳', value: '2024-10-18 10:32:45' },
  { label: '测试进度', value: '62%' },
  { label: '静区幅度波纹', value: '0.9 dB' },
]

let probes: Probe[] = [
  { id: 'P-01', ring: '上层', polarization: 'V/H', position: '(2.50, 0.00, 1.00)m' },
  { id: 'P-02', ring: '上层', polarization: 'V/H', position: '(1.77, 1.77, 1.00)m' },
  { id: 'P-03', ring: '上层', polarization: 'V/H', position: '(0.00, 2.50, 1.00)m' },
  { id: 'P-04', ring: '上层', polarization: 'V/H', position: '(-1.77, 1.77, 1.00)m' },
  { id: 'P-05', ring: '上层', polarization: 'V/H', position: '(-2.50, 0.00, 1.00)m' },
  { id: 'P-06', ring: '上层', polarization: 'V/H', position: '(-1.77, -1.77, 1.00)m' },
  { id: 'P-07', ring: '上层', polarization: 'V/H', position: '(0.00, -2.50, 1.00)m' },
  { id: 'P-08', ring: '上层', polarization: 'V/H', position: '(1.77, -1.77, 1.00)m' },
  { id: 'P-09', ring: '中层', polarization: 'V/H', position: '(2.50, 0.00, 0.00)m' },
  { id: 'P-10', ring: '中层', polarization: 'V/H', position: '(2.31, 0.96, 0.00)m' },
  { id: 'P-11', ring: '中层', polarization: 'V/H', position: '(1.77, 1.77, 0.00)m' },
  { id: 'P-12', ring: '中层', polarization: 'V/H', position: '(0.96, 2.31, 0.00)m' },
  { id: 'P-13', ring: '中层', polarization: 'V/H', position: '(0.00, 2.50, 0.00)m' },
  { id: 'P-14', ring: '中层', polarization: 'V/H', position: '(-0.96, 2.31, 0.00)m' },
  { id: 'P-15', ring: '中层', polarization: 'V/H', position: '(-1.77, 1.77, 0.00)m' },
  { id: 'P-16', ring: '中层', polarization: 'V/H', position: '(-2.31, 0.96, 0.00)m' },
  { id: 'P-17', ring: '中层', polarization: 'V/H', position: '(-2.50, 0.00, 0.00)m' },
  { id: 'P-18', ring: '中层', polarization: 'V/H', position: '(-2.31, -0.96, 0.00)m' },
  { id: 'P-19', ring: '中层', polarization: 'V/H', position: '(-1.77, -1.77, 0.00)m' },
  { id: 'P-20', ring: '中层', polarization: 'V/H', position: '(-0.96, -2.31, 0.00)m' },
  { id: 'P-21', ring: '中层', polarization: 'V/H', position: '(0.00, -2.50, 0.00)m' },
  { id: 'P-22', ring: '中层', polarization: 'V/H', position: '(0.96, -2.31, 0.00)m' },
  { id: 'P-23', ring: '中层', polarization: 'V/H', position: '(1.77, -1.77, 0.00)m' },
  { id: 'P-24', ring: '中层', polarization: 'V/H', position: '(2.31, -0.96, 0.00)m' },
  { id: 'P-25', ring: '下层', polarization: 'V/H', position: '(2.31, 0.96, -1.00)m' },
  { id: 'P-26', ring: '下层', polarization: 'V/H', position: '(0.96, 2.31, -1.00)m' },
  { id: 'P-27', ring: '下层', polarization: 'V/H', position: '(-0.96, 2.31, -1.00)m' },
  { id: 'P-28', ring: '下层', polarization: 'V/H', position: '(-2.31, 0.96, -1.00)m' },
  { id: 'P-29', ring: '下层', polarization: 'V/H', position: '(-2.31, -0.96, -1.00)m' },
  { id: 'P-30', ring: '下层', polarization: 'V/H', position: '(-0.96, -2.31, -1.00)m' },
  { id: 'P-31', ring: '下层', polarization: 'V/H', position: '(0.96, -2.31, -1.00)m' },
  { id: 'P-32', ring: '下层', polarization: 'V/H', position: '(2.31, -0.96, -1.00)m' },
]

const sequenceLibrary: SequenceLibraryItem[] = [
  {
    id: 'lib-setup-frequency',
    title: '设置频率',
    meta: 'FR1/FR2 支持 · 自动功率归一化',
    description: '配置目标载频、带宽以及波束初始方向，可带功放策略。',
  },
  {
    id: 'lib-load-channel',
    title: '载入信道模型',
    meta: '3GPP CDL/TDL · 自定义波场',
    description: '指定信道模型、子路径参数或导入WFS矩阵。',
  },
  {
    id: 'lib-comm-standard',
    title: '通讯制式编辑',
    meta: 'NR / LTE / C-V2X 制式切换',
    description: '选择目标协议、上下行业务配置与核心网连接方式。',
  },
  {
    id: 'lib-rotate',
    title: '执行转台扫描',
    meta: '方位/俯仰扫描 · 支持多循环',
    description: '控制DUT转台或探头阵列，采集不同角度的性能数据。',
  },
  {
    id: 'lib-measure-kpi',
    title: '采集性能指标',
    meta: '吞吐量 / BLER / RSSI',
    description: '调用仪表和DUT API获取实时性能指标，并聚合为报告。',
  },
  {
    id: 'lib-power-scan',
    title: '功率扫描设置',
    meta: '功放线性区 · 灵敏度/阻塞用',
    description: '设定功率步进、放大器策略与保护阈值，生成功率扫描脚本。',
  },
  {
    id: 'lib-antenna-pattern',
    title: '天线Pattern',
    meta: '全向/定向测量 · 极化控制',
    description: '配置天线指向、极化与采样分辨率，用于生成3D方向图。',
  },
  {
    id: 'lib-export',
    title: '生成报告',
    meta: 'PDF / HTML / JSON',
    description: '按模板导出日志、静区指标、测试曲线等结果文件。',
  },
]

const storageKeyCases = 'mock-db-test-cases-v1'
const hasStorage = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'

const caseSnapshots: Record<string, SequenceStep[]> = {}

const testCaseLibrary: TestCase[] = [
  {
    id: 'CTIA-01-40',
    name: 'CTIA 01.40 OTA 性能测试',
    dut: '全尺寸SUV',
    createdAt: '2024-10-01',
    category: '标准认证',
    tags: ['CTIA', 'OTA', 'FR1'],
  },
  {
    id: 'VDS-001',
    name: '虚拟路测-城市峡谷',
    dut: 'SUV 平台',
    createdAt: '2024-10-08',
    category: '虚拟路测',
    tags: ['UMi', 'NLOS'],
  },
  {
    id: 'VDS-002',
    name: '虚拟路测-高速立交',
    dut: '轿车平台',
    createdAt: '2024-10-09',
    category: '虚拟路测',
    tags: ['高速', '多径'],
  },
  {
    id: 'VDS-003',
    name: '虚拟路测-郊区林地',
    dut: '跨界车',
    createdAt: '2024-10-10',
    category: '虚拟路测',
    tags: ['郊区', '衰落'],
  },
  {
    id: 'VDS-004',
    name: '虚拟路测-港口集装箱',
    dut: '原型车 A',
    createdAt: '2024-10-11',
    category: '虚拟路测',
    tags: ['散射', '遮挡'],
  },
  {
    id: 'VDS-005',
    name: '虚拟路测-隧道连贯场景',
    dut: '货车底盘',
    createdAt: '2024-10-12',
    category: '虚拟路测',
    tags: ['隧道', '连续场景'],
  },
  {
    id: 'TP-201',
    name: '5G NR OTA 灵敏度',
    dut: 'SUV 平台',
    createdAt: '2024-09-02',
    category: '性能验证',
    tags: ['NR', '灵敏度'],
  },
  {
    id: 'TP-317',
    name: 'C-V2X 场景仿真',
    dut: '轿车平台',
    createdAt: '2024-09-18',
    category: '车联网',
    tags: ['C-V2X', 'PC5'],
  },
  {
    id: 'TP-404',
    name: 'PWG 车顶天线方向图',
    dut: '原型车 A',
    createdAt: '2024-10-05',
    category: '方向图',
    tags: ['PWG', '天线'],
  },
]

const recentTests: RecentTest[] = [
  { id: 'R-1345', name: 'NR 城市宏场景', dut: 'Pilot SUV', result: '通过', date: '2024-10-15' },
  { id: 'R-1342', name: 'PWG 车顶天线', dut: 'Sedan X', result: '进行中', date: '2024-10-14' },
  { id: 'R-1338', name: 'C-V2X 干扰容限', dut: 'Prototype Z', result: '失败', date: '2024-10-12' },
]

const reportTemplates: ReportTemplate[] = [
  { id: 'RP-01', name: '认证报告', format: 'PDF', lastUpdated: '2024-09-28' },
  { id: 'RP-02', name: '研发调试报告', format: 'HTML', lastUpdated: '2024-10-10' },
]

const monitoringFeeds: MetricItem[] = [
  { id: 'metric-1', label: '吞吐量', value: '754 Mbps', trend: '↑' },
  { id: 'metric-2', label: 'SNR', value: '27.4 dB', trend: '→' },
  { id: 'metric-3', label: 'EVM', value: '2.9 %', trend: '↓' },
  { id: 'metric-4', label: '载干比', value: '18 dB', trend: '→' },
]

type TestPlanRecord = TestPlanDetail

let stepCounter = 1

const createStepId = () => `step-${String(stepCounter++).padStart(3, '0')}`
let customCaseCounter = 1

const createCaseId = () => `CUST-${String(customCaseCounter++).padStart(4, '0')}`

const formatDate = () => {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const stepTemplateDefaults: Record<string, Record<string, string>> = {
  'lib-setup-frequency': {
    frequencyMHz: '3500',
    bandwidthMHz: '100',
    powerDbm: '-3',
    referenceLevel: '仪表默认',
  },
  'lib-comm-standard': {
    standard: 'nr',
    uplinkProfile: 'NR-FR1-eMBB-UL',
    downlinkProfile: 'NR-FR1-eMBB-DL',
    coreNetwork: '5GC SA',
  },
  'lib-load-channel': {
    channelModel: '3GPP_CDL-C',
    dopplerProfile: '城市UMi',
    quietZoneTarget: '1.0 dB / 10°',
    calibrationProfile: '校准矩阵 v1.3',
  },
  'lib-rotate': {
    axis: 'azimuth',
    startAngleDeg: '0',
    stopAngleDeg: '360',
    stepAngleDeg: '15',
    dwellTimeSec: '1',
    postureSync: '启用',
  },
  'lib-measure-kpi': {
    averageCount: '5',
    sampleIntervalMs: '200',
    targetMetrics: '吞吐量, BLER, RSSI',
    storeRawTrace: '是',
  },
  'lib-power-scan': {
    startPowerDbm: '-30',
    stopPowerDbm: '10',
    stepPowerDb: '1',
    protectionThresholdDbm: '15',
  },
  'lib-antenna-pattern': {
    azimuthRange: '±180°',
    elevationRange: '±60°',
    resolutionDeg: '5',
    polarizationMode: 'V/H',
    referencePlane: '车顶坐标系',
  },
  'lib-export': {
    reportFormat: 'pdf',
    includeAttachments: '是',
    fileNamePrefix: 'OTA-Report',
    recipients: 'qa@lab.example',
  },
}

const caseBlueprints: Record<string, string[]> = {
  'CTIA-01-40': [
    'lib-setup-frequency',
    'lib-comm-standard',
    'lib-load-channel',
    'lib-rotate',
    'lib-measure-kpi',
    'lib-export',
  ],
  'VDS-001': ['lib-comm-standard', 'lib-load-channel', 'lib-rotate', 'lib-measure-kpi'],
  'VDS-002': ['lib-comm-standard', 'lib-load-channel', 'lib-antenna-pattern', 'lib-measure-kpi', 'lib-export'],
  'VDS-003': ['lib-load-channel', 'lib-rotate', 'lib-measure-kpi'],
  'VDS-004': ['lib-load-channel', 'lib-rotate', 'lib-power-scan', 'lib-measure-kpi'],
  'VDS-005': ['lib-load-channel', 'lib-rotate', 'lib-measure-kpi', 'lib-export'],
  'TP-201': ['lib-setup-frequency', 'lib-power-scan', 'lib-measure-kpi', 'lib-export'],
  'TP-317': ['lib-comm-standard', 'lib-load-channel', 'lib-measure-kpi', 'lib-export'],
  'TP-404': ['lib-antenna-pattern', 'lib-load-channel', 'lib-measure-kpi'],
}

const defaultBlueprint = ['lib-setup-frequency', 'lib-load-channel', 'lib-measure-kpi']

type PersistedCasePayload = {
  library: TestCase[]
  snapshots: Record<string, SequenceStep[]>
  blueprints: Record<string, string[]>
  customCounter: number
}

const loadPersistedCases = () => {
  if (!hasStorage) return
  try {
    const raw = window.localStorage.getItem(storageKeyCases)
    if (!raw) return
    const parsed = JSON.parse(raw) as PersistedCasePayload
    if (Array.isArray(parsed?.library)) {
      testCaseLibrary.splice(0, testCaseLibrary.length, ...parsed.library)
    }
    if (parsed?.snapshots && typeof parsed.snapshots === 'object') {
      Object.assign(caseSnapshots, parsed.snapshots)
    }
    if (parsed?.blueprints && typeof parsed.blueprints === 'object') {
      Object.assign(caseBlueprints, parsed.blueprints)
    }
    if (typeof parsed?.customCounter === 'number' && Number.isFinite(parsed.customCounter)) {
      customCaseCounter = parsed.customCounter
    }
  } catch (error) {
    console.warn('加载测试例缓存失败', error)
  }
}

const persistCases = () => {
  if (!hasStorage) return
  try {
    const payload: PersistedCasePayload = {
      library: clone(testCaseLibrary),
      snapshots: clone(caseSnapshots),
      blueprints: clone(caseBlueprints),
      customCounter: customCaseCounter,
    }
    window.localStorage.setItem(storageKeyCases, JSON.stringify(payload))
  } catch (error) {
    console.warn('保存测试例缓存失败', error)
  }
}

loadPersistedCases()

const createSnapshotFromTemplates = (templates: string[]): SequenceStep[] => {
  const result: SequenceStep[] = []
  templates.forEach((templateId) => {
    const template = sequenceLibrary.find((item) => item.id === templateId)
    if (!template) return
    const defaults = stepTemplateDefaults[template.id]
    result.push({
      id: template.id,
      templateId: template.id,
      title: template.title,
      meta: template.meta,
      description: template.description,
      parameters: defaults ? { ...defaults } : {},
    })
  })
  return result
}

const ensureCaseSnapshot = (caseId: string): SequenceStep[] => {
  if (!caseSnapshots[caseId] || caseSnapshots[caseId].length === 0) {
    const blueprint = caseBlueprints[caseId] ?? defaultBlueprint
    const snapshot = createSnapshotFromTemplates(blueprint)
    caseSnapshots[caseId] = snapshot
    persistCases()
  }
  return caseSnapshots[caseId]
}

const cloneBaseStepsForCase = (caseId: string): SequenceStep[] =>
  ensureCaseSnapshot(caseId).map((step) => ({
    id: createStepId(),
    templateId: step.templateId ?? step.id,
    title: step.title,
    meta: step.meta,
    description: step.description,
    parameters: step.parameters ? { ...step.parameters } : {},
  }))

const createSnapshotFromPlan = (steps: SequenceStep[]): SequenceStep[] =>
  steps.map((step) => ({
    id: step.templateId ?? step.id,
    templateId: step.templateId ?? step.id,
    title: step.title,
    meta: step.meta,
    description: step.description,
    parameters: step.parameters ? { ...step.parameters } : {},
  }))

const buildCaseDetail = (testCase: TestCase): TestCaseDetail => {
  const snapshot = ensureCaseSnapshot(testCase.id)
  const steps = snapshot.map((step, index) => ({
    id: `${step.templateId ?? step.id}-detail-${index}`,
    templateId: step.templateId ?? step.id,
    title: step.title,
    meta: step.meta,
    description: step.description,
    parameters: step.parameters ? { ...step.parameters } : {},
  }))
  return {
    ...testCase,
    steps,
  }
}

const findCaseName = (caseId: string) =>
  testCaseLibrary.find((item) => item.id === caseId)?.name ?? caseId

let testPlans: TestPlanRecord[] = [
  {
    id: 'PLAN-CTIA-Q4-A',
    name: 'CTIA 01.40 - Q4 场次A',
    caseId: 'CTIA-01-40',
    caseName: findCaseName('CTIA-01-40'),
    status: '草稿',
    updatedAt: '2024-10-18 10:20',
    notes: '预跑验证，使用SUV样车。',
    steps: cloneBaseStepsForCase('CTIA-01-40'),
  },
  {
    id: 'PLAN-VDS-URBAN-01',
    name: '虚拟路测·城市峡谷 10月回归',
    caseId: 'VDS-001',
    caseName: findCaseName('VDS-001'),
    status: '待执行',
    updatedAt: '2024-10-17 16:05',
    notes: '集成路测回放 v2.1，重点验证NLOS稳定性。',
    steps: cloneBaseStepsForCase('VDS-001'),
  },
]

const demoRunResult: DemoRunResult = {
  verdict: '通过',
  summary: 'CTIA 01.40 OTA 性能测试通过，关键指标满足规范，静区稳定且吞吐量裕度充足。',
  metrics: [
    { label: '下行吞吐量', baseline: '≥ 600 Mbps', measured: '742 Mbps', status: 'ok' },
    { label: '静区幅度波纹', baseline: '≤ 1.5 dB', measured: '0.9 dB', status: 'ok' },
    { label: 'BLER', baseline: '≤ 2.0 %', measured: '1.4 %', status: 'ok' },
    { label: '探头互耦补偿残差', baseline: '≤ 0.5 dB', measured: '0.3 dB', status: 'ok' },
  ],
  attachments: [
    { name: 'RUN-CTIA-DEMO-01-report.pdf', type: 'PDF', size: '1.2 MB' },
    { name: 'RUN-CTIA-DEMO-01-waveform.csv', type: 'CSV', size: '640 KB' },
  ],
  recommendations: [
    '建议在隧道及高架组合场景下追加虚拟路测，覆盖极端NLOS工况。',
    '对探头 #17 的反馈延迟继续跟踪，纳入下一轮校准复测计划。',
  ],
}

const demoRunPlan: DemoRunPlan = {
  id: 'RUN-CTIA-DEMO-01',
  templateId: 'CTIA-01-40',
  templateName: 'CTIA 01.40 OTA 性能测试',
  description:
    '该场景展示从加载 CTIA 标准模板、静区快速校准、信道模型加载，到执行旋转扫描、采集吞吐量并生成报告的完整自动化流程。',
  totalDuration: '约 32 分钟',
  steps: [
    {
      id: 'step-prep-template',
      title: '加载 CTIA 模板',
      goal: '导入标准化参数集并校验仪表连接状态。',
      duration: '2 分钟',
      deliverables: ['校验信道/基站仿真器在线状态', '填写 CTIA 01.40 关键参数表单'],
      kpis: ['模板加载耗时 < 120 s', '参数一致性 100%'],
    },
    {
      id: 'step-calibration',
      title: '执行静区快速校准',
      goal: '获取最新的幅度/相位补偿矩阵，确认静区性能。',
      duration: '8 分钟',
      deliverables: ['更新静区幅度补偿矩阵 v1.3', '生成互耦补偿残差报告'],
      kpis: ['幅度波纹 ≤ 1.0 dB', '相位均方差 ≤ 8°'],
    },
    {
      id: 'step-channel',
      title: '载入信道模型 CDL-C',
      goal: '配置 3GPP CDL-C 都市微蜂窝模型，并将权重下发至探头阵列。',
      duration: '5 分钟',
      deliverables: ['信道仿真器权重集 (64x64)', '驱动日志归档'],
      kpis: ['探头激励误差 ≤ 0.5 dB', '信道加载成功率 100%'],
    },
    {
      id: 'step-rotation',
      title: '执行 360° 旋转扫描',
      goal: '控制转台完成全方位扫描并同步采集姿态信息。',
      duration: '12 分钟',
      deliverables: ['45 个方位角采样点', '姿态同步日志'],
      kpis: ['扫描完成耗时 ≤ 15 分钟', '姿态同步丢包率 0%'],
    },
    {
      id: 'step-measure',
      title: '采集吞吐量/BLER',
      goal: '记录不同角度下的吞吐量、SNR 与 BLER，输出统计结果。',
      duration: '4 分钟',
      deliverables: ['吞吐量曲线', 'BLER 统计表'],
      kpis: ['平均吞吐量 ≥ 700 Mbps', 'BLER ≤ 2%'],
    },
    {
      id: 'step-report',
      title: '生成并归档报告',
      goal: '按 CTIA 模板生成报告并归档至结果库。',
      duration: '1 分钟',
      deliverables: ['PDF 报告', '波形与配置附件', '执行摘要'],
      kpis: ['报告生成成功率 100%', '归档平台确认'],
    },
  ],
  timeline: [
    {
      id: 'evt-000',
      offsetMs: 0,
      stepIndex: 0,
      level: 'INFO',
      message: '加载 CTIA 01.40 模板，校验仪器连接并写入基础参数。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '—', trend: '→' },
        { id: 'metric-2', label: 'SNR', value: '—', trend: '→' },
        { id: 'metric-3', label: 'EVM', value: '—', trend: '→' },
        { id: 'metric-4', label: '载干比', value: '—', trend: '→' },
      ],
    },
    {
      id: 'evt-001',
      offsetMs: 4000,
      stepIndex: 1,
      level: 'INFO',
      message: '静区快速校准启动，探头幅度补偿矩阵刷新中。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '准备中', trend: '→' },
        { id: 'metric-2', label: 'SNR', value: '27.0 dB', trend: '→' },
        { id: 'metric-3', label: 'EVM', value: '3.8 %', trend: '↑' },
        { id: 'metric-4', label: '载干比', value: '16 dB', trend: '↓' },
      ],
    },
    {
      id: 'evt-002',
      offsetMs: 12000,
      stepIndex: 2,
      level: 'INFO',
      message: '信道仿真器载入 CDL-C 模型，完成 64x64 探头权重下发。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '680 Mbps', trend: '↑' },
        { id: 'metric-2', label: 'SNR', value: '26.5 dB', trend: '→' },
        { id: 'metric-3', label: 'EVM', value: '3.1 %', trend: '↓' },
        { id: 'metric-4', label: '载干比', value: '17 dB', trend: '↑' },
      ],
      checkpoint: {
        summary: '信道模型校验完成，准备进入旋转扫描阶段。',
        progress: '已完成 2/6 步骤',
      },
    },
    {
      id: 'evt-003',
      offsetMs: 20000,
      stepIndex: 3,
      level: 'INFO',
      message: '转台进入方位扫描，姿态同步正常，采样点累计 18 个。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '715 Mbps', trend: '↑' },
        { id: 'metric-2', label: 'SNR', value: '27.9 dB', trend: '↑' },
        { id: 'metric-3', label: 'EVM', value: '2.6 %', trend: '↓' },
        { id: 'metric-4', label: '载干比', value: '18 dB', trend: '→' },
      ],
    },
    {
      id: 'evt-004',
      offsetMs: 26000,
      stepIndex: 4,
      level: 'INFO',
      message: '关键角度吞吐量采集中，实时平均值 742 Mbps，BLER 1.4%。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '742 Mbps', trend: '↑' },
        { id: 'metric-2', label: 'SNR', value: '28.4 dB', trend: '↑' },
        { id: 'metric-3', label: 'EVM', value: '2.4 %', trend: '↓' },
        { id: 'metric-4', label: '载干比', value: '18 dB', trend: '→' },
      ],
    },
    {
      id: 'evt-005',
      offsetMs: 32000,
      stepIndex: 5,
      level: 'INFO',
      message: '报告生成完成，上传结果管理系统并推送汇总。',
      metrics: [
        { id: 'metric-1', label: '吞吐量', value: '742 Mbps', trend: '→' },
        { id: 'metric-2', label: 'SNR', value: '28.4 dB', trend: '→' },
        { id: 'metric-3', label: 'EVM', value: '2.4 %', trend: '→' },
        { id: 'metric-4', label: '载干比', value: '18 dB', trend: '→' },
      ],
      result: demoRunResult,
    },
  ],
  result: demoRunResult,
}

let instrumentCatalog: InstrumentCategory[] = [
  {
    key: 'channel-emulator',
    label: '信道仿真器',
    description: '驱动MPAC阵列并合成目标波场，支持WFS/PWG模式。',
    tags: ['64TRX', 'WFS', 'PWG'],
    selectedModelId: 'propsim-f64',
    connection: { endpoint: '192.168.100.21', controller: 'LAN', notes: '暗室机柜1#' },
    models: [
      {
        id: 'ksw-wns02b',
        vendor: 'KSW',
        model: 'WNS02B',
        summary: '64通道组网信道仿真仪，支持中文SCPI与JSON场景导入。',
        interfaces: ['LAN/SCPI', 'REST'],
        capabilities: ['64x64 MIMO', '400 MHz 带宽', '多机同步'],
        bandwidth: '400 MHz',
        channels: '64 TRX',
        status: 'available',
      },
      {
        id: 'propsim-f64',
        vendor: 'Keysight',
        model: 'PROPSIM F64',
        summary: '车载OTA标杆平台，具备多节点同步与动态路测回放能力。',
        interfaces: ['LAN/SCPI', 'REST', 'LXI'],
        capabilities: ['64x2 TRX', '动态场景回放', '可编程噪声'],
        bandwidth: '400 MHz',
        channels: '64 TRX',
        status: 'available',
      },
      {
        id: 'spirent-vertex',
        vendor: 'Spirent',
        model: 'Vertex 64',
        summary: '面向6G研究的波场合成平台，支持Python API与毫米波扩展。',
        interfaces: ['REST', 'Python SDK'],
        capabilities: ['多机级联', '毫米波扩展', '实时统计'],
        bandwidth: '500 MHz',
        channels: '64 TRX',
        status: 'reserved',
      },
    ],
  },
  {
    key: 'base-station-emulator',
    label: '基站仿真器',
    description: '生成5G NR/LTE/C-V2X协议栈信号，提供核心网交互。',
    tags: ['5G NR', 'C-V2X'],
    selectedModelId: 'rs-cmx500',
    connection: { endpoint: '192.168.100.11', controller: 'LAN', notes: 'NR-SA 模式' },
    models: [
      {
        id: 'rs-cmx500',
        vendor: 'Rohde & Schwarz',
        model: 'CMX500',
        summary: '支持5G NR Rel-17与Wi-Fi 7，内置端到端测量工作流。',
        interfaces: ['LAN/SCPI', 'REST'],
        capabilities: ['NR SA/NSA', 'C-V2X PC5', 'VoNR'],
        status: 'available',
      },
      {
        id: 'keysight-uxm',
        vendor: 'Keysight',
        model: 'UXM 5G',
        summary: '多小区基站仿真平台，适配空口一致性与OTA联调。',
        interfaces: ['LAN/SCPI', 'REST'],
        capabilities: ['MIMO/CA', '高阶调制', 'NB-IoT'],
        status: 'maintenance',
      },
      {
        id: 'anritsu-md8475',
        vendor: 'Anritsu',
        model: 'MD8475B',
        summary: '多制式综合测试平台，兼容LTE-A、C-V2X及Legacy制式。',
        interfaces: ['LAN/SCPI'],
        capabilities: ['LTE/LTE-A', 'WCDMA', 'C-V2X PC5'],
        status: 'available',
      },
    ],
  },
  {
    key: 'vna',
    label: '矢量网络分析仪',
    description: '用于静区路径校准与探头S参数测量，覆盖FR1全频段。',
    tags: ['校准', 'S参数'],
    selectedModelId: 'keysight-pna',
    connection: { endpoint: '192.168.100.31', controller: 'LAN', notes: '校准台专用' },
    models: [
      {
        id: 'keysight-pna',
        vendor: 'Keysight',
        model: 'PNA N5247B',
        summary: '67 GHz 双端口PNA，支持时间域转换与脉冲测量。',
        interfaces: ['LAN/SCPI', 'USB'],
        capabilities: ['时域转换', '脉冲调制', '宽带S参数'],
        status: 'available',
      },
      {
        id: 'rs-zna43',
        vendor: 'Rohde & Schwarz',
        model: 'ZNA43',
        summary: '43.5 GHz 四端口VNA，具备多端口校准向导。',
        interfaces: ['LAN/SCPI', 'GPIB'],
        capabilities: ['四端口', '相位同步', '高动态范围'],
        status: 'available',
      },
      {
        id: 'copper-mtn-6080',
        vendor: 'Copper Mountain',
        model: 'S5065',
        summary: '紧凑型6.5 GHz USB VNA，适合便携校准与现场验证。',
        interfaces: ['USB', 'LAN'],
        capabilities: ['2端口', '便携式', '脚本自动化'],
        status: 'offline',
      },
    ],
  },
  {
    key: 'spectrum-analyzer',
    label: '频谱与信号分析仪',
    description: '用于实时监控静区内杂散、干扰与波束功率分布。',
    tags: ['监控', '干扰'],
    selectedModelId: 'rsa-306',
    connection: { endpoint: '', controller: 'USB', notes: '便携式采样' },
    models: [
      {
        id: 'rs-fsv3070',
        vendor: 'Rohde & Schwarz',
        model: 'FSV3070',
        summary: '7 GHz 中档频谱仪，支持EVM与ACLR分析。',
        interfaces: ['LAN/SCPI', 'USB'],
        capabilities: ['ACLR', 'EVM', '多信号存储'],
        status: 'available',
      },
      {
        id: 'tek-rsa7100',
        vendor: 'Tektronix',
        model: 'RSA7100B',
        summary: '110 MHz 实时带宽，适合干扰监测与录波。',
        interfaces: ['LAN', 'USB3.0'],
        capabilities: ['实时频谱', '长时捕获', 'IQ导出'],
        status: 'reserved',
      },
      {
        id: 'rsa-306',
        vendor: 'Tektronix',
        model: 'RSA306B',
        summary: 'USB 6.2 GHz 便携频谱仪，快速部署于暗室巡检。',
        interfaces: ['USB3.0'],
        capabilities: ['便携式', '实时DPX', 'SignalVu-PC'],
        status: 'available',
      },
    ],
  },
]

const bumpPlanTimestamp = (plan: TestPlanRecord) => {
  const now = new Date()
  plan.updatedAt = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

const clone = <T,>(data: T): T => JSON.parse(JSON.stringify(data))

export const mockDatabase = {
  getDashboard(): DashboardResponse {
    return clone({ systemStatus, activeAlerts, liveMetrics })
  },
  getProbes(): ProbesResponse {
    return { probes: clone(probes) }
  },
  setProbes(next: Probe[]): ProbesResponse {
    const map = new Map<string, Probe>()
    next.forEach((probe) => {
      if (!probe?.id) return
      map.set(probe.id, {
        id: probe.id,
        ring: probe.ring ?? '中层',
        polarization: probe.polarization ?? 'V/H',
        position: probe.position ?? '(0.0, 0.0, 0.0)m',
      })
    })
    probes = Array.from(map.values())
    return { probes: clone(probes) }
  },
  createProbe(probe: Probe): Probe {
    probes = [...probes.filter((item) => item.id !== probe.id), probe]
    return clone(probe)
  },
  updateProbe(id: string, payload: Omit<Probe, 'id'>): Probe | null {
    const index = probes.findIndex((probe) => probe.id === id)
    if (index === -1) return null
    probes[index] = { ...probes[index], ...payload }
    return clone(probes[index])
  },
  deleteProbe(id: string): boolean {
    const lengthBefore = probes.length
    probes = probes.filter((probe) => probe.id !== id)
    return probes.length < lengthBefore
  },
  getSequenceLibrary(): SequenceLibraryResponse {
    return { library: clone(sequenceLibrary) }
  },
  getTestTemplates(): TestTemplatesResponse {
    // 兼容旧接口，返回同样结构
    return {
      templates: clone(
        testCaseLibrary.map<TestTemplate>(({ id, name, dut, createdAt }) => ({
          id,
          name,
          dut,
          createdAt,
        })),
      ),
    }
  },
  getTestCases(): TestCasesResponse {
    return { cases: clone(testCaseLibrary) }
  },
  createTestCase(payload: CreateTestCasePayload): CreateTestCaseResponse | null {
    const rawBlueprint = payload.blueprint?.map((templateId) => templateId.trim()).filter(Boolean) ?? []
    const filteredBlueprint = rawBlueprint.filter((templateId) =>
      sequenceLibrary.some((item) => item.id === templateId),
    )
    const uniqueBlueprint = Array.from(new Set(filteredBlueprint))
    const blueprint = uniqueBlueprint.length > 0 ? uniqueBlueprint : defaultBlueprint
    const snapshot = createSnapshotFromTemplates(blueprint)
    if (snapshot.length === 0) {
      return null
    }
    const caseId = createCaseId()
    caseSnapshots[caseId] = snapshot
    caseBlueprints[caseId] = blueprint
    const tags = payload.tags?.map((tag) => tag.trim()).filter((tag) => tag.length > 0) ?? []
    const newCase: TestCase = {
      id: caseId,
      name: payload.name,
      dut: payload.dut,
      createdAt: formatDate(),
      category: payload.category,
      tags,
      description: payload.description,
    }
    testCaseLibrary.unshift(newCase)
    persistCases()
    return { testCase: buildCaseDetail(newCase) }
  },
  getTestCaseDetail(caseId: string): TestCaseResponse | null {
    const target = testCaseLibrary.find((item) => item.id === caseId)
    if (!target) return null
    ensureCaseSnapshot(caseId)
    return { testCase: buildCaseDetail(target) }
  },
  deleteTestCase(caseId: string): DeleteTestCaseResponse {
    const index = testCaseLibrary.findIndex((item) => item.id === caseId)
    if (index === -1) {
      return { success: false }
    }
    testCaseLibrary.splice(index, 1)
    delete caseBlueprints[caseId]
    delete caseSnapshots[caseId]
    persistCases()
    return { success: true }
  },
  getTestPlans(): TestPlanListResponse {
    const plans = testPlans.map<TestPlanSummary>((plan) => ({
      id: plan.id,
      name: plan.name,
      caseId: plan.caseId,
      caseName: plan.caseName,
      status: plan.status,
      updatedAt: plan.updatedAt,
      owner: 'AutoLab',
    }))
    return { plans: clone(plans) }
  },
  getTestPlan(planId: string): TestPlanResponse | null {
    const plan = testPlans.find((item) => item.id === planId)
    if (!plan) return null
    return { plan: clone(plan) }
  },
  createTestPlan(payload: CreatePlanPayload): TestPlanResponse | null {
    const targetCase = testCaseLibrary.find((item) => item.id === payload.caseId)
    if (!targetCase) return null
    const plan: TestPlanRecord = {
      id: `PLAN-${payload.caseId}-${Date.now().toString(36).toUpperCase()}`,
      name: payload.name || `${targetCase.name} - 新建计划`,
      caseId: targetCase.id,
      caseName: targetCase.name,
      status: '草稿',
      updatedAt: '刚刚',
      notes: '',
      steps: cloneBaseStepsForCase(targetCase.id),
    }
    testPlans = [plan, ...testPlans]
    bumpPlanTimestamp(plan)
    return { plan: clone(plan) }
  },
  updateTestPlan(planId: string, payload: UpdatePlanPayload): TestPlanResponse | null {
    const index = testPlans.findIndex((item) => item.id === planId)
    if (index === -1) return null
    const current = testPlans[index]
    const next: TestPlanRecord = {
      ...current,
      name: payload.name ?? current.name,
      status: payload.status ?? current.status,
      notes: payload.notes ?? current.notes,
    }
    if (payload.steps) {
      next.steps = payload.steps.map((step) => {
        const templateId = step.templateId ?? step.id
        const template = sequenceLibrary.find((item) => item.id === templateId)
        const defaults = templateId ? stepTemplateDefaults[templateId] : undefined
        return {
          id: step.id || createStepId(),
          templateId: template?.id ?? templateId,
          title: step.title,
          meta: step.meta,
          description: step.description,
          parameters: step.parameters ? { ...step.parameters } : defaults ? { ...defaults } : {},
        }
      })
    }
    bumpPlanTimestamp(next)
    testPlans[index] = next
    return { plan: clone(next) }
  },
  savePlanAsTestCase(payload: CreateTestCaseFromPlanPayload): CreateTestCaseResponse | null {
    const sourcePlan = testPlans.find((item) => item.id === payload.sourcePlanId)
    if (!sourcePlan) return null
    const requestedId = payload.caseId?.trim()
    let caseId = requestedId && requestedId.length > 0 ? requestedId : createCaseId()
    if (testCaseLibrary.some((item) => item.id === caseId)) {
      caseId = `${caseId}-${Date.now().toString(36).toUpperCase()}`
    }
    const sourceSteps = payload.steps && payload.steps.length > 0 ? payload.steps : sourcePlan.steps
    const snapshot = createSnapshotFromPlan(sourceSteps)
    caseSnapshots[caseId] = snapshot
    caseBlueprints[caseId] = snapshot.map((step) => step.templateId ?? step.id)
    const tags = payload.tags?.map((tag) => tag.trim()).filter((tag) => tag.length > 0) ?? []
    const newCase: TestCase = {
      id: caseId,
      name: payload.name,
      dut: payload.dut,
      createdAt: formatDate(),
      category: payload.category,
      tags,
      description: payload.description,
    }
    const existingIndex = testCaseLibrary.findIndex((item) => item.id === caseId)
    if (existingIndex !== -1) {
      testCaseLibrary.splice(existingIndex, 1)
    }
    testCaseLibrary.unshift(newCase)
    persistCases()
    return { testCase: buildCaseDetail(newCase) }
  },
  appendPlanStep(planId: string, libraryId: string): TestPlanResponse | null {
    const plan = testPlans.find((item) => item.id === planId)
    if (!plan) return null
    const template = sequenceLibrary.find((item) => item.id === libraryId)
    if (!template) return null
    const defaults = stepTemplateDefaults[template.id]
    const newStep: SequenceStep = {
      id: createStepId(),
      templateId: template.id,
      title: template.title,
      meta: template.meta,
      description: template.description,
      parameters: defaults ? { ...defaults } : {},
    }
    plan.steps = [...plan.steps, newStep]
    bumpPlanTimestamp(plan)
    return { plan: clone(plan) }
  },
  reorderPlanStep(planId: string, fromId: string, toId: string | '__end__'): TestPlanResponse | null {
    const plan = testPlans.find((item) => item.id === planId)
    if (!plan) return null
    const fromIndex = plan.steps.findIndex((step) => step.id === fromId)
    if (fromIndex === -1) return null
    const updated = [...plan.steps]
    const [moved] = updated.splice(fromIndex, 1)
    if (toId === '__end__') {
      updated.push(moved)
    } else {
      const toIndex = updated.findIndex((step) => step.id === toId)
      if (toIndex === -1) return null
      updated.splice(toIndex, 0, moved)
    }
    plan.steps = updated
    bumpPlanTimestamp(plan)
    return { plan: clone(plan) }
  },
  removePlanStep(planId: string, stepId: string): TestPlanResponse | null {
    const plan = testPlans.find((item) => item.id === planId)
    if (!plan) return null
    plan.steps = plan.steps.filter((step) => step.id !== stepId)
    bumpPlanTimestamp(plan)
    return { plan: clone(plan) }
  },
  deleteTestPlan(planId: string): { success: boolean } {
    const index = testPlans.findIndex((item) => item.id === planId)
    if (index === -1) return { success: false }
    testPlans.splice(index, 1)
    return { success: true }
  },
  reorderPlanQueue(planId: string, direction: 'up' | 'down' | 'top' | 'bottom'): TestPlanListResponse {
    const index = testPlans.findIndex((item) => item.id === planId)
    if (index === -1) {
      return this.getTestPlans()
    }
    const [plan] = testPlans.splice(index, 1)
    switch (direction) {
      case 'top':
        testPlans.unshift(plan)
        break
      case 'bottom':
        testPlans.push(plan)
        break
      case 'up': {
        const targetIndex = Math.max(index - 1, 0)
        testPlans.splice(targetIndex, 0, plan)
        break
      }
      case 'down': {
        const targetIndex = Math.min(index + 1, testPlans.length)
        testPlans.splice(targetIndex, 0, plan)
        break
      }
      default:
        testPlans.splice(index, 0, plan)
        break
    }
    return this.getTestPlans()
  },
  getRecentTests(): RecentTestsResponse {
    return { recentTests: clone(recentTests) }
  },
  getReportTemplates(): ReportTemplatesResponse {
    return { reportTemplates: clone(reportTemplates) }
  },
  getMonitoringFeeds(): MonitoringFeedsResponse {
    return { feeds: clone(monitoringFeeds) }
  },
  getDemoRunPlan(): DemoRunPlanResponse {
    return { plan: clone(demoRunPlan) }
  },
  getInstrumentCatalog(): InstrumentsResponse {
    return { categories: clone(instrumentCatalog) }
  },
  updateInstrumentCategory(categoryKey: string, payload: UpdateInstrumentPayload): InstrumentCategory | null {
    const index = instrumentCatalog.findIndex((item) => item.key === categoryKey)
    if (index === -1) return null
    const current = instrumentCatalog[index]
    const next: InstrumentCategory = {
      ...current,
      connection: {
        ...current.connection,
        ...(payload.connection ?? {}),
      },
      selectedModelId: current.selectedModelId,
    }
    if (payload.modelId && next.models.some((model) => model.id === payload.modelId)) {
      next.selectedModelId = payload.modelId
    }
    instrumentCatalog[index] = next
    return clone(next)
  },
}
