# P1-69 校准完善设计稿（2026-08-24，供用户 review）

> 队列出处：2026-08-24 批准队列第三片（~~P2-41~~ ✅ #386 → ~~P1-68~~ ✅ #388 → P1-69）。
> 职责：对 Schema Review 遗留的四个设计问题给出**可执行裁决**，并把 #386/#388 两轮
> 内审申报的连带项一并裁掉。产出 = 本稿；**用户 review 通过后**才产生代码切片。
> 双实证：memory 命中 `project_calibration_ce_sa_decision`（CE+SA 不引 VNA）、
> `project_pfs_phase_cal_decision`、`project_b2_universal_channel_injection_design`
> （B-2 标注式 CDL 路线 + F64 无 custom PSD 硬约束）；NotebookLM 本稿不适用
> （不新增 SCPI；§1 激活片实施时**必查** SA 手册——见验收）。
> ⚠ 本稿两处**修正**已批准 Schema Review 的裁决（R7/R8），修正理由基于新实证，
> 逐处标注 —— 请重点 review 这两处。

## §1 R8 裁决修正：channel_calibration 8 表不是过度设计存量，是信道验证体系 —— 保留并分级激活

**Schema Review 原判**：「2025 设计稿时代铺的体系，冻结待裁决」。
**新实证推翻原判的三个事实**：
1. 这 8 张表对应 **TR 37.977 / CTIA MIMO OTA 信道验证**（channel model validation）
   标准项目：PDP/时延扩展（temporal）、多普勒频谱（doppler）、空间相关（spatial）、
   角度功率谱（angular）、静区均匀性（qz）、端到端 EIS——正式测量前验证暗室合成
   信道与理论一致，是「校准完善」阶段的**正主**而非遗产。
   ⚠ 依据层级：标准语义出自我方对 TR 37.977 §8/CTIA 的知识记忆，**建议用户复核**。
2. API 面完整（`app/api/channel_calibration.py` 全套 REST：sessions/六类 start+get/
   history/status/invalidate）——不是自家 service 闭环。
3. real 分支**已有骨架**：temporal 走 `sa.measure_pdp`（service:847）、doppler 走
   `sa.measure_doppler_spectrum`（:950）；spatial fail-closed（:1017，转台系旋转
   degree 轴无法摆天线间距，如实拒绝）；qz fail-closed（:1203，P1-64 挡的——缺
   厘米级 XY 场扫描平台）。

**逐表裁决**：

| 表 | real 分支现状 | 裁决 | 激活条件 |
|---|---|---|---|
| temporal_channel_calibrations | 有骨架，但 `measure_pdp` **只有 Mock SA 实现**（signal_analyzer.py:197 random 合成），真驱动（keysight_x_series_sa / rs_fsva）零实现 | **保留，第一激活批** | 给现场 SA（X 系列）实现 PDP 测量 SCPI —— 实施片必查 SA 手册/NotebookLM |
| doppler_calibrations | 同上（:227 仅 Mock） | **保留，第一激活批** | 同上（Doppler 频谱测量） |
| channel_calibration_sessions | 编排壳，无仪器依赖 | **保留**（随激活批使用） | 无 |
| channel_calibration_validity | 信道级五类 validity（见 §2 修正） | **保留** | 随激活批开始写 |
| spatial_correlation_calibrations | fail-closed（转台轴限制，措辞如实） | **保留、暂不激活** | 硬件前提不满足；维持 fail-closed |
| angular_spread_calibrations | 纯 mock（无 use_mock 参数，合成 APS 拟合 Laplacian） | **保留、暂不激活** | ⚠ B-2 路线关联：F64 无 custom PSD、按角度 native-fit 聚类——角度验证的物理可测点要在 B-2 落地后重议 |
| channel_quiet_zone_calibrations | fail-closed（P1-64：缺 XY 场扫描平台） | 见 §2 QZ 并轨 | 硬件采购项 |
| eis_validations | 纯 mock | **保留、暂不激活** | EIS 属 TIS 侧端到端验收，first-call（吞吐类）后再议 |

**第一激活批 = temporal + doppler**：CE 加载 CDL 模型（已有）→ SA 实测 PDP/Doppler →
与 3GPP 理论对比落库。这是「校准完善」阶段第一个可交付的真实闭环，且完全走
CE+SA 既定路线（CE 出信号、SA 收）——**不引 VNA**。

## §2 R6/R7 裁决修正与执行

**R7 修正（原判「以 probe 侧为准、channel 侧并轨」——前提有误）**：两张 validity
**不是双轨**。`probe_calibration_validity`（主键 probe_id）管探头级五类（amplitude/
phase/polarization/pattern/link）；`channel_calibration_validity` 管信道级五类
（temporal/doppler/spatial/angular/qz）——正交域，**都保留**，无并轨动作。

**R6 维持（QZ 双张确是重叠）**：`quiet_zone_calibrations`（49 列，chamber 挂靠，
SGH/grid 实测导向，orchestrator 链）vs `channel_quiet_zone_calibrations`（28 列，
session 挂靠，幅相均匀性统计）。两张都 0 行、生成路径都 fail-closed（P1-64）。
**并轨方向：保留 channel 侧、封存 probe 侧**——理由：① 静区均匀性在标准语义下属
信道验证域（与 §1 体系同宿），validity 位也在 channel_calibration_validity 里；
② channel 侧的幅相统计字段与将来 XY 场扫描平台的产出形态对齐；③ probe 侧那张
49 列大表混入了 SGH/certificate 等路损域字段，职责不单一。
执行：probe 侧表照计划链五表模式挂封存 banner（不删表，历史 0 行无迁移动作）；
`quiet_zone_validation_service` / orchestrator 的 qz 引用改指 channel 侧（换源）。

