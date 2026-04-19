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

// ==================== 文档内容 ====================
const bulletConfigs = [
  { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl2", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl3", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl4", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl5", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl6", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl7", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl8", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bl9", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "bla", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "blb", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  { reference: "blc", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
];

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
    // ======================== 封面 ========================
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
        gap(), gap(), gap(), gap(), gap(),
        new Paragraph({
          alignment: AlignmentType.CENTER, spacing: { after: 100 },
          children: [new TextRun({ text: "Meta-3D MIMO OTA 测试系统", size: 36, color: "666666", font: "Arial" })]
        }),
        new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("静态 MIMO-OTA 冲刺计划")] }),
        new Paragraph({
          alignment: AlignmentType.CENTER, spacing: { before: 80, after: 400 },
          children: [new TextRun({ text: "v2.0 — 融合代码现状的精确执行方案", size: 28, color: "2E5984", font: "Arial", italics: true })]
        }),
        gap(),
        new Table({
          columnWidths: [3000, 6360],
          rows: [
            new TableRow({ children: [
              dCell("文档版本", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("v2.0", 6360)
            ]}),
            new TableRow({ children: [
              dCell("编制日期", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("2026-04-19", 6360)
            ]}),
            new TableRow({ children: [
              dCell("基准代码", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("main 分支 @ 2026-04-19 (App.tsx 5832行, HAL 7文件, 校准服务 11个)", 6360)
            ]}),
            new TableRow({ children: [
              dCell("计划时长", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("18 个工作日（约 3.5 周）", 6360)
            ]}),
            new TableRow({ children: [
              dCell("前序文档", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("静态MIMO-OTA冲刺计划 v1.0", 6360)
            ]}),
            new TableRow({ children: [
              dCell("变更说明", 3000, { shading: SUB_HEADER_FILL, run: { bold: true } }),
              dCell("基于 v1.0 全面审计代码现状后重构，明确已完成/待完成边界", 6360)
            ]}),
          ]
        }),

        // ======================== 1. 概述 ========================
        pb(),
        heading("1. 概述与目标"),
        heading("1.1 冲刺定位", HeadingLevel.HEADING_2),
        para("本冲刺是 MIMO-First 项目从「软件仿真平台」向「真实硬件测试系统」跨越的关键里程碑。冲刺结束后，系统将具备在物理暗室中完成一次完整的静态 MIMO OTA 吞吐量测试的能力，并自动生成符合 3GPP/CTIA 规范的测试报告。"),

        heading("1.2 v2.0 与 v1.0 的核心差异", HeadingLevel.HEADING_2),
        para([
          { text: "v1.0 的制定未充分考虑已有代码资产。", bold: true },
          { text: " 本 v2.0 基于对当前代码仓库的逐文件审计，精确识别了每个模块的完成度，将工作量聚焦在「最后一公里」——真实 SCPI 驱动编写与真实测量数据灌入。以下是关键差异：" }
        ]),
        bullet("HAL 层：v1.0 假设从零开始；实际已有完整的三层架构（InstrumentDriver → TypeDriver → RealModelDriver），含 7 个驱动文件和 F64 真实驱动原型", "bl"),
        bullet("校准系统：v1.0 假设校准软件需大量开发；实际 11 个校准服务已完成（共 ~380KB 代码），含编排器、依赖管理、ISO 证书生成", "bl"),
        bullet("前端 GUI：v1.0 未提及已有的校准向导、测试计划管理、OTA 映射器等完整 UI 组件群", "bl"),
        bullet("仪器注册：v1.0 未提及数据库中已有的 InstrumentCategory/Model/Connection 三表体系和驱动工厂模式", "bl"),

        heading("1.3 冲刺完成标准（Definition of Done）", HeadingLevel.HEADING_2),
        bullet("信道仿真器（Keysight PROPSIM F64）、基站仿真器的 Real HAL 驱动可通过 VISA/SCPI 正常控制仪器", "bl2"),
        bullet("完成 Level 0–4 全链路校准（路损 + RF 链路 + 端到端 + 信道校准），校准数据写入 SQLite 数据库", "bl2"),
        bullet("成功加载至少 2 种 3GPP CDL 信道模型（CDL-A 和 CDL-C），信道参数验证通过", "bl2"),
        bullet("完成至少一次端到端 MIMO OTA 吞吐量测试（2×2 MIMO，NR FRC，吞吐量 vs 功率曲线）", "bl2"),
        bullet("测试报告 PDF 包含 PDP、SCF、吞吐量 CDF 曲线和 TIS 门限判定", "bl2"),

        heading("1.4 标准参考依据", HeadingLevel.HEADING_2),
        bullet("3GPP TR 38.827 — MIMO OTA 测试方法论", "bl3"),
        bullet("3GPP TS 38.521-4 — NR UE 性能要求", "bl3"),
        bullet("CTIA MIMO OTA v1.2 — 测试计划与规程", "bl3"),
        bullet("3GPP TR 38.901 — 信道模型规范", "bl3"),

        // ======================== 2. 代码现状审计 ========================
        pb(),
        heading("2. 代码现状审计摘要"),
        para("以下矩阵展示本次冲刺涉及的核心模块的真实完成度（截至 2026-04-19）："),

        new Table({
          columnWidths: [2400, 1500, 1200, 4260],
          rows: [
            new TableRow({ children: [
              hCell("模块", 2400), hCell("文件/代码量", 1500),
              hCell("完成度", 1200), hCell("冲刺工作", 4260)
            ]}),
            // HAL Base
            new TableRow({ children: [
              dCell("HAL 基类 (base.py)", 2400, { run: { bold: true } }),
              dCell("160 行", 1500),
              dCell("100%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("无需改动。InstrumentDriver 抽象接口已完备。", 4260)
            ]}),
            // Channel Emulator
            new TableRow({ children: [
              dCell("信道仿真器 HAL", 2400, { run: { bold: true } }),
              dCell("407 + 1198 行", 1500),
              dCell("95%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("MockChannelEmulator + RealPropsimF64Driver 双管线 SCPI 翻译已完成; 需真实仪器验证", 4260)
            ]}),
            // Base Station
            new TableRow({ children: [
              dCell("基站仿真器 HAL", 2400, { run: { bold: true } }),
              dCell("104 行", 1500),
              dCell("40%", 1200, { shading: WARN_FILL, run: { bold: true, color: "F57F17" } }),
              dCell("MockBaseStation 完成; 需编写 RealBaseStationDriver（SCPI 或 REST）", 4260)
            ]}),
            // Signal Analyzer
            new TableRow({ children: [
              dCell("信号分析仪 HAL", 2400, { run: { bold: true } }),
              dCell("121 行", 1500),
              dCell("40%", 1200, { shading: WARN_FILL, run: { bold: true, color: "F57F17" } }),
              dCell("MockSignalAnalyzer 完成; 需编写 RealSignalAnalyzerDriver", 4260)
            ]}),
            // RF Switch
            new TableRow({ children: [
              dCell("RF 开关矩阵 HAL", 2400, { run: { bold: true } }),
              dCell("0 行", 1500),
              dCell("0%", 1200, { shading: RISK_FILL, run: { bold: true, color: "C62828" } }),
              dCell("需新建 rf_switch.py：RFSwitchDriver 抽象接口 + RealRFSwitchDriver", 4260)
            ]}),
            // Positioner
            new TableRow({ children: [
              dCell("转台 HAL", 2400, { run: { bold: true } }),
              dCell("101 行", 1500),
              dCell("50%", 1200, { shading: WARN_FILL, run: { bold: true, color: "F57F17" } }),
              dCell("MockPositioner 完成; 静态测试暂不需要真实驱动", 4260)
            ]}),
            // HAL Service
            new TableRow({ children: [
              dCell("HAL 服务管理器", 2400, { run: { bold: true } }),
              dCell("620 行", 1500),
              dCell("90%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("Mock/Real 切换、驱动工厂、指标缓存已完成; 需注册新 Real 驱动到 DRIVER_REGISTRY", 4260)
            ]}),
            // Calibration
            new TableRow({ children: [
              dCell("校准系统 (11个服务)", 2400, { run: { bold: true } }),
              dCell("~380KB", 1500),
              dCell("95%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("编排器、6 级校准、依赖管理、ISO 证书全部完成; 需用真实测量数据替换 Mock 数据", 4260)
            ]}),
            // Channel Engine
            new TableRow({ children: [
              dCell("Channel Engine 服务", 2400, { run: { bold: true } }),
              dCell("360 行", 1500),
              dCell("85%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("探头权重计算、CDL 模型集成已完成; 需验证真实 ASC 文件生成与下发", 4260)
            ]}),
            // GUI
            new TableRow({ children: [
              dCell("前端 GUI", 2400, { run: { bold: true } }),
              dCell("5832 行 App.tsx", 1500),
              dCell("80%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("校准向导、仪器面板、报告系统已完成; 需增加真实仪器状态指示和 TIS 结果展示", 4260)
            ]}),
            // Report
            new TableRow({ children: [
              dCell("报告系统", 2400, { run: { bold: true } }),
              dCell("~66KB", 1500),
              dCell("85%", 1200, { shading: DONE_FILL, run: { bold: true, color: "2E7D32" } }),
              dCell("PDF 生成、图表渲染已完成; 需增加 TIS 门限判定和 CDF 曲线", 4260)
            ]}),
          ]
        }),

        // ======================== 3. 冲刺架构 ========================
        pb(),
        heading("3. 冲刺整体架构"),
        para("本冲刺分为 5 个阶段，总时长约 18 个工作日（3.5 周）。各阶段串行依赖，后阶段以前阶段输出为前提。"),
        para([
          { text: "与 v1.0 的关键调整：", bold: true },
          { text: " 新增 Phase 0.5（代码适配），将 v1.0 的 Phase 1（5天 HAL 开发）压缩至 3 天，因为三层架构和 Mock 驱动已经就位，只需编写 SCPI 翻译层。" }
        ]),

        new Table({
          columnWidths: [1200, 3600, 1200, 3360],
          rows: [
            new TableRow({ children: [
              hCell("阶段", 1200), hCell("内容", 3600),
              hCell("工期", 1200), hCell("关键交付物", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 0", 1200, { run: { bold: true } }),
              dCell("硬件清点与环境准备", 3600),
              dCell("Day 0", 1200),
              dCell("仪器清单、VISA 连通性验证、.env 配置", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 0.5", 1200, { run: { bold: true, color: "C62828" } }),
              dCell("代码适配层准备（v2.0 新增）", 3600),
              dCell("Day 0", 1200),
              dCell("RF 开关 HAL 骨架、DRIVER_REGISTRY 更新、__init__.py 导出", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 1", 1200, { run: { bold: true } }),
              dCell("HAL 真实驱动开发", 3600),
              dCell("Day 1–3", 1200),
              dCell("4 个 Real 驱动通过冒烟测试", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 2", 1200, { run: { bold: true } }),
              dCell("暗室全链路校准", 3600),
              dCell("Day 4–8", 1200),
              dCell("6 级校准完成、ISO 证书 PDF 生成", 3360)
            ]}),
            new TableRow({ children: [
              dCell("Phase 3", 1200, { run: { bold: true } }),
              dCell("CDL 信道加载与首次 E2E 测试", 3600),
              dCell("Day 9–13", 1200),
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

        // ======================== 4. Phase 0 ========================
        pb(),
        heading("4. Phase 0 — 硬件清点与环境准备（Day 0）"),
        para("本阶段在正式 Day 1 之前完成。目标是确保团队对硬件现状有一致认知，消除后续开发的信息不确定性。"),

        heading("4.1 仪器清单确认", HeadingLevel.HEADING_2),
        para("需在暗室内逐一确认并记录以下仪器的品牌、型号、固件版本和网络/GPIB 地址："),

        new Table({
          columnWidths: [2400, 2400, 2400, 2160],
          rows: [
            new TableRow({ children: [
              hCell("仪器类型", 2400), hCell("当前代码假设", 2400),
              hCell("需确认项", 2400), hCell("状态", 2160)
            ]}),
            new TableRow({ children: [
              dCell("信道仿真器", 2400), dCell("Keysight PROPSIM F64", 2400),
              dCell("IP、端口、固件版本", 2400), dCell("已有 Real 驱动原型", 2160, { shading: DONE_FILL })
            ]}),
            new TableRow({ children: [
              dCell("基站仿真器", 2400), dCell("Keysight 5G NE / R&S CMW500", 2400),
              dCell("接口类型（SCPI/REST）", 2400), dCell("仅有 Mock 驱动", 2160, { shading: WARN_FILL })
            ]}),
            new TableRow({ children: [
              dCell("信号分析仪", 2400), dCell("R&S FSW", 2400),
              dCell("GPIB/LAN 地址", 2400), dCell("仅有 Mock 驱动", 2160, { shading: WARN_FILL })
            ]}),
            new TableRow({ children: [
              dCell("VNA", 2400), dCell("暂无假设", 2400),
              dCell("型号、连接方式", 2400), dCell("校准服务已就位", 2160, { shading: ACCENT_FILL })
            ]}),
            new TableRow({ children: [
              dCell("RF 开关矩阵", 2400), dCell("暂无假设", 2400),
              dCell("型号、通道数、协议", 2400), dCell("需新建 HAL", 2160, { shading: RISK_FILL })
            ]}),
          ]
        }),

        heading("4.2 开发环境验证", HeadingLevel.HEADING_2),
        bullet("确认 ChannelEngine 本地路径（/Users/Simon/Tools/ChannelEgine）可正常导入，依赖库版本锁定", "bl4"),
        bullet("运行 npm run dev:all，确认三个服务（前端 5173、API 8000、信道引擎 8001）全部正常启动", "bl4"),
        bullet("配置 .env 文件：填入各仪器真实 IP/GPIB 地址，设置 INSTRUMENT_MODE=real", "bl4"),
        bullet("验证 HAL 服务管理器的 switch_hal_mode(DriverMode.REAL) 可正确触发驱动工厂流程", "bl4"),
        bullet("确认 SQLite 数据库 (meta3d_ota.db) 中 instrument_categories 表已有正确的仪器分类记录", "bl4"),

        heading("4.3 Phase 0.5 — 代码适配层准备（v2.0 新增）", HeadingLevel.HEADING_2),
        para([
          { text: "此步骤在 v1.0 中不存在。", bold: true, color: "C62828" },
          { text: " 基于代码审计发现的缺口，需在进入 Phase 1 之前完成以下基础设施准备：" }
        ]),
        bullet("新建 api-service/app/hal/rf_switch.py：定义 RFSwitchDriver 抽象接口（connect_paths, disconnect_all, get_path_status），提供 MockRFSwitch 实现", "bl5"),
        bullet("更新 api-service/app/hal/__init__.py：导出 RFSwitchDriver, MockRFSwitch, PositionerDriver, MockPositioner", "bl5"),
        bullet("更新 instrument_hal_service.py 中的 REAL_DRIVER_REGISTRY：预注册 channelEmulator, baseStation, signalAnalyzer, rfSwitch 四个类别的 Real 驱动类占位", "bl5"),
        bullet("更新 MOCK_FALLBACK 字典：添加 rfSwitch: MockRFSwitch, positioner: MockPositioner", "bl5"),
        bullet("在数据库 instrument_categories 表中确保存在所有五类仪器的记录（含 RF 开关矩阵和 VNA）", "bl5"),

        // ======================== 5. Phase 1 ========================
        pb(),
        heading("5. Phase 1 — HAL 真实驱动开发（Day 1–3）"),
        para([
          { text: "v2.0 调整说明：", bold: true },
          { text: " v1.0 安排了 5 天进行 HAL 开发。由于三层适配器架构（InstrumentDriver → [Type]Driver → Real[Model]Driver）已完整就位，Mock 驱动均可正常运行，且 F64 真实驱动已完成 1198 行双管线 SCPI 代码，实际工作量仅剩基站仿真器和信号分析仪。因此压缩至 3 天。" }
        ]),
        para([
          { text: "驱动文件命名规则：", bold: true },
          { text: " 每个具体仪器型号一个独立 .py 文件，以型号命名（如 propsim_f64.py、cmw500_base_station.py、fsw_signal_analyzer.py），避免使用泛化的 real_xxx.py 命名，防止多厂商场景下命名冲突。" }
        ]),

        heading("5.1 Day 1：信道仿真器双管线验证（已完成 SCPI 编写）", HeadingLevel.HEADING_2),
        heading("状态：propsim_f64.py 双管线 SCPI 翻译已完成", HeadingLevel.HEADING_3),
        para([
          { text: "propsim_f64.py 已扩展至 1198 行、33 个方法，", bold: true },
          { text: "基于 User Reference Ch.20、Runtime Emulation User Guide 和 ATE Practice AN 三份文档完成了全部 SCPI 翻译。Day 1 的任务从「编写代码」变为「真实仪器验证」。" }
        ]),
        para("F64 驱动支持两种信道加载管线："),

        new Table({
          columnWidths: [1800, 3600, 3960],
          rows: [
            new TableRow({ children: [
              hCell("管线", 1800), hCell("工作原理", 3600), hCell("关键 SCPI 指令", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Pipeline A: GCM 原生", 1800, { run: { bold: true } }),
              dCell("F64 内置 Channel Studio 编译 .smu 仿真文件, 原生衰落播放", 3600),
              dCell("CALC:FILT:FILE → DIAG:SIMU:GO → DIAG:SIMU:MOB:MAN:CH", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Pipeline B: ASC Runtime", 1800, { run: { bold: true } }),
              dCell("外部 Channel Engine 计算权重, FTP 传输 .rtc 文件, Runtime Emulation 播放", 3600),
              dCell("FTP STOR → CALC:FILT:FILE → CH:MOD:CONT:ENV", 3960)
            ]}),
          ]
        }),
        gap(),
        para([
          { text: "Day 1 验证清单：", bold: true }
        ]),
        bullet("Pipeline A 验证：加载一个标准 CDL-A .smu 文件, 确认 CALC:FILT:FILE + *OPC? 正常返回", "bl6"),
        bullet("Pipeline B 验证：FTP 上传波形文件到 D:\\User Emulations\\ASC, 确认文件完整到达", "bl6"),
        bullet("校准旁路验证：DIAG:SIMU:MODEL:STATIC 3（校准模式）, 验证所有通道等增益等延迟", "bl6"),
        bullet("RSRP 内置测量验证：INP:RSRP:MEAS? 输入5G信号, 确认返回值合理", "bl6"),
        bullet("输入/输出相位验证：INP:PHA:DEG:CH / OUTP:PHA:DEG:CH 写入/读回一致性", "bl6"),
        bullet("UDP 测量数据流验证：SYST:MEAS:TAR:SET 启用后, Python 端收到 UDP 包", "bl6"),

        heading("5.2 Day 2：基站仿真器驱动", HeadingLevel.HEADING_2),
        heading("目标：新建 [型号]_base_station.py", HeadingLevel.HEADING_3),
        para("当前 base_station.py 有 104 行代码，含 BaseStationDriver 抽象类和 MockBaseStation。需根据暗室中实际使用的型号新建对应驱动文件（如 cmw500_base_station.py 或 uxm_base_station.py）。"),

        new Table({
          columnWidths: [3200, 3200, 2960],
          rows: [
            new TableRow({ children: [
              hCell("需实现的原语", 3200), hCell("业务含义", 3200), hCell("关键参数", 2960)
            ]}),
            new TableRow({ children: [
              dCell("set_cell_config(band, freq, bw, scs)", 3200),
              dCell("配置 NR 物理小区", 3200),
              dCell("n78, 3.5 GHz, 100 MHz, 30 kHz", 2960)
            ]}),
            new TableRow({ children: [
              dCell("set_frc_config(frc_ref)", 3200),
              dCell("配置固定参考信道（FRC）", 3200),
              dCell("3GPP TS 38.521-4 FRC 表", 2960)
            ]}),
            new TableRow({ children: [
              dCell("set_downlink_power(power_dbm)", 3200),
              dCell("调节下行发射功率", 3200),
              dCell("-50 ~ 0 dBm 步进", 2960)
            ]}),
            new TableRow({ children: [
              dCell("start_signaling()", 3200),
              dCell("开启信令，等待 DUT Attach", 3200),
              dCell("超时 60 秒告警", 2960)
            ]}),
            new TableRow({ children: [
              dCell("get_throughput_metrics()", 3200),
              dCell("轮询读取 MAC 吞吐量 + BLER + CQI", 3200),
              dCell("200ms 采样间隔", 2960)
            ]}),
          ]
        }),

        heading("5.3 Day 3：信号分析仪 + RF 开关 + 集成冒烟测试", HeadingLevel.HEADING_2),
        bullet("信号分析仪 [型号]_signal_analyzer.py（如 fsw_signal_analyzer.py）：实现 setup_spectrum_analyzer()、fetch_peak_power() 两个核心原语", "bl6"),
        bullet("RF 开关矩阵 [型号]_rf_switch.py：实现 connect_paths()、disconnect_all()，支持 32 探头通道逐一切换", "bl6"),
        gap(),
        heading("Day 3 下午：全仪器集成冒烟测试", HeadingLevel.HEADING_3),
        bullet("运行 e2e_test_suite.py（已有 19.7KB 测试框架）中的 HAL 连接测试用例", "bl7"),
        bullet("调用 switch_hal_mode(DriverMode.REAL) 切换至真实驱动模式，观察驱动工厂日志", "bl7"),
        bullet("在 GUI 仪表板切换至 Real 模式，确认仪器在线状态显示绿色", "bl7"),
        bullet("验证降级逻辑：断开一台仪器 → 系统自动回退 Mock → 触发告警", "bl7"),
        bullet("将新 Real 驱动注册到 REAL_DRIVER_REGISTRY 字典并提交代码", "bl7"),

        // ======================== 6. Phase 2 ========================
        pb(),
        heading("6. Phase 2 — 暗室全链路校准（Day 4–8）"),
        para([
          { text: "v2.0 调整说明：", bold: true },
          { text: " 校准系统软件已完成 95%（11 个服务，~380KB 代码），包括：calibration_orchestrator.py（953行，含拓扑排序和级联失效）、probe_calibration_service.py（87KB）、e2e_calibration_service.py、phase_calibration_service.py、calibration_report_generator.py（含 ISO 证书）等。本阶段任务是将 Mock 测量数据替换为真实仪器数据。" }
        ]),

        new Table({
          columnWidths: [900, 2100, 2400, 3960],
          rows: [
            new TableRow({ children: [
              hCell("Day", 900), hCell("校准级别", 2100),
              hCell("使用仪器", 2400), hCell("验收标准", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 4", 900, { run: { bold: true } }),
              dCell("Level 0：探头单元校准", 2100),
              dCell("VNA + RF 开关矩阵", 2400),
              dCell("32 个探头的 S11 幅度、相位、极化方向图测量完成，与标称参数差值 < 0.5 dB", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 5", 900, { run: { bold: true } }),
              dCell("Level 1：路损校准", 2100),
              dCell("VNA + RF 开关矩阵", 2400),
              dCell("SGH→每个探头的 S21 插入损耗扫描完成（3.5 GHz ± 100 MHz），补偿矩阵入库", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 5", 900, { run: { bold: true } }),
              dCell("Level 2：RF 链路校准", 2100),
              dCell("VNA + 信号分析仪", 2400),
              dCell("LNA/PA/双工器增益/噪声系数测量完成，各链路不一致度 < 1 dB", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 6", 900, { run: { bold: true } }),
              dCell("Level 3：端到端校准", 2100),
              dCell("信道仿真器 + 信号分析仪", 2400),
              dCell("E2E 补偿矩阵生成，所有通道幅相误差 < 2 dB / 5°", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 7", 900, { run: { bold: true } }),
              dCell("Level 4：信道校准", 2100),
              dCell("信道仿真器 + VNA", 2400),
              dCell("时域 PDP 与 CDL-A 目标值匹配（< 1 ns RMS 延迟），空间相关性 SCF 满足 TR 38.827 §6.4", 3960)
            ]}),
            new TableRow({ children: [
              dCell("Day 8", 900, { run: { bold: true } }),
              dCell("Level 5：系统验证", 2100),
              dCell("基站仿真器 + 信号分析仪", 2400),
              dCell("TRP/TIS 基准测量，静区场均匀性 < 1 dB（CTIA），生成 ISO 校准证书 PDF", 3960)
            ]}),
          ]
        }),

        gap(),
        para([
          { text: "关键代码接入点：", bold: true },
          { text: " 校准编排器 (calibration_orchestrator.py) 的 execute_calibration_plan() 方法会按拓扑排序依次调用各校准服务。目前各服务使用 use_mock=True 参数生成模拟数据。冲刺期间需将 use_mock 切换为 False，使系统通过 HAL 层调用真实仪器获取测量数据。" }
        ]),
        para([
          { text: "Day 8 是关键里程碑检查点：", bold: true, color: "C62828" },
          { text: " 校准证书生成代表硬件链路完整可信，Phase 3 的 CDL 信道测试才有意义。若任一级校准不通过，不得进入 Phase 3。" }
        ]),

        // ======================== 7. Phase 3 ========================
        pb(),
        heading("7. Phase 3 — CDL 信道加载与首次 E2E 测试（Day 9–13）"),

        heading("7.1 Day 9–10：静态 CDL 信道模型配置与验证", HeadingLevel.HEADING_2),
        para("3GPP 静态 MIMO OTA 测试使用标准化 CDL 信道模型（无时变，时延/功率/角度固定）。"),

        new Table({
          columnWidths: [1800, 2400, 2400, 2760],
          rows: [
            new TableRow({ children: [
              hCell("信道模型", 1800), hCell("场景类型", 2400),
              hCell("MIMO 配置", 2400), hCell("验证参数（TR 38.827 §6）", 2760)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }),
              dCell("UMi NLOS（散射丰富）", 2400),
              dCell("2×2 MIMO", 2400),
              dCell("PDP、SCF、XPO（交叉极化比）", 2760)
            ]}),
            new TableRow({ children: [
              dCell("CDL-C", 1800, { run: { bold: true } }),
              dCell("UMa NLOS（宏小区）", 2400),
              dCell("2×2 MIMO", 2400),
              dCell("PDP、SCF、角度扩展 AS 偏差 < 10%", 2760)
            ]}),
          ]
        }),

        para([
          { text: "代码集成路径：", bold: true },
          { text: " Channel Engine 服务（端口 8001）的 ChannelEngineService.generate_probe_weights() 方法已可计算探头权重。冲刺期间需验证：(1) ASC 文件从 Channel Engine 生成 → (2) 通过 RealPropsimF64Driver.upload_asc_files() 下发到 F64 → (3) F64 播放信号 → (4) 信号分析仪验证 PDP/SCF。" }
        ]),
        para("Day 10 下午：运行 OTA 映射器（GUI 中已有 OTAMapper 组件），输入 CDL-A 参数，验证 32 探头权重计算结果与参考值一致（幅度误差 < 0.3 dB，相位误差 < 3°）。"),

        heading("7.2 Day 11：系统集成预检", HeadingLevel.HEADING_2),
        bullet("DUT 放置于静区，确认基站仿真器信令建立（DUT 成功 Attach 并进入连接态）", "bl8"),
        bullet("手动触发下行功率从 -20 dBm 扫描至 -80 dBm，确认 DUT 吞吐量随功率下降", "bl8"),
        bullet("验证 GUI 实时监控页面的吞吐量曲线正常刷新（WebSocket 推送 + KPI 卡片显示）", "bl8"),
        bullet("确认测试步骤编排器可正确触发完整序列：信道仿真器播放 → 基站配置 → 吞吐量采集 → 停止", "bl8"),

        heading("7.3 Day 12–13：首次完整 E2E 吞吐量测试", HeadingLevel.HEADING_2),
        heading("测试规程（参照 CTIA MIMO OTA v1.2 §4）", HeadingLevel.HEADING_3),

        new Table({
          columnWidths: [800, 2800, 5760],
          rows: [
            new TableRow({ children: [
              hCell("步骤", 800), hCell("操作", 2800), hCell("技术参数", 5760)
            ]}),
            new TableRow({ children: [
              dCell("1", 800, { run: { bold: true } }), dCell("小区配置", 2800),
              dCell("NR n78 (3.5 GHz)，100 MHz，30 kHz SCS，FRC DL 256QAM", 5760)
            ]}),
            new TableRow({ children: [
              dCell("2", 800, { run: { bold: true } }), dCell("信道加载", 2800),
              dCell("CDL-A，2×2 MIMO，路径损耗 78 dB（参考值），多普勒 0 Hz", 5760)
            ]}),
            new TableRow({ children: [
              dCell("3", 800, { run: { bold: true } }), dCell("功率校准点确认", 2800),
              dCell("设定参考下行功率，使 DUT 吞吐量约 70% 峰值（动态范围中间点）", 5760)
            ]}),
            new TableRow({ children: [
              dCell("4", 800, { run: { bold: true } }), dCell("吞吐量 vs 功率扫描", 2800),
              dCell("功率步进 2 dBm，每功率点 200ms × 50 次（共 10 秒），记录 ACK/NACK/DTX", 5760)
            ]}),
            new TableRow({ children: [
              dCell("5", 800, { run: { bold: true } }), dCell("TIS 提取", 2800),
              dCell("从曲线提取 70% 峰值吞吐量对应的接收灵敏度功率", 5760)
            ]}),
            new TableRow({ children: [
              dCell("6", 800, { run: { bold: true } }), dCell("CDL-C 重复", 2800),
              dCell("切换 CDL-C 信道，重复步骤 2–5", 5760)
            ]}),
            new TableRow({ children: [
              dCell("7", 800, { run: { bold: true } }), dCell("Pass/Fail 判定", 2800),
              dCell("对照 3GPP TS 38.521-4 TIS 门限值", 5760)
            ]}),
          ]
        }),

        // ======================== 8. Phase 4 ========================
        pb(),
        heading("8. Phase 4 — 合规测试与报告生成（Day 14–18）"),

        heading("8.1 Day 14–15：多场景合规扫描", HeadingLevel.HEADING_2),

        new Table({
          columnWidths: [1800, 2100, 2100, 3360],
          rows: [
            new TableRow({ children: [
              hCell("CDL 场景", 1800), hCell("频段", 2100),
              hCell("MIMO 配置", 2100), hCell("优先级说明", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }), dCell("n78（3.5 GHz）", 2100),
              dCell("2×2", 2100), dCell("首测已完成，Day 14 复验一次", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-C", 1800, { run: { bold: true } }), dCell("n78（3.5 GHz）", 2100),
              dCell("2×2", 2100), dCell("首测已完成，Day 14 复验一次", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-D（LOS）", 1800, { run: { bold: true } }), dCell("n78（3.5 GHz）", 2100),
              dCell("2×2", 2100), dCell("新增 LOS 场景（K 因子 ≠ 0）", 3360)
            ]}),
            new TableRow({ children: [
              dCell("CDL-A", 1800, { run: { bold: true } }), dCell("n41（2.5 GHz）", 2100),
              dCell("2×2", 2100), dCell("频段扩展，可选，视时间安排", 3360)
            ]}),
          ]
        }),

        heading("8.2 Day 16：Pass/Fail 判定系统完善", HeadingLevel.HEADING_2),
        bullet("在报告系统（pdf_generator.py 66KB 已有图表引擎）中增加 TIS 门限自动判定逻辑", "bl9"),
        bullet("验证系统自动生成吞吐量 CDF 曲线图（CTIA v1.2 §5.3 格式）", "bl9"),
        bullet("确认 PDP 验证图、SCF 验证图在报告中正确展示（TR 38.827 §6.4 强制要求）", "bl9"),

        heading("8.3 Day 17–18：最终报告与里程碑验收", HeadingLevel.HEADING_2),
        bullet("生成完整 PDF 测试报告：封面、测试配置、校准证书引用、各场景结果、Pass/Fail 汇总", "bla"),
        bullet("整理《仪器驱动交接文档》：各仪器型号、SCPI 地址、关键指令清单", "bla"),
        bullet("团队评审：确认所有 DoD 条件已满足，正式关闭本冲刺", "bla"),
        bullet("记录 Phase B 工作清单（App.tsx 拆分重构、PostgreSQL 迁移、动态 MIMO OTA）", "bla"),

        // ======================== 9. 风险 ========================
        pb(),
        heading("9. 关键路径分析与风险管控"),

        heading("9.1 关键路径（v2.0 更新）", HeadingLevel.HEADING_2),
        para("本冲刺的关键路径："),
        para([
          { text: "F64 SCPI 补全（Day 1）→ 基站驱动（Day 2）→ Level 4 信道校准（Day 7）→ 首次 E2E 测试（Day 12）", bold: true }
        ]),
        para([
          { text: "v2.0 调整：", bold: true },
          { text: " 由于 F64 已有原型驱动，关键路径从 v1.0 的「从零建立 VISA 连接」变为「补全 SCPI 指令集」，风险显著降低。但基站仿真器驱动仍是未知领域（可能是 SCPI 或 REST API），需提前确认接口类型。" }
        ]),

        heading("9.2 风险登记册（v2.0 更新）", HeadingLevel.HEADING_2),
        new Table({
          columnWidths: [3000, 800, 800, 4760],
          rows: [
            new TableRow({ children: [
              hCell("风险描述", 3000), hCell("概率", 800),
              hCell("影响", 800), hCell("缓解措施", 4760)
            ]}),
            new TableRow({ children: [
              dCell("信道仿真器 SCPI 文档不完整，指令与实际不符", 3000),
              dCell("高", 800, { shading: RISK_FILL }),
              dCell("1–2 天", 800),
              dCell("已有 F64 原型可加速验证; 用 pyvisa 手动探查仪器响应; 利用 AI 辅助解析 Programming Manual", 4760)
            ]}),
            new TableRow({ children: [
              dCell("基站仿真器采用私有 REST API 而非 SCPI", 3000),
              dCell("中", 800, { shading: WARN_FILL }),
              dCell("1–2 天", 800),
              dCell("Phase 0 即确认接口类型; 若 REST 则改用 httpx 而非 pyvisa; 可抓包 GUI 操作逆向分析", 4760)
            ]}),
            new TableRow({ children: [
              dCell("RF 开关矩阵 HAL 需完全新建，无现有代码参考", 3000),
              dCell("中", 800, { shading: WARN_FILL }),
              dCell("1 天", 800),
              dCell("Phase 0.5 先建骨架; 大多数 RF 开关使用标准 SCPI; 参考 signal_analyzer.py 的驱动模式", 4760)
            ]}),
            new TableRow({ children: [
              dCell("DUT 首次 E2E 无法 Attach（信令故障）", 3000),
              dCell("中", 800, { shading: WARN_FILL }),
              dCell("2 天", 800),
              dCell("提前在传导模式验证 DUT; 检查静区功率电平是否在 DUT 动态范围内", 4760)
            ]}),
            new TableRow({ children: [
              dCell("App.tsx 5832 行单文件导致合并冲突", 3000),
              dCell("高", 800, { shading: RISK_FILL }),
              dCell("持续摩擦", 800),
              dCell("冲刺期间 App.tsx 仅做最小改动; 新增组件以独立文件添加; 拆分留至 Phase A", 4760)
            ]}),
            new TableRow({ children: [
              dCell("ChannelEngine 依赖本地路径; 团队成员环境不一致", 3000),
              dCell("低", 800, { shading: ACCENT_FILL }),
              dCell("0.5 天", 800),
              dCell("已通过 CHANNEL_ENGINE_PATH 环境变量解耦; 确保 .env.example 文档完整", 4760)
            ]}),
          ]
        }),

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
              dCell("硬件驱动工程师（核心）", 2100, { run: { bold: true } }),
              dCell("Phase 0–1", 1800),
              dCell("基于现有 Mock 驱动和 F64 原型，编写所有 Real SCPI 驱动; 补全 VISA 连接; 编写交接文档", 5460)
            ]}),
            new TableRow({ children: [
              dCell("测试/RF 工程师", 2100, { run: { bold: true } }),
              dCell("Phase 2–3", 1800),
              dCell("执行全链路校准（校准软件已就位，操作仪器+验证数据）; 配置 CDL 参数; 完成 E2E 测试; Pass/Fail 判定", 5460)
            ]}),
            new TableRow({ children: [
              dCell("后端工程师", 2100, { run: { bold: true } }),
              dCell("Phase 1–4", 1800),
              dCell("Phase 0.5 代码适配; HAL 集成测试; 校准服务 use_mock→False 切换; TIS 门限 API; DRIVER_REGISTRY 维护", 5460)
            ]}),
            new TableRow({ children: [
              dCell("前端工程师", 2100, { run: { bold: true } }),
              dCell("Phase 1, 4", 1800),
              dCell("Day 3 仪器在线状态验证; Day 17 报告 PDP/SCF 图表验证; 仅做最小改动（避免 App.tsx 冲突）", 5460)
            ]}),
          ]
        }),
        gap(),
        para([
          { text: "人力受限时优先级排序：", bold: true },
          { text: " 信道仿真器驱动 → 基站仿真器驱动 → Level 1 路损校准 → 首次 E2E 测试。其他模块（VNA 驱动、RF 开关）可在首测成功后逐步补全。" }
        ]),

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
              dCell("0", 800, { run: { bold: true } }), dCell("Phase 0/0.5", 1200),
              dCell("所有仪器 VISA IDN 查询返回正常; RF 开关 HAL 骨架代码提交", 4200),
              dCell("VISA 连接失败 → 排查网络/GPIB", 3160)
            ]}),
            new TableRow({ children: [
              dCell("1", 800, { run: { bold: true } }), dCell("Phase 1", 1200),
              dCell("F64 信道仿真器可远程加载 CDL-A 模型并启动仿真", 4200),
              dCell("SCPI 指令无响应 → 当日不切换下一仪器", 3160)
            ]}),
            new TableRow({ children: [
              dCell("2", 800, { run: { bold: true } }), dCell("Phase 1", 1200),
              dCell("基站仿真器可通过软件控制开启小区，DUT 可 Attach", 4200),
              dCell("DUT 无法 Attach → 先传导模式排查", 3160)
            ]}),
            new TableRow({ children: [
              dCell("3", 800, { run: { bold: true } }), dCell("Phase 1", 1200),
              dCell("全仪器 Mock → Real 切换冒烟测试通过", 4200),
              dCell("任一驱动冒烟失败 → 不进入 Phase 2", 3160)
            ]}),
            new TableRow({ children: [
              dCell("6", 800, { run: { bold: true } }), dCell("Phase 2", 1200),
              dCell("Level 0–3 校准完成，补偿矩阵入库", 4200),
              dCell("通道幅相误差超标 → 检查物理连接", 3160)
            ]}),
            new TableRow({ children: [
              dCell("8", 800, { run: { bold: true } }), dCell("Phase 2", 1200),
              dCell("Level 4–5 校准通过，ISO 校准证书 PDF 生成", 4200),
              dCell("PDP/SCF 偏差 > 10% → 不进入 Phase 3", 3160)
            ]}),
            new TableRow({ children: [
              dCell("11", 800, { run: { bold: true } }), dCell("Phase 3", 1200),
              dCell("DUT 吞吐量随功率正常变化（功能验证）", 4200),
              dCell("吞吐量不变 → 排查链路增益和 FRC", 3160)
            ]}),
            new TableRow({ children: [
              dCell("13", 800, { run: { bold: true } }), dCell("Phase 3", 1200),
              dCell("CDL-A 和 CDL-C 场景 TIS 曲线绘制完成", 4200),
              dCell("TIS 异常 → 复查信道权重和路损校准", 3160)
            ]}),
            new TableRow({ children: [
              dCell("18", 800, { run: { bold: true } }), dCell("Phase 4", 1200),
              dCell("完整测试报告 PDF 生成，所有 DoD 条件满足", 4200),
              dCell("—— 冲刺终点 ——", 3160)
            ]}),
          ]
        }),

        // ======================== 12. 冲刺后续 ========================
        pb(),
        heading("12. 冲刺后续路线图"),
        para("本冲刺聚焦于静态 MIMO OTA 的硬件打通。成功后项目路线："),

        new Table({
          columnWidths: [2100, 1800, 5460],
          rows: [
            new TableRow({ children: [
              hCell("阶段", 2100), hCell("时间估算", 1800), hCell("工作内容", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase A 代码治理", 2100, { run: { bold: true } }),
              dCell("冲刺后 2 周", 1800),
              dCell("App.tsx 5832 行拆分重构（按路由模块化）; PostgreSQL 迁移（从 SQLite）; Docker 容器化部署; Mantine UI 组件库引入", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase B 动态信道", 2100, { run: { bold: true } }),
              dCell("Phase A 后 4–6 周", 1800),
              dCell("实现动态 CDL 时变信道播放（TR 38.762 路点线性插值）; VRT 虚拟路测模块接入真实仪器; DET 动态吞吐量指标验证", 5460)
            ]}),
            new TableRow({ children: [
              dCell("Phase C RT-OTA", 2100, { run: { bold: true } }),
              dCell("Phase B 后 8–12 周", 1800),
              dCell("接入 RT 射线追踪信道引擎; 实现 CCSA RT-OTA 数字孪生标尺验证; K-S 合规检验; DET P50/P10 计算", 5460)
            ]}),
          ]
        }),

        gap(),
        para("本冲刺完成的静态 MIMO OTA 测试能力，是动态 MIMO OTA（Phase B）和 RT-OTA（Phase C）的硬件基础。静态测试的 TIS 数据还可作为「动静桥接比」分母，用于 RT-OTA 草案中的 DET 与 TRMS 静态灵敏度对比指标。"),

        // ======================== 附录 ========================
        pb(),
        heading("附录 A：当前代码文件清单（Phase 1 相关）"),
        para("以下为冲刺期间需要修改或新建的核心文件："),
        new Table({
          columnWidths: [4800, 1000, 1200, 2360],
          rows: [
            new TableRow({ children: [
              hCell("文件路径", 4800), hCell("行数", 1000),
              hCell("操作", 1200), hCell("说明", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/base.py", 4800), dCell("160", 1000),
              dCell("无需改动", 1200, { shading: DONE_FILL }), dCell("抽象基类", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/channel_emulator.py", 4800), dCell("407", 1000),
              dCell("无需改动", 1200, { shading: DONE_FILL }), dCell("Mock 驱动", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/propsim_f64.py", 4800), dCell("1198", 1000),
              dCell("已完成", 1200, { shading: DONE_FILL }), dCell("双管线 SCPI 已完成", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/base_station.py", 4800), dCell("104", 1000),
              dCell("无需改动", 1200, { shading: DONE_FILL }), dCell("Mock 驱动", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/[型号]_base_station.py", 4800), dCell("—", 1000),
              dCell("新建", 1200, { shading: RISK_FILL }), dCell("如 cmw500 或 uxm", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/signal_analyzer.py", 4800), dCell("121", 1000),
              dCell("无需改动", 1200, { shading: DONE_FILL }), dCell("Mock 驱动", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/[型号]_signal_analyzer.py", 4800), dCell("—", 1000),
              dCell("新建", 1200, { shading: RISK_FILL }), dCell("如 fsw 或 n9040b", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/rf_switch.py", 4800), dCell("—", 1000),
              dCell("新建", 1200, { shading: RISK_FILL }), dCell("抽象 + Mock", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/[型号]_rf_switch.py", 4800), dCell("—", 1000),
              dCell("新建", 1200, { shading: RISK_FILL }), dCell("型号专用 Real 驱动", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/hal/__init__.py", 4800), dCell("31", 1000),
              dCell("修改", 1200, { shading: WARN_FILL }), dCell("导出新驱动", 2360)
            ]}),
            new TableRow({ children: [
              dCell("api-service/app/services/instrument_hal_service.py", 4800), dCell("620", 1000),
              dCell("修改", 1200, { shading: WARN_FILL }), dCell("注册 Real 驱动", 2360)
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

const outputPath = "/Users/Simon/Tools/MIMO-First/docs/产品特性/静态MIMO-OTA冲刺计划_3-4周_v2.0.docx";
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log("SUCCESS: " + outputPath);
}).catch(err => {
  console.error("FAILED:", err.message);
  process.exit(1);
});
