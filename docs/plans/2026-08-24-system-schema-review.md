# 系统级 Schema Review —— v0.9.0 之后、校准完善之前（2026-08-24）

> 目的：进入「系统校准完善」阶段前，审查数据架构的**完备性**（校准链路要落的数有没有地方放、
> 链路通不通）与**准确性**（现有 schema 与数据是不是真的），并对冗余给出明确裁决。
> 本文是审查报告 + 裁决建议，**未动任何代码**；每条建议须用户 triage 后才进 roadmap。
> 所有数字来自 main `78b1f11` + 本地 PG 实测（`COUNT(*)`，不是 `n_live_tup` 估计值）。

## 0. 方法

- 双实证：memory 命中 `project_calibration_ce_sa_decision`（路损真测 = CE 出 tone + SA 收功率，
  不引 VNA）、`project_pfs_phase_cal_decision`（phase cal 基建为将来 PWS 保留，PFS 不需要）、
  `project_database_stack`、`feedback_api_contract_sync_after_pydantic_change`；
  NotebookLM 不适用（非仪器语义）。
- 盘点四层：SQLAlchemy models（含 `road_test/` 子目录）→ 本地 PG 真实行数 → 服务层写方定性
  （mock/real 分支）→ API/契约/GUI 消费面。

## 1. 总量地图

| 维度 | 实测 |
|---|---|
| PG 表 | **61** 张（`pg_tables`；不含 alembic_version 则是 60 张） |
| 有 model 的表 | 58 张（`app/models/` 含子目录；61 − alembic_version − 2 孤儿 = 58，双向 diff 对平） |
| 孤儿表（PG 有、model 无） | **2 张**：`alerts_p1_38_backup_20260811`（674 行备份）、`instrument_logs`（0 行；P1-35 已删 model，表遗留，源码注记自认「孤儿表」） |
| 有数据的表 | 36 张；真空表 25 张 |
| 校准域表 | **28 张**（calibration.py 6 + channel_calibration.py 8 + probe_calibration.py 14）= 全库 46% |
| API 端点（实现侧） | 活 app OpenAPI 口径 **253 路径 / 313 操作**，其中校准相关 **101 路径 / 105 操作**（≈40%）。统计方式：启动 app 生成 OpenAPI 后按路径含 calib 计数 |
| openapi.yaml 路径 | **19** 条，校准相关 **0** 条 |
| GUI 引用 calibration 的文件 | 23 个 |

## 2. 准确性发现

### A-1 存量校准数据 289 行，来源标记全部为 NULL —— 正式链路一条都用不上（这是对的，但要知道）

7 张有数据的校准表（amplitude 112 / polarization 62 / phase 52 / link 41 / path_loss 9 /
rf_chain 7 / channel_phase 6 = **289 行**）都有 `use_mock` 来源列，但**每一行的值都是
NULL**——写入时间 2026-04-16 → 2026-05-11，全部是 roadmap 治理（05-14）之前的演示时代数据。
`calibration_orchestrator` 的 provenance 门（`real compensation requires explicit
use_mock=False`）会把 NULL 判为 unknown 并拒绝进入正式补偿——**fail-closed 正确工作**。
含义：**校准完善的起点是 0 行可用的 real 数据**，这 289 行永远进不了正式链路。

**判断**：不抢救。这批行留在库里只会制造「库里已有校准数据」的错误观感（P1-65 教训的
反方向假信息形态）。→ 建议导出归档后清理，或至少批量补 `use_mock=true` 显式打标。

另 3 张有数据表**没有来源列**：`calibration_baselines`(1)、`ce_internal_calibrations`(1)、
`probe_calibration_validity`(32)。validity 是派生表可由重算刷新；前两张单行也是演示期写入。

### A-2 「api/openapi.yaml 是 API 契约定义」已名不副实

