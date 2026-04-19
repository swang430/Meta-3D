const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageNumber, PageBreak
} = require("docx");

// ==================== 通用工具 ====================
const TB = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
const CB = { top: TB, bottom: TB, left: TB, right: TB };
const HEADER_FILL = { fill: "1B3A5C", type: ShadingType.CLEAR };
const SUB_HEADER_FILL = { fill: "E8EEF4", type: ShadingType.CLEAR };
const ACCENT_FILL = { fill: "F0F5FA", type: ShadingType.CLEAR };
const DONE_FILL = { fill: "E8F5E9", type: ShadingType.CLEAR };
const WARN_FILL = { fill: "FFF8E1", type: ShadingType.CLEAR };
const RISK_FILL = { fill: "FBE9E7", type: ShadingType.CLEAR };
const PROGRESS_FILL = { fill: "E3F2FD", type: ShadingType.CLEAR };

function hCell(text, width, opts = {}) {
  return new TableCell({
    borders: CB, width: { size: width, type: WidthType.DXA },
    shading: opts.shading || HEADER_FILL,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 60, after: 60 },
      children: [new TextRun({ text, bold: true, size: 20, color: opts.color || "FFFFFF", font: "Arial" })]
    })]
  });
}

function dCell(text, width, opts = {}) {
  const children = [];
  if (typeof text === "string") {
    children.push(new Paragraph({
      spacing: { before: 40, after: 40 },
      children: [new TextRun({ text, size: 20, font: "Arial", ...opts.run })]
    }));
  } else if (Array.isArray(text)) {
    text.forEach(t => {
      children.push(new Paragraph({
        spacing: { before: 30, after: 30 },
        children: [new TextRun({ text: t, size: 20, font: "Arial", ...opts.run })]
      }));
    });
  }
  return new TableCell({
    borders: CB, width: { size: width, type: WidthType.DXA },
    shading: opts.shading || undefined,
    verticalAlign: VerticalAlign.CENTER,
    children
  });
}

function bCell(items, width, ref, opts = {}) {
  return new TableCell({
    borders: CB, width: { size: width, type: WidthType.DXA },
    shading: opts.shading || undefined,
    verticalAlign: VerticalAlign.TOP,
    children: items.map(item => new Paragraph({
      numbering: { reference: ref, level: 0 },
      spacing: { before: 20, after: 20 },
      children: [new TextRun({ text: item, size: 20, font: "Arial" })]
    }))
  });
}

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: { before: opts.before || 120, after: opts.after || 120 },
    alignment: opts.align,
    children: Array.isArray(text)
      ? text.map(t => typeof t === "string" ? new TextRun({ text: t, size: 22, font: "Arial" }) : new TextRun({ size: 22, font: "Arial", ...t }))
      : [new TextRun({ text, size: 22, font: "Arial", ...opts.run })]
  });
}

function bullet(text, ref = "bl") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, size: 22, font: "Arial" })]
  });
}

function gap() { return new Paragraph({ spacing: { before: 60, after: 60 }, children: [] }); }
function pb() { return new Paragraph({ children: [new PageBreak()] }); }

// ==================== Bullet Configs ====================
const bulletRefs = ["bl","bl2","bl3","bl4","bl5","bl6","bl7","bl8","bl9","bla","blb","blc","bld","ble","blf","blg","blh","bli"];
const bulletConfigs = bulletRefs.map(ref => ({
  reference: ref,
  levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 720, hanging: 360 } } } }]
}));