## §3 RFChain 测量路线裁决：端到端吸收，明细测量冻结

三个选项：
- A. 按现状打通 VNA+SG real —— **否**：rig 无 VNA/SG，违背既定决策。
- B. 重写为 CE+SA —— **否**：UL 链（探头→LNA→CE）方向上 CE 不能既当源又当收；
  硬凑需要 OTA 差分组合，精度与工序都劣于 C。
- **C. 端到端吸收（推荐）**：既有设计已内含此路线——`chamber.py:129` 注释明言
  「其他段的 cable + switch + PA gain 全都包含在端到端测量里」，CE+SA 端到端路损
  （P1-68 已恢复 real 可达的 path_loss / multi_freq `_via_ce_sa`）测的就是**含链增益
  的净路径**，正式补偿用它即可；LNA/PA 明细增益保留 chamber 的标称字段
  （lna_gain_db/pa_gain_db，人工录入 datasheet 值）作诊断参考。
  执行：RFChain 的 `_real_uplink/_real_downlink_measurement`（VNA 基）挂「冻结」
  docstring（不删——将来买 VNA 可复活）；`StartRFChainCalibrationRequest.use_mock`
  字段 description 从「路线归 P1-69 裁决」更新为本裁决结论。

## §4 mock 口全集处置矩阵（#388 申报 + 内审纠偏清单的收口）

| 组 | 站点 | 裁决 |
|---|---|---|
| **Orchestrator ×2**（api :507/:531，含 `execute_calibration_plan` 主链） | 校准编排执行主链 | **随激活批改 request 传入**（照 P1-68 模式）——这是校准完善的执行入口，第一激活批实施片一并做 |
| **workflow_engine phase 步骤**（:583 → `execute_phase_calibration`，活的间接 mock 落库口） | 与 B-2 phase 裁决同源 | **关**：workflow 的 phase 步骤类型 fail-loud（同 P1-68 REST 口语义）；PWS 复活时一并复活 |
| probe_calibration.py amplitude/polarization/pattern/link 四类 mock 写点 | 显式 use_mock=True 落库、GUI 在用 | **保留**（开发/演示路径，provenance 已显式标注，orchestrator fail-closed 挡它们进正式补偿）——不是每个 mock 口都要关，要关的是「没有 provenance 或冒充 real」的 |
| CEInternal ×4 / Relative ×4 / RFSwitch ×2 / E2E ×4 / MeasurementCompensator ×1 | 表在冻结域或依赖冻结路线 | **随所属域冻结**，不单独治理；激活哪个域时按 P1-68 模式一并改 |
| PhaseCalibration 只读端点 ×3（不落库） | 读路径死参 | 随手清（照 P1-68 GET 去死参模式），归第一激活批实施片顺带 |

## §5 P1-4 重复性接 TestExecution

现状：`ReportComparison`/`TestReport` 的对比字段全部 FK 到**封存的** test_plans
（report.py:87/:277-278）；`repeatability_tests` 空表无消费。
方案（**换源不加表**）：
1. `ReportComparison` 增列 `baseline_execution_id` / `comparison_execution_ids`
   （FK→test_executions），旧 plan 列保留只读（封存语义），报表服务对比逻辑换源到
   execution 级；
2. `repeatability_tests` 保留并激活为「同 TestCase 多次 execution 的指标对齐记录」
   ——行含 test_case_id + execution_ids + 指标差分（吞吐/RSRP/SINR），由报表对比
   服务落库；
3. 验收＝Phase 5 跑两次 first-call 后能出 execution 级对比报告（P1-4 的关闭判据）。

## §6 E2E 软引用两列（P2-41 内审 F3 收口）

`e2e_compensation_matrices.path_loss_calibration_id / rf_chain_calibration_id`
（comment 软引用、零 FK、零业务解引用、表 0 行）：随 §4 的 E2E 域冻结**不动**；
若 E2E 域将来激活，激活片须给两列补 FK 或补悬空巡检（届时裁决）。

## §7 切片建议（本稿批准后进入队列）

| 片 | 内容 | 依赖 |
|---|---|---|
| **P1-70 信道验证第一激活批（temporal + doppler）** | 真 SA 驱动实现 measure_pdp / measure_doppler_spectrum（必查 SA 手册 SCPI，X 系列）；channel_calibration 两端点暴露 use_mock（P1-68 模式）；Orchestrator ×2 同批改；phase 只读 ×3 去死参；诊断序列补一条 SA 测量能力探针（出发前载体） | 本稿批准 |
| **P1-71 QZ 并轨 + workflow phase 口关闭** | §2 R6 执行（probe 侧 QZ 封存 banner + qz 引用换源）+ §4 workflow phase fail-loud | 本稿批准 |
| **P1-72 P1-4 对比换源** | §5 三步 | 本稿批准 |
| （不排队）RFChain VNA 复活 / spatial / angular / EIS / XY 场扫描平台 | 硬件采购或路线前提未满足 | 挂 Blocked/HOLD |

## 附：本稿修正的已批准裁决清单（请显式确认）

1. **R8**：冻结待裁决 → **保留并分级激活**（第一批 temporal+doppler）。
2. **R7**：validity 并轨 → **撤销**（两张正交，都保留）。
3. R6 维持但定向：保留 **channel 侧** QZ、封存 probe 侧（原稿倾向相反）。