CLAUDE.md 与 docs 把 `api/openapi.yaml` 称为契约单一真值源，实况是 19/253 ≈ **8% 覆盖**，
校准域 0%。G8/G11 门守的是「契约 ⊆ 实现」（防契约撒谎），守不到「实现无契约」这 92%。
GUI 的校准页面全部对无契约端点编程（手写类型，非 generated）。

**判断**：两条路二选一，别维持名实不符：① 承认 openapi.yaml 只覆盖核心面并在 CLAUDE.md
如实降格；② 校准完善动到的端点**边做边补契约**（走四步同步），其余面维持现状。建议 ②——
只给要动的面补，不做全量补齐运动（那是纯文档工程，价值密度低）。

### A-3 无假数据泄漏的旁证

`calibration_certificates` 0 行 + readiness 如实报「未补偿」（P1-62 治理过），一致；
`chamber_configuration_integrity` 序列 + G13 门在守校准引用。准确性问题集中在 A-1 存量，
运行时叙述没有说谎。

## 3. 完备性发现（校准完善的三个前置缺口）

### B-1 real 测量路径：CE+SA 两条齐全，RFChain 是 VNA 基（与决策冲突）；5 个端点硬编码 use_mock=True

- **真 CE+SA 的 real 分支只有两条**：path_loss `_real_path_loss_measurement_via_ce_sa` 与
  MultiFreq `_real_frequency_sweep_via_ce_sa`——与既定决策（CE+SA，不引 VNA）一致。
- **RFChain 的 `_real_uplink/_real_downlink_measurement` 是 VNA(+SG) 基**（:1733/:1806，
  docstring 明写 VNA Port1/Port2 S21、"SG 注入信号代替 CE"）——rig 上没有这套仪器，
  与「不引 VNA」决策冲突。**打通它之前必须先裁决测量路线**（重写为 CE+SA 还是接受
  VNA），该裁决归 P1-69 设计稿；P1-68 对 RFChain 只去硬编码、real 标记待裁决。
- API 层：path_loss 端点已支持 `request.use_mock`（含两个强制 real 端点）；但
  `app/api/path_loss_calibration.py` 的 **RFChain 4 个端点（:254/:301/:331/:347）与
  MultiFreq 1 个端点（:376）硬编码 `use_mock=True`**——real 分支从 API 到不了。
- **判断**：P1-68 修「可达性」——5 端点 use_mock 改 request 传入；real 行为门验收收窄到
  MultiFreq（真 CE+SA），RFChain 路线归 P1-69。

### B-2 相位校准 mock 落库口仍开着（P1-5 已知）

`POST /calibration/probe/phase/start` 会生成 job 并落 mock 数据行（现行代码已显式
`use_mock=True`，不会增殖 NULL 来源——内审 F3 核实）。按既定决策 PFS 不需要相位校准。
**判断**：显式挡掉（fail-loud「PFS 不需要相位校准；PWS 未实现」）。

### B-3 重复性（P1-4）缺 TestExecution 级数据位

`repeatability_tests` 表空、`ReportComparison` 契约仍比较已封存的 `plan_id`。校准完善若含
「校准结果可重复」验收，需要把这两处接到 TestExecution 语义上——已在 roadmap P1-4 记录，
此处仅确认数据位缺口属实。

## 4. 冗余裁决清单（明确判断）