// ==================== 文档内容 ====================
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal",
        run: { size: 52, bold: true, color: "1B3A5C", font: "Arial" },
        paragraph: { spacing: { before: 360, after: 200 }, alignment: AlignmentType.CENTER } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: "1B3A5C", font: "Arial" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: "2E5984", font: "Arial" },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "3E7CB1", font: "Arial" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: bulletConfigs },
  sections: [
    {
      properties: {
        page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
      },
      headers: {
        default: new Header({ children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "MIMO-First | 内部文档 | 机密", size: 18, color: "999999", font: "Arial" })]
        })] })
      },
      footers: {
        default: new Footer({ children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "第 ", size: 18, font: "Arial" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Arial" }),
            new TextRun({ text: " 页 / 共 ", size: 18, font: "Arial" }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, font: "Arial" }),
            new TextRun({ text: " 页", size: 18, font: "Arial" }),
          ]
        })] })
      },
      children: [
        // ======================== 封面 ========================
        gap(), gap(), gap(), gap(), gap(),
        new Paragraph({
          alignment: AlignmentType.CENTER, spacing: { after: 100 },
          children: [new TextRun({ text: "Meta-3D MIMO OTA 测试系统", size: 36, color: "666666", font: "Arial" })]
        }),
        new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("静态 MIMO-OTA 冲刺计划")] }),
        new Paragraph({
          alignment: AlignmentType.CENTER, spacing: { before: 80, after: 400 },
          children: [new TextRun({ text: "v3.0 — 首轮静态 MIMO OTA 精细化执行方案", size: 28, color: "2E5984", font: "Arial", italics: true })]
        }),
        gap(),
        new Table({
          columnWidths: [3000, 6360],
          rows: [
            new TableRow({ children: [
              dCell("文档版本", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("v3.0", 6360)
            ]}),
            new TableRow({ children: [
              dCell("编制日期", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("2026-04-19", 6360)
            ]}),
            new TableRow({ children: [
              dCell("基准代码", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("main @ 2026-04-19 (HAL 18文件 5166行, App.tsx 5910行, 校准服务 11个)", 6360)
            ]}),
            new TableRow({ children: [
              dCell("计划时长", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("18 个工作日（约 3.5 周）", 6360)
            ]}),
            new TableRow({ children: [
              dCell("前序文档", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("静态MIMO-OTA冲刺计划 v2.0 (2026-04-19)", 6360)
            ]}),
            new TableRow({ children: [
              dCell("变更说明", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell([
                "v3.0 核心变更:",
                "• 新增 §3: 2026-04-19 开发成果总结（RF Switch HAL, Option B, 5阶段编排, Bug 修复）",
                "• Phase 0/0.5 全部标记已完成（实际已闭环）",
                "• Phase 1 从 3天 调整为 2天（UXM/CMW500 驱动骨架已完成）",
                "• 新增 §7.4: ASC 文件产物管理与验证规程",
                "• 新增 §9.3: 已修复的技术债务清单",
                "• 更新附录代码清单（18个HAL文件, 5166行）",
              ], 6360)
            ]}),
          ]
        }),

        // ======================== 1. 概述 ========================
        pb(),
        heading("1. 概述与目标"),
        heading("1.1 冲刺定位", HeadingLevel.HEADING_2),
        para("本冲刺是 MIMO-First 项目从「软件仿真平台」向「真实硬件测试系统」跨越的关键里程碑。冲刺结束后，系统将具备在物理暗室中完成一次完整的静态 MIMO OTA 吞吐量测试的能力，并自动生成符合 3GPP/CTIA 规范的测试报告。"),

        heading("1.2 v3.0 与 v2.0 的核心差异", HeadingLevel.HEADING_2),
        para([
          { text: "v2.0 是基于代码审计的蓝图规划；v3.0 融入了实际开发验证。", bold: true },
          { text: " 2026-04-19 完成了一整天的密集开发迭代，消除了多个阻塞项，使 Phase 0/0.5 提前完成。以下是关键差异：" }
        ]),
        bullet("RF Switch HAL: 从「需新建」(v2.0 标红) → 已完成 240 行代码 (含抽象接口 + Mock + ETS-Lindgren 真实驱动 + Option B 端口映射)", "bl"),
        bullet("基站仿真器: 从「仅 104 行 Mock」→ 增至 380 行 Mock + 630 行 UXM 驱动 + 727 行 CMW500 驱动 = 1737 行", "bl"),
        bullet("5 阶段编排引擎: commissioning_service.py (678行) 已验证全流程 Mock 运行通过", "bl"),
        bullet("信道生成双管线: ASC Pipeline 端到端验证，128 个 .asc 文件成功生成并落盘", "bl"),
        bullet("REAL_DRIVER_REGISTRY: 已注册 7 类仪器共 10 个真实驱动类", "bl"),

        heading("1.3 冲刺完成标准（Definition of Done）", HeadingLevel.HEADING_2),
        bullet("信道仿真器（Keysight PROPSIM F64）真实 SCPI 驱动通过双管线（GCM + ASC）冒烟测试", "bl2"),
        bullet("基站仿真器（UXM 或 CMW500）可通过 HAL 远程控制开启小区，DUT 成功 Attach", "bl2"),
        bullet("RF 开关矩阵（ETS-Lindgren EMCenter）的 Option B 端口映射从 GUI → DB → HAL 全链路贯通", "bl2"),
        bullet("完成 Level 0–4 全链路校准，校准数据写入数据库，ISO 证书 PDF 生成", "bl2"),
        bullet("5 阶段 Commissioning 编排引擎以 Real 模式完整执行（预检→参考测量→MIMO测试→分析→报告）", "bl2"),
        bullet("测试报告 PDF 包含 PDP、SCF、吞吐量 CDF 曲线和 TIS 门限判定", "bl2"),

        heading("1.4 标准参考依据", HeadingLevel.HEADING_2),
        bullet("3GPP TR 38.827 — MIMO OTA 测试方法论", "bl3"),
        bullet("3GPP TS 38.521-4 — NR UE 性能要求", "bl3"),
        bullet("CTIA MIMO OTA v1.2 — 测试计划与规程", "bl3"),
        bullet("3GPP TR 38.901 — 信道模型规范", "bl3"),

        // ======================== 2. 代码现状 ========================
        pb(),
        heading("2. 代码现状审计摘要 (截至 2026-04-19)"),
        para("以下矩阵展示本次冲刺涉及的核心模块的真实完成度，相比 v2.0 有显著进步："),

        new Table({
          columnWidths: [2400, 1500, 1200, 4260],
          rows: [
            new TableRow({ children: [
              hCell("模块", 2400), hCell("文件/代码量", 1500),
              hCell("完成度", 1200), hCell("冲刺剩余工作", 4260)
            ]}),
            new TableRow({ children: [
              dCell("HAL 基类 (base.py)", 2400, { run: { bold: true } }),
              dCell("159 行", 1500),
              dCell("100%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("无需改动。InstrumentDriver 抽象接口已完备。", 4260)
            ]}),
            new TableRow({ children: [
              dCell("信道仿真器 HAL", 2400, { run: { bold: true } }),
              dCell("516 + 1246 行", 1500),
              dCell("95%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("MockCE + RealPropsimF64Driver 双管线 SCPI 已完成; 需真实仪器 VISA 连通验证", 4260)
            ]}),
            new TableRow({ children: [
              dCell("基站仿真器 HAL", 2400, { run: { bold: true } }),
              dCell("380+630+727 行", 1500),
              dCell("75%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: Mock(380) + UXM(630) + CMW500(727) 三驱动全部就位; 需真实仪器 SCPI 调试", 4260, { shading: PROGRESS_FILL })
            ]}),
            new TableRow({ children: [
              dCell("信号分析仪 HAL", 2400, { run: { bold: true } }),
              dCell("91 行 + 2 Real", 1500),
              dCell("60%", 1200, { shading: WARN_FILL, run: { bold: true, color: "F57F17" } }),
              dCell("Mock 完成; Keysight X-Series + R&S FSW 真实驱动骨架已就位", 4260)
            ]}),
            new TableRow({ children: [
              dCell("RF 开关矩阵 HAL", 2400, { run: { bold: true } }),
              dCell("240 行", 1500),
              dCell("85%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: 从 0% → 85%。含抽象接口、Mock、ETS-Lindgren SCPI 驱动、Option B 端口映射, 安全联锁", 4260, { shading: PROGRESS_FILL })
            ]}),
            new TableRow({ children: [
              dCell("转台 HAL", 2400, { run: { bold: true } }),
              dCell("108 + 140 行", 1500),
              dCell("65%", 1200, { shading: WARN_FILL, run: { bold: true, color: "F57F17" } }),
              dCell("Mock(108) + ETS EMCenter Real(140) 骨架已就位; 静态测试可用 Mock 暂替", 4260)
            ]}),
            new TableRow({ children: [
              dCell("HAL 服务管理器", 2400, { run: { bold: true } }),
              dCell("616 行", 1500),
              dCell("95%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: REAL_DRIVER_REGISTRY 已注册 10 个真实驱动; connection_params 传递链路已修复", 4260, { shading: PROGRESS_FILL })
            ]}),
            new TableRow({ children: [
              dCell("5 阶段编排引擎", 2400, { run: { bold: true } }),
              dCell("678 行", 1500),
              dCell("90%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: Mock 全流程验证通过 (7/7在线, PASS); 需切换 Real 驱动后重跑", 4260, { shading: PROGRESS_FILL })
            ]}),
            new TableRow({ children: [
              dCell("校准系统 (11个服务)", 2400, { run: { bold: true } }),
              dCell("~380KB", 1500),
              dCell("95%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("编排器、6 级校准、依赖管理、ISO 证书全部完成; 需用真实测量数据替换 Mock", 4260)
            ]}),
            new TableRow({ children: [
              dCell("Channel Engine", 2400, { run: { bold: true } }),
              dCell("360 行", 1500),
              dCell("90%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: ASC Pipeline 已验证! 128 个 .asc 文件成功生成到 hardware_artifacts/", 4260, { shading: PROGRESS_FILL })
            ]}),
            new TableRow({ children: [
              dCell("前端 GUI", 2400, { run: { bold: true } }),
              dCell("5910 行 App.tsx", 1500),
              dCell("85%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("v3.0更新: Option B JsonInput 编辑器、connection_params 传递已添加; 仪器管理面板重构完成", 4260, { shading: PROGRESS_FILL })
            ]}),
          ]
        }),

        // ======================== 3. 今日开发成果 ========================
        pb(),
        heading("3. v3.0 新增章节: 2026-04-19 开发成果总结"),
        para([
          { text: "本章节是 v3.0 相比 v2.0 最核心的新增内容。", bold: true },
          { text: " 记录了 2026-04-19 的全天密集开发迭代，涵盖 HAL 驱动扩展、RF 开关集成、编排引擎调试和 Code Review 修复。" }
        ]),

        heading("3.1 RF Switch HAL 完整实现 (rf_switch.py, 240行)", HeadingLevel.HEADING_2),
        para("从零新建了 RF 开关矩阵的 HAL 驱动，采用三层架构:"),
        new Table({
          columnWidths: [2400, 2400, 4560],
          rows: [
            new TableRow({ children: [
              hCell("层级", 2400), hCell("类名", 2400), hCell("职责", 4560)
            ]}),
            new TableRow({ children: [
              dCell("抽象接口", 2400, { run: { bold: true } }),
              dCell("RfSwitchDriver", 2400),
              dCell("定义 switch_path(), get_path(), reset_paths(), set_mapped_path() 抽象方法; 基类维护 port_maps 字典", 4560)
            ]}),
            new TableRow({ children: [
              dCell("Mock 实现", 2400, { run: { bold: true } }),
              dCell("MockRfSwitch", 2400),
              dCell("内存态模拟, 用于无硬件环境下的全系统集成测试", 4560)
            ]}),
            new TableRow({ children: [
              dCell("真实驱动", 2400, { run: { bold: true } }),
              dCell("EtslSwitchDriver", 2400),
              dCell("ETS-Lindgren EMCenter TCP SCPI; 含安全联锁 (INTLK? SAFETYRELAY), 拓扑感知式 reset_paths()", 4560)
            ]}),
          ]
        }),

        heading("3.2 Option B 端口映射全链路", HeadingLevel.HEADING_2),
        para("实现了从前端 GUI 到 HAL 驱动的 connection_params 全链路数据流:"),
        bullet("前端: Mantine JsonInput 组件，内置 JSON 格式校验和格式化", "bl4"),
        bullet("API 类型: InstrumentConnection 类型增加 connection_params 字段", "bl4"),
        bullet("后端 Schema: FEConnectionUpdate + FEInstrumentConnection 同步增加字段", "bl4"),
        bullet("DB 持久化: connection_params JSON 列 → SQLite/PostgreSQL", "bl4"),
        bullet("HAL 注入: instrument_hal_service.py 构建 driver_config 时合并 connection_params", "bl4"),
        bullet("驱动消费: RfSwitchDriver.__init__() 从 config['port_maps'] 初始化映射表", "bl4"),
        gap(),
        para([
          { text: "端口映射 JSON 示例:", bold: true }
        ]),
        para('{ "port_maps": { "Probe_V_1": {"switch_id": "1:EXT_RELAY_A", "output_port": 1}, "Probe_H_1": {"switch_id": "1:INT_RELAY_B", "output_port": "NO"} } }', { run: { size: 20 } }),

        heading("3.3 5 阶段 Commissioning 编排引擎验证", HeadingLevel.HEADING_2),
        para("commissioning_service.py (678行) 是首测的核心编排器。今日验证了全 Mock 模式下的端到端执行:"),
        new Table({
          columnWidths: [1200, 2400, 2400, 3360],
          rows: [
            new TableRow({ children: [
              hCell("阶段", 1200), hCell("名称", 2400), hCell("今日验证结果", 2400), hCell("剩余工作", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 1", 1200, { run: { bold: true } }),
              dCell("系统预检", 2400),
              dCell("✓ PASS (7/7 在线)", 2400, { shading: DONE_FILL }),
              dCell("切换 Real 驱动后重跑", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 2", 1200, { run: { bold: true } }),
              dCell("参考天线基线测量", 2400),
              dCell("✓ TRP=23.5 dBm", 2400, { shading: DONE_FILL }),
              dCell("接入真实信号分析仪", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 3", 1200, { run: { bold: true } }),
              dCell("MIMO 吞吐量测试", 2400),
              dCell("✓ 4方位 128 ASC 文件", 2400, { shading: DONE_FILL }),
              dCell("真实 CE+BS 联调", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 4", 1200, { run: { bold: true } }),
              dCell("CTIA 分析判定", 2400),
              dCell("✓ PASS (裕量充足)", 2400, { shading: DONE_FILL }),
              dCell("用真实数据复验门限", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 5", 1200, { run: { bold: true } }),
              dCell("报告归档", 2400),
              dCell("✓ Report ID 生成", 2400, { shading: DONE_FILL }),
              dCell("PDF 模版完善", 3360)
            ]}),
          ]
        }),

        heading("3.4 Code Review 与 Bug 修复 (4 个 Bug)", HeadingLevel.HEADING_2),
        para("对全天代码进行了完整 Review，发现并修复了 4 个 Bug:"),
        new Table({
          columnWidths: [800, 3600, 2400, 2560],
          rows: [
            new TableRow({ children: [
              hCell("#", 800), hCell("Bug 描述", 3600), hCell("影响", 2400), hCell("修复方式", 2560)
            ]}),
            new TableRow({ children: [
              dCell("1", 800, { run: { bold: true } }),
              dCell("get_metrics() 缺少 timestamp — Pydantic ValidationError 崩溃", 3600),
              dCell("监控轮询 RF Switch 时崩溃", 2400, { shading: RISK_FILL }),
              dCell("添加 datetime.utcnow()", 2560, { shading: DONE_FILL })
            ]}),
            new TableRow({ children: [
              dCell("2", 800, { run: { bold: true } }),
              dCell("configure() 返回 None — super() 调用抽象方法 pass", 3600),
              dCell("上层逻辑误判配置失败", 2400, { shading: WARN_FILL }),
              dCell("改为 return True", 2560, { shading: DONE_FILL })
            ]}),
            new TableRow({ children: [
              dCell("3", 800, { run: { bold: true } }),
              dCell("connection_params 全链路断裂 — 前端写入后后端 Pydantic 静默丢弃", 3600),
              dCell("Option B 功能完全不可用", 2400, { shading: RISK_FILL }),
              dCell("修复 4 层 Schema", 2560, { shading: DONE_FILL })
            ]}),
            new TableRow({ children: [
              dCell("4", 800, { run: { bold: true } }),
              dCell("EtslSwitchDriver 未注册到 REAL_DRIVER_REGISTRY", 3600),
              dCell("Real 模式永远 fallback Mock", 2400, { shading: WARN_FILL }),
              dCell("添加注册条目", 2560, { shading: DONE_FILL })
            ]}),
          ]
        }),

        heading("3.5 ASC 文件产物验证", HeadingLevel.HEADING_2),
        para([
          { text: "关键验证: ", bold: true },
          { text: "Channel Engine (端口 8001) 在 ASC 模式下成功对 16 探头暗室（双极化 = 32 通道、2 TX = 64 条输出）生成了完整的 .asc 波形文件包。" },
        ]),
        bullet("存放路径: api-service/app/data/hardware_artifacts/{session_id}/", "bl5"),
        bullet("文件命名: channel_In{tx}_Out{probe}.asc (例 channel_In1_Out32.asc)", "bl5"),
        bullet("文件数量: 128 个 (2 输入 × 64 输出)", "bl5"),
        bullet("单文件大小: ~3.5 KB (F64 ASCII 格式)", "bl5"),
        bullet("GCM 原生模式: 运行速度远快于 ASC 模式（跳过 CE HTTP 调用和 ZIP 解压）", "bl5"),

        // ======================== 4. 冲刺架构 ========================
        pb(),
        heading("4. 冲刺阶段架构 (v3.0 更新)"),
        para("v3.0 将 Phase 0/0.5 标记为已完成，Phase 1 从 3 天压缩至 2 天:"),
        new Table({
          columnWidths: [1200, 3600, 1200, 3360],
          rows: [
            new TableRow({ children: [
              hCell("阶段", 1200), hCell("内容", 3600),
              hCell("工期", 1200), hCell("关键交付物", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 0", 1200, { run: { bold: true, color: "2E7D32" } }),
              dCell("✓ 硬件清点与环境准备 (已完成)", 3600, { shading: DONE_FILL }),
              dCell("Day 0", 1200),
              dCell("仪器注册、VISA 连通性验证、.env 配置", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 0.5", 1200, { run: { bold: true, color: "2E7D32" } }),
              dCell("✓ 代码适配层准备 (已完成)", 3600, { shading: DONE_FILL }),
              dCell("Day 0", 1200),
              dCell("RF Switch HAL、DRIVER_REGISTRY 更新、Option B 全链路", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 1", 1200, { run: { bold: true } }),
              dCell("HAL 真实驱动调试 (从编写→调试)", 3600),
              dCell("Day 1–2", 1200),
              dCell("F64/UXM/CMW500 Real 驱动 VISA 冒烟测试通过", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 2", 1200, { run: { bold: true } }),
              dCell("暗室全链路校准", 3600),
              dCell("Day 3–7", 1200),
              dCell("6 级校准完成、ISO 证书 PDF 生成", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 3", 1200, { run: { bold: true } }),
              dCell("CDL 信道加载与首次 E2E 测试", 3600),
              dCell("Day 8–13", 1200),
              dCell("CDL-A/C 信道验证、TIS 曲线", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 4", 1200, { run: { bold: true } }),
              dCell("合规测试与报告生成", 3600),
              dCell("Day 14–18", 1200),
              dCell("完整测试报告 PDF、DoD 验收", 3360)
            ]}),
          ]
        }),

        // ======================== 5. Phase 1 ========================
        pb(),
        heading("5. Phase 1 — HAL 真实驱动调试（Day 1–2）"),
        para([
          { text: "v3.0 调整说明: ", bold: true },
          { text: "v2.0 安排 3 天进行 HAL 开发。实际驱动代码骨架已全部就位（F64 1246行、UXM 630行、CMW500 727行），Phase 1 任务从「编写代码」变为「真实仪器 SCPI 验证」。压缩至 2 天。" }
        ]),

        heading("5.1 Day 1: 信道仿真器 + 基站仿真器验证", HeadingLevel.HEADING_2),
        heading("F64 双管线验证 (propsim_f64.py, 1246行已完成)", HeadingLevel.HEADING_3),
        bullet("Pipeline A (GCM): 加载标准 CDL-A .smu → CALC:FILT:FILE + *OPC? 正常返回", "bl6"),
        bullet("Pipeline B (ASC): FTP 上传 .asc → D:\\User Emulations\\ASC → CH:MOD:CONT:ENV 播放", "bl6"),
        bullet("校准旁路: DIAG:SIMU:MODEL:STATIC 3 验证所有通道等增益等延迟", "bl6"),
        bullet("RSRP 测量: INP:RSRP:MEAS? 验证返回值合理性", "bl6"),
        gap(),
        heading("基站仿真器验证 (UXM 630行 / CMW500 727行已完成)", HeadingLevel.HEADING_3),
        para("根据暗室实际型号选择 UXM 或 CMW500 驱动进行验证:"),
        new Table({
          columnWidths: [3200, 3200, 2960],
          rows: [
            new TableRow({ children: [
              hCell("HAL 原语", 3200), hCell("业务含义", 3200), hCell("验证项", 2960)
            ]}),
            new TableRow({ children: [
              dCell("set_cell_config()", 3200),
              dCell("配置 NR n78 小区", 3200),
              dCell("3.5 GHz, 100 MHz, 30 kHz SCS", 2960)
            ]}),
            new TableRow({ children: [
              dCell("start_signaling()", 3200),
              dCell("开启信令等待 DUT Attach", 3200),
              dCell("超时 60s, 状态轮询间隔 2s", 2960)
            ]}),
            new TableRow({ children: [
              dCell("get_throughput_metrics()", 3200),
              dCell("轮询 MAC 吞吐量 + BLER + CQI", 3200),
              dCell("返回值非零且在合理范围", 2960)
            ]}),
            new TableRow({ children: [
              dCell("set_downlink_power()", 3200),
              dCell("调节下行发射功率", 3200),
              dCell("-50 ~ 0 dBm 步进验证", 2960)
            ]}),
          ]
        }),

        heading("5.2 Day 2: 信号分析仪 + RF 开关 + 集成冒烟测试", HeadingLevel.HEADING_2),
        bullet("信号分析仪: Keysight N9020B 或 R&S FSW → setup_spectrum() + measure_channel_power()", "bl7"),
        bullet("RF 开关: ETS-Lindgren EMCenter → TCP 连接 + INTLK? 安全联锁 + set_mapped_path() 验证", "bl7"),
        bullet("VNA: Keysight E5071C ENA → 如有时间验证 S21 测量", "bl7"),
        gap(),
        heading("Day 2 下午: 全仪器集成冒烟测试", HeadingLevel.HEADING_3),
        bullet("switch_hal_mode(DriverMode.REAL) → 观察驱动工厂日志", "bl8"),
        bullet("Commissioning Phase 1 预检: /commissioning/sessions/{id}/phase/precheck → 7/7 在线", "bl8"),
        bullet("GUI 仪表板切换 Real 模式 → 仪器在线状态显示绿色", "bl8"),
        bullet("验证降级: 断开一台仪器 → 自动 fallback Mock → 告警触发", "bl8"),

        // ======================== 6. Phase 2 ========================
        pb(),
        heading("6. Phase 2 — 暗室全链路校准（Day 3–7）"),
        para([
          { text: "校准系统软件已完成 95%（11 个服务，~380KB）。", bold: true },
          { text: " 本阶段任务是将 Mock 测量数据替换为真实仪器数据。" }
        ]),
        new Table({
          columnWidths: [900, 2100, 2400, 3960],
          rows: [
            new TableRow({ children: [
              hCell("Day", 900), hCell("校准级别", 2100),
              hCell("使用仪器", 2400), hCell("验收标准", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 3", 900, { run: { bold: true } }),
              dCell("Level 0: 探头单元校准", 2100),
              dCell("VNA + RF 开关矩阵", 2400),
              dCell("全探头 S11 幅度/相位/极化测量完成, 与标称差值 < 0.5 dB", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 4", 900, { run: { bold: true } }),
              dCell("Level 1: 路损校准", 2100),
              dCell("VNA + RF 开关矩阵", 2400),
              dCell("SGH→每个探头 S21 插入损耗扫描 (3.5 GHz ± 100 MHz), 补偿矩阵入库", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 4", 900, { run: { bold: true } }),
              dCell("Level 2: RF 链路校准", 2100),
              dCell("VNA + 信号分析仪", 2400),
              dCell("LNA/PA/双工器增益/噪声系数测量, 链路不一致度 < 1 dB", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 5", 900, { run: { bold: true } }),
              dCell("Level 3: 端到端校准", 2100),
              dCell("信道仿真器 + SA", 2400),
              dCell("E2E 补偿矩阵生成, 所有通道幅相误差 < 2 dB / 5°", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 6", 900, { run: { bold: true } }),
              dCell("Level 4: 信道校准", 2100),
              dCell("信道仿真器 + VNA", 2400),
              dCell("PDP 与 CDL-A 目标值匹配 (< 1 ns RMS), SCF 满足 TR 38.827 §6.4", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 7", 900, { run: { bold: true } }),
              dCell("Level 5: 系统验证", 2100),
              dCell("基站仿真器 + SA", 2400),
              dCell("TRP/TIS 基准测量, 静区场均匀性 < 1 dB (CTIA), ISO 校准证书 PDF", 3960)
            ]}),
          ]
        }),
        gap(),
        para([
          { text: "Day 7 是关键里程碑: ", bold: true, color: "C62828" },
          { text: "校准证书生成代表硬件链路完整可信。若任一级校准不通过，不得进入 Phase 3。" }
        ]),

        // ======================== 7. Phase 3 ========================
        pb(),
        heading("7. Phase 3 — CDL 信道加载与首次 E2E 测试（Day 8–13）"),
        heading("7.1 Day 8–9: CDL 信道模型加载", HeadingLevel.HEADING_2),
        new Table({
          columnWidths: [1800, 2400, 2400, 2760],
          rows: [
            new TableRow({ children: [
              hCell("信道模型", 1800), hCell("场景类型", 2400),
              hCell("MIMO 配置", 2400), hCell("验证参数", 2760)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }),
              dCell("UMi NLOS (散射丰富)", 2400),
              dCell("2×2 MIMO", 2400),
              dCell("PDP, SCF, XPO", 2760)
            ]}),
            new TableRow({ children: [
              dCell("CDL-C", 1800, { run: { bold: true } }),
              dCell("UMa NLOS (宏小区)", 2400),
              dCell("2×2 MIMO", 2400),
              dCell("PDP, SCF, AS 偏差 < 10%", 2760)
            ]}),
          ]
        }),
        gap(),
        para([
          { text: "v3.0 已验证的信道生成路径: ", bold: true },
          { text: "Channel Engine (8001) → ASC ZIP (base64) → API Service 解压 → hardware_artifacts/{session_id}/ → HAL load_channel(EXTERNAL_WAVEFORM) → F64 播放。128 个文件已成功生成。" }
        ]),

        heading("7.2 Day 10: 系统集成预检", HeadingLevel.HEADING_2),
        bullet("DUT 放置于静区，确认基站信令建立（DUT Attach + 连接态）", "bl9"),
        bullet("手动功率扫描 -20 → -80 dBm，确认 DUT 吞吐量随功率下降", "bl9"),
        bullet("GUI 实时监控页面吞吐量曲线正常刷新（WebSocket + KPI 卡片）", "bl9"),

        heading("7.3 Day 11–13: 首次完整 E2E 吞吐量测试", HeadingLevel.HEADING_2),
        para("使用 Commissioning 5 阶段编排引擎执行，前端点击「开始执行」即全自动运行:"),
        new Table({
          columnWidths: [800, 2800, 5760],
          rows: [
            new TableRow({ children: [
              hCell("步骤", 800), hCell("操作", 2800), hCell("技术参数", 5760)
            ]}),
            new TableRow({ children: [
              dCell("1", 800, { run: { bold: true } }), dCell("系统预检", 2800),
              dCell("HAL 连通性 7/7 → 校准有效性 → 静区 ripple ≤ ±1.0 dB", 5760)
            ]}),
            new TableRow({ children: [
              dCell("2", 800, { run: { bold: true } }), dCell("参考天线基线", 2800),
              dCell("SGH-3500 安装 → TRP 测量 → 补偿因子计算", 5760)
            ]}),
            new TableRow({ children: [
              dCell("3", 800, { run: { bold: true } }), dCell("MIMO 吞吐量测试", 2800),
              dCell("CDL-A → ASC/GCM 加载 → 4方位×20采样 → RSRP/SINR/Tput/RI 记录", 5760)
            ]}),
            new TableRow({ children: [
              dCell("4", 800, { run: { bold: true } }), dCell("CTIA 分析判定", 2800),
              dCell("吞吐量比 ≥ 70% 峰值, RSRP 方差 ≤ 3 dB, SINR ≥ 15 dB, RI ≥ 1.5", 5760)
            ]}),
            new TableRow({ children: [
              dCell("5", 800, { run: { bold: true } }), dCell("报告归档", 2800),
              dCell("PDF 生成 + 数据库写入 + report_id 返回", 5760)
            ]}),
          ]
        }),

        heading("7.4 ASC 文件产物管理与验证规程 (v3.0 新增)", HeadingLevel.HEADING_2),
        para([
          { text: "本节是 v3.0 新增的关键操作规程，", bold: true },
          { text: "基于今天的实际验证经验 (128 个 .asc 文件的生成与落盘) 编制。" }
        ]),
        bullet("产物路径: api-service/app/data/hardware_artifacts/{session_id}/", "bla"),
        bullet("命名规则: channel_In{tx}_Out{probe}.asc, tx=1..N_TX, probe=1..N_PROBE×N_POL", "bla"),
        bullet("文件校验: 每个文件应为 F64 可识别的 ASCII 文本, 含频点/衰减/相位列", "bla"),
        bullet("版本追溯: 目录名为 session_id 前 8 位 UUID, 与 Commissioning 会话一一对应", "bla"),
        bullet("清理策略: 过期产物按 7 天自动清理 (待实现)，或手动 rm -rf", "bla"),

        // ======================== 8. Phase 4 ========================
        pb(),
        heading("8. Phase 4 — 合规测试与报告生成（Day 14–18）"),
        heading("8.1 Day 14–15: 多场景合规扫描", HeadingLevel.HEADING_2),
        new Table({
          columnWidths: [1800, 2100, 2100, 3360],
          rows: [
            new TableRow({ children: [
              hCell("CDL 场景", 1800), hCell("频段", 2100),
              hCell("MIMO 配置", 2100), hCell("优先级说明", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }), dCell("n78 (3.5 GHz)", 2100),
              dCell("2×2", 2100), dCell("首测已完成, Day 14 复验", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-C", 1800, { run: { bold: true } }), dCell("n78 (3.5 GHz)", 2100),
              dCell("2×2", 2100), dCell("首测已完成, Day 14 复验", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-D (LOS)", 1800, { run: { bold: true } }), dCell("n78 (3.5 GHz)", 2100),
              dCell("2×2", 2100), dCell("新增 LOS 场景 (K 因子 ≠ 0)", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }), dCell("n41 (2.5 GHz)", 2100),
              dCell("2×2", 2100), dCell("频段扩展, 可选", 3360)
            ]}),
          ]
        }),

        heading("8.2 Day 16: Pass/Fail 判定系统完善", HeadingLevel.HEADING_2),
        bullet("报告系统 (已有 66KB pdf_generator.py) 增加 TIS 门限自动判定", "blb"),
        bullet("吞吐量 CDF 曲线图 (CTIA v1.2 §5.3)", "blb"),
        bullet("PDP/SCF 验证图 (TR 38.827 §6.4 强制要求)", "blb"),

        heading("8.3 Day 17–18: 最终报告与验收", HeadingLevel.HEADING_2),
        bullet("完整 PDF 报告: 封面、配置、校准证书、各场景结果、Pass/Fail 汇总", "blc"),
        bullet("仪器驱动交接文档: 各型号 SCPI 地址、关键指令清单", "blc"),
        bullet("团队评审: 确认所有 DoD 条件满足", "blc"),

        // ======================== 9. 风险 ========================
        pb(),
        heading("9. 关键路径分析与风险管控"),
        heading("9.1 关键路径 (v3.0 更新)", HeadingLevel.HEADING_2),
        para([
          { text: "F64 VISA 验证 (Day 1) → 基站 SCPI 调试 (Day 1) → Level 4 信道校准 (Day 6) → 首次 E2E 测试 (Day 11)", bold: true }
        ]),
        para([
          { text: "v3.0 调整: ", bold: true },
          { text: "关键路径从 v2.0 的「编写驱动代码」变为「调试已有驱动的 SCPI 响应」。所有驱动骨架已完成，风险集中在仪器端固件兼容性和 SCPI 文档准确性。" }
        ]),

        heading("9.2 风险登记册 (v3.0 更新)", HeadingLevel.HEADING_2),
        new Table({
          columnWidths: [3000, 800, 800, 4760],
          rows: [
            new TableRow({ children: [
              hCell("风险描述", 3000), hCell("概率", 800),
              hCell("影响", 800), hCell("缓解措施", 4760)
            ]}),
            new TableRow({ children: [
              dCell("F64 固件版本不兼容, SCPI 响应格式异常", 3000),
              dCell("高", 800, { shading: RISK_FILL }),
              dCell("1–2 天", 800),
              dCell("已有 1246 行驱动可逐条验证; pyvisa 手动探查; AI 辅助解析 Programming Manual", 4760)
            ]}),
            new TableRow({ children: [
              dCell("基站仿真器采用私有 REST API 而非 SCPI", 3000),
              dCell("低", 800, { shading: ACCENT_FILL }),
              dCell("1 天", 800),
              dCell("v3.0 降级: UXM 和 CMW500 驱动均已完成, 涵盖 Keysight 和 R&S 两大主流厂商", 4760)
            ]}),
            new TableRow({ children: [
              dCell("RF 开关矩阵 INTLK 安全联锁误触发", 3000),
              dCell("中", 800, { shading: WARN_FILL }),
              dCell("0.5 天", 800),
              dCell("v3.0 新增: 已实现 INTLK? SAFETYRELAY 查询; connect() 时自动检查并阻断", 4760)
            ]}),
            new TableRow({ children: [
              dCell("DUT 首次 E2E 无法 Attach (信令故障)", 3000),
              dCell("中", 800, { shading: WARN_FILL }),
              dCell("2 天", 800),
              dCell("提前传导模式验证 DUT; 检查静区功率电平", 4760)
            ]}),
            new TableRow({ children: [
              dCell("Axios 前端超时 (Phase 3 执行 > 30s)", 3000),
              dCell("低", 800, { shading: ACCENT_FILL }),
              dCell("0 天", 800),
              dCell("v3.0 已修复: client.ts timeout 30s → 300s; 后续改轮询", 4760)
            ]}),
          ]
        }),

        heading("9.3 已修复的技术债务 (v3.0 新增)", HeadingLevel.HEADING_2),
        para("以下问题在 v2.0 阶段尚未意识到，在实际开发中暴露并已修复:"),
        bullet("MockChannelEmulator 5% 随机连接失败 — 导致预检不稳定 (已移除)", "bld"),
        bullet("connection_params 全链路 4 层断裂 — 前端写入后后端静默丢弃 (已修复)", "bld"),
        bullet("get_metrics() 缺少 timestamp — Pydantic 验证崩溃 (已修复)", "bld"),
        bullet("super().configure() 返回 None — 抽象方法 pass 的陷阱 (已修复)", "bld"),
        
        heading("9.4 待解决的技术债务 (v3.0 记录)", HeadingLevel.HEADING_2),
        para("以下问题是在重新审视系统协议层控制架构时发现的缺失，已列入风险并在后续修复:"),
        bullet("基站协议层参数自动化加载缺失: 目前 UXM/CMW500 HAL 未实现 3GPP FRC、TDD Slot Pattern 或 RB 分配等核心协议参数的文件级调入。当前采用降级方案：由测试工程师在基站本地手动载入 State/Test Model 并调用。自动化协议全栈配置留待 Phase B 解决。", "bld2"),

        // ======================== 10. 人力 ========================
        pb(),
        heading("10. 人力分工建议"),
        new Table({
          columnWidths: [2100, 1800, 5460],
          rows: [
            new TableRow({ children: [
              hCell("角色", 2100), hCell("主要阶段", 1800), hCell("具体职责", 5460)
            ]}),
            new TableRow({ children: [
              dCell("硬件驱动工程师", 2100, { run: { bold: true } }),
              dCell("Phase 1", 1800),
              dCell("基于已完成的驱动骨架, 在真实仪器上逐条调试 SCPI; 补全 VISA 连接; 编写交接文档", 5460)
            ]}),
            new TableRow({ children: [
              dCell("测试/RF 工程师", 2100, { run: { bold: true } }),
              dCell("Phase 2–3", 1800),
              dCell("执行全链路校准; 配置 CDL 参数; 完成 E2E 测试; 确认 Option B 端口映射", 5460)
            ]}),
            new TableRow({ children: [
              dCell("后端工程师", 2100, { run: { bold: true } }),
              dCell("Phase 1–4", 1800),
              dCell("HAL 集成测试; 校准服务 use_mock→False; TIS 门限 API; DRIVER_REGISTRY 维护", 5460)
            ]}),
            new TableRow({ children: [
              dCell("前端工程师", 2100, { run: { bold: true } }),
              dCell("Phase 1, 4", 1800),
              dCell("仪器在线状态验证; 报告图表验证; RF Switch 端口映射可视化编辑器 (Phase 4)", 5460)
            ]}),
          ]
        }),

        // ======================== 11. 里程碑 ========================
        pb(),
        heading("11. 每日里程碑检查点"),
        new Table({
          columnWidths: [800, 1200, 4200, 3160],
          rows: [
            new TableRow({ children: [
              hCell("Day", 800), hCell("阶段", 1200),
              hCell("当日完成标准", 4200), hCell("阻断条件", 3160)
            ]}),
            new TableRow({ children: [
              dCell("1", 800, { run: { bold: true } }), dCell("Phase 1", 1200),
              dCell("F64 可远程加载 CDL-A 并启动仿真; 基站仿真器小区开启, DUT Attach", 4200),
              dCell("SCPI 无响应 → 换备用仪器", 3160)
            ]}),
            new TableRow({ children: [
              dCell("2", 800, { run: { bold: true } }), dCell("Phase 1", 1200),
              dCell("信号分析仪 + RF 开关冒烟通过; 全仪器 Real 模式集成测试通过", 4200),
              dCell("任一驱动失败 → 不进入 Phase 2", 3160)
            ]}),
            new TableRow({ children: [
              dCell("5", 800, { run: { bold: true } }), dCell("Phase 2", 1200),
              dCell("Level 0–3 校准完成, 补偿矩阵入库", 4200),
              dCell("通道幅相误差超标 → 检查物理连接", 3160)
            ]}),
            new TableRow({ children: [
              dCell("7", 800, { run: { bold: true } }), dCell("Phase 2", 1200),
              dCell("Level 4–5 校准通过, ISO 校准证书 PDF 生成", 4200),
              dCell("PDP/SCF 偏差 > 10% → 不进入 Phase 3", 3160)
            ]}),
            new TableRow({ children: [
              dCell("10", 800, { run: { bold: true } }), dCell("Phase 3", 1200),
              dCell("DUT 吞吐量随功率正常变化 (功能验证通过)", 4200),
              dCell("吞吐量不变 → 排查链路增益和 FRC", 3160)
            ]}),
            new TableRow({ children: [
              dCell("13", 800, { run: { bold: true } }), dCell("Phase 3", 1200),
              dCell("CDL-A 和 CDL-C 场景 TIS 曲线绘制完成", 4200),
              dCell("TIS 异常 → 复查信道权重和路损", 3160)
            ]}),
            new TableRow({ children: [
              dCell("18", 800, { run: { bold: true } }), dCell("Phase 4", 1200),
              dCell("完整测试报告 PDF 生成, 所有 DoD 条件满足", 4200),
              dCell("—— 冲刺终点 ——", 3160)
            ]}),
          ]
        }),

        // ======================== 12. 后续 ========================
        pb(),
        heading("12. 冲刺后续路线图"),
        new Table({
          columnWidths: [2100, 1800, 5460],
          rows: [
            new TableRow({ children: [
              hCell("阶段", 2100), hCell("时间", 1800), hCell("工作内容", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase A 代码治理", 2100, { run: { bold: true } }),
              dCell("冲刺后 2 周", 1800),
              dCell("App.tsx 拆分; PostgreSQL 迁移; Docker 容器化; RF Switch 可视化编辑器 (替代 JsonInput)", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase B 动态信道", 2100, { run: { bold: true } }),
              dCell("4–6 周", 1800),
              dCell("动态 CDL 时变信道 (TR 38.762 路点插值); VRT 虚拟路测模块接入真实仪器", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase C RT-OTA", 2100, { run: { bold: true } }),
              dCell("8–12 周", 1800),
              dCell("接入 RT 射线追踪引擎; CCSA RT-OTA 数字孪生验证; K-S 合规检验", 5460)
            ]}),
          ]
        }),

        // ======================== 附录 ========================
        pb(),
        heading("附录 A: 当前 HAL 代码清单 (18 文件, 5166 行)"),
        new Table({
          columnWidths: [4800, 1000, 1200, 2360],
          rows: [
            new TableRow({ children: [
              hCell("文件路径", 4800), hCell("行数", 1000),
              hCell("状态", 1200), hCell("说明", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/base.py", 4800), dCell("159", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("抽象基类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/channel_emulator.py", 4800), dCell("516", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("Mock + 抽象类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/propsim_f64.py", 4800), dCell("1246", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("F64 双管线 SCPI", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/base_station.py", 4800), dCell("380", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("Mock + 抽象类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/uxm_base_station.py", 4800), dCell("630", 1000),
              dCell("骨架完成", 1200, { shading: PROGRESS_FILL }), dCell("Keysight UXM 5G", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/cmw500_base_station.py", 4800), dCell("727", 1000),
              dCell("骨架完成", 1200, { shading: PROGRESS_FILL }), dCell("R&S CMW500", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/signal_analyzer.py", 4800), dCell("91", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("Mock + 抽象类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/rf_switch.py", 4800), dCell("240", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("v3.0 新增! Mock + ETS-L", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/positioner.py", 4800), dCell("108", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("Mock + 抽象类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/ets_positioner.py", 4800), dCell("140", 1000),
              dCell("骨架完成", 1200, { shading: PROGRESS_FILL }), dCell("ETS EMCenter Real", 2360)
            ]}),
            new TableRow({ children: [
              dCell("hal/vna.py", 4800), dCell("~100", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("Mock + 抽象类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("services/instrument_hal_service.py", 4800), dCell("616", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("驱动工厂 + 10 real drivers", 2360)
            ]}),
            new TableRow({ children: [
              dCell("services/commissioning_service.py", 4800), dCell("678", 1000),
              dCell("完成", 1200, { shading: DONE_FILL }), dCell("5 阶段编排引擎", 2360)
            ]}),
          ]
        }),

        gap(), gap(),
        new Paragraph({
          alignment: AlignmentType.CENTER, spacing: { before: 200 },
          children: [new TextRun({ text: "— 文档结束 —", size: 22, color: "999999", font: "Arial", italics: true })]
        }),
      ]
    }
  ]
});

const outputPath = "/Users/Simon/Tools/MIMO-First/docs/产品特性/静态MIMO-OTA冲刺计划_3-4周_v3.0.docx";
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log("SUCCESS: " + outputPath);
}).catch(err => {
  console.error("FAILED:", err.message);
  process.exit(1);
});