| # | 对象 | 现状 | **裁决** | 理由 |
|---|---|---|---|---|
| R1 | `alerts_p1_38_backup_20260811` | 674 行孤儿备份 | **删**（导出归档 → DROP 迁移） | P1-38 已收口三个月，backup 表不该活在生产库 |
| R2 | `instrument_logs` 表 | model 已删（P1-35），表遗留 | **删**（补 DROP 迁移） | 裁决已下、执行未完的尾巴 |
| R3 | `probe_configurations` + `ProbeConfiguration` model + `app/schemas/probe.py` 的 4 个 ProbeConfiguration* 死 schema 类 | 0 行 + 全零引用（schema 类全仓零引用，内审 F5 核实） | **删**（model + 表 + schema 类） | 双零死表；删前按名字前缀全仓终扫 |
| R4 | 计划链五表（27 行历史） | 已封存有 banner | **维持封存，不动** | 已有治理；校准阶段与它无关 |
| R5 | 289 行 NULL 来源校准数据 + `calibration_baselines`(1) / `ce_internal_calibrations`(1) 两行同期演示数据 | 见 A-1 | **导出归档后清理**（次选：批量显式打标 `use_mock=true`） | 正式链路已永久拒绝它们；留着只剩误导价值。A-1 的理由对无来源列的 2 行同样成立 |
| R6 | `quiet_zone_calibrations` vs `channel_quiet_zone_calibrations` | 双轨、都 0 行、各挂一条服务链 | **二选一，校准完善设计时并轨**（倾向保留 probe/orchestrator 侧，channel 侧并入） | 同一概念两处落数，将来必出「只改一处」的镜像 bug——本项目反复踩的母题 |
| R7 | `probe_calibration_validity`(32) vs `channel_calibration_validity`(0) | 双轨 | **以 probe 侧为准，channel 侧随 R8 一并裁决** | probe 侧有活消费链 |
| R8 | `channel_calibration.py` 全家 8 表（sessions/temporal/doppler/spatial/angular/eis/validity/channel_qz） | 8 张全 0 行；引用只在 `channel_calibration_service` + 报告生成器自家闭环 | **冻结待设计裁决**：校准完善设计稿必须显式回答「B-2 标注式 CDL 路线下，多普勒/空间相关/角度扩展校准还要不要」，保留集之外整体封存（照计划链五表模式） | 2025 设计稿时代铺的体系；F64 无 custom PSD 口的硬约束下，这套按信道特征逐项校准的设计很可能已被 B-2 路线取代。**不要默认保留，也不要现在就删**——这是设计问题不是清理问题 |
| R9 | `probe_phase_calibrations`(52) + `channel_phase_calibrations`(6) + phase 基建 | mock 时代数据 | **冻结**（数据随 R5 清理；表与服务保留） | 既定决策：phase cal 为将来 PWS 保留，PFS 不需要。校准完善不在这里花力气 |
| R10 | `system_trp_calibrations`、`system_tis_calibrations`、`comparability_tests` | 0 行、极少引用 | **冻结**（不删不投入） | CTIA 系统级验收概念，first-call 路线未到 |
| R11 | `repeatability_tests` | 0 行 | **保留并激活**——P1-4 的自然数据位 | 唯一一张「空但下一步就要用」的表 |

## 5. 建议的行动切片（供 triage，按依赖排序）

1. **[清理片，低风险]** R1 + R2 + R3 + R5：一个 alembic 迁移 + 一次数据导出归档。
   全部是已裁决/双零对象，不碰活链路。
2. **[校准完善第一片]** B-1：5 个端点的 `use_mock` 改 request 传入（照 path_loss 模式），
   顺带把动到的端点补进 openapi.yaml（A-2 裁决 ②）。
3. **[校准完善设计稿]** R6/R7/R8 的保留集裁决 + B-3 的 TestExecution 接法 +
   **RFChain 测量路线裁决**（VNA 基现状 vs 重写 CE+SA，见 B-1）——先设计后动代码（⓪⁺② 流程）。
4. **[随手关口]** B-2：phase 入口 fail-loud。

## 6. 本审查的已知边界

- 未审 GUI 手写类型与后端 schema 的逐字段对齐（工作量大、G7/G8 已守部分；建议随切片 2 顺带）。
- 未审 `docs/api/data-model.md` 三层规范与实况的逐条对照（该文档本身可能也需随 A-2 降格更新）。
- 行数快照取自本地开发库；现场部署库的分布可能不同（但 schema 相同）。
