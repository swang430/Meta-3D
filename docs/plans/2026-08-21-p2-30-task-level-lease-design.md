# P2-30 设计稿：校准/方向图任务级仪表租约（避免逐点重连）

日期：2026-08-21
Roadmap：P2-30（来源 = roadmap `[discovered 2026-08-08 during 现场分支内审, F4]`「仪表租约的粒度落在最内层」）

## 双实证前置

- **memory**：本会话 memory 不可用（工作棚环境），显式记录；以 `CLAUDE.md` +
  仓库既有权威文档为替代实证源。关键命中：
  - `instrument_test_lease.py::hold()` docstring（189-206 行）：嵌套按引用计数处理，
    只有最外层真正取/放控制权；内层要的控制权不能比外层宽，否则 fail-loud。
  - `path_loss_calibration_service.py::acquire_sa_power_via_ce_tone` docstring
    （改动前 853-856 行，改后 888-891 行）：「调用方要减少 socket 建拆开销时，直接在作业入口（一次探头
    方向图 / 一次 QZ 校验 / 一次 path-loss 作业）外面再包一圈租约即可，本方法
    这圈会自动变成 no-op。」—— 本片就是把这句话落地。
  - 目标文件禁令 grep（`绝不|不许|禁止|must not|别把`）命中 3 条，均与本改动
    不相交：path_loss:52（cert mode 匹配语义）、path_loss:1082（清理警告不许
    只沉日志 —— 外层租约不改变 warning_sink 链路）、quiet_zone:383（positioner
    度数单位禁用于 cm —— 不碰）。
- **NotebookLM**：**不适用** —— 零新 SCPI、零新仪器语义断言。「外层持有期间仪器
  保持 Remote」是既有租约语义（`hold()` 已实现并有测试覆盖），本片只改变**谁**
  在哪一层持有，不改变任何一条仪器命令或其顺序。

## 可观察故障

租约取放在最内层共用 primitive `acquire_sa_power_via_ce_tone`
（path_loss_calibration_service.py，2026-08-07 内审 F2 加的，解决「park 之后
校准必撞 Local 门」），但所有调用方无一在外层持租约。于是**每个测量点**都
真取真放：`release_to_local_control()` 清 `_visa_resource` → 下一点
`acquire_remote_control()` 走完整 `connect()` → `_apply_session_reset()`
每次清 6 个缓存字段（含 running / pipeline / bypass）。

- 一次 path-loss 校准作业（32 探头 × 2 极化）= **64 次 socket 建拆 + 64 次缓存复位**；
- 一次方向图扫描按**角度点**计（el × az 双重循环，每点一次），更甚；
- 一次 QZ XPD 校验 = 2 次（co + cross）。

## 根因

租约粒度落在最内层 primitive，粒度正确性（park 后校准可用）用逐点开销换来。
`hold()` 已于 2026-08-07 内审 F5 改成引用计数/嵌套安全，外层持有时内层那圈
自动 no-op —— 基建已备，只差调用方在作业入口包一圈。

## 改法（不加机制，只在作业入口包一圈）

三类作业在代码里共 **6 个潜在站点**，本次包 **5 处**（②⁺ 全集枚举）：

| # | 作业类 | 入口函数 | 循环形态 | 包法 |
|---|--------|----------|----------|------|
| 1 | 方向图 | `probe_calibration_service.py::PatternCalibrationService._real_pattern_measurements` | el × az 双重循环逐点 | real-only 函数，函数内包住双重循环 |
| 2 | QZ 校验 | `quiet_zone_validation_service.py::run_xpd_validation` | co + cross 两次 | real 分支（else 块）内包住两次调用 |
| 3 | path-loss | `path_loss_calibration_service.py::ProbePathLossCalibrationService.start_calibration` | probe × pol 逐组 | mock/real 同循环 → `nullcontext`/租约条件包住循环 |
| 4 | path-loss | 同文件 `start_calibration_for_lab_profile` | 逐 chain | 同 #3 条件包 |
| 5 | path-loss | 同文件 `MultiFrequencyPathLossService.calibrate_frequency_sweep` | 逐 probe × 逐频点 | 条件包（同 #3，`nullcontext`/租约），包在 probe 循环外 —— 整个扫频作业 1 次而非每探头 1 次；`_real_frequency_sweep_via_ce_sa` 内层不再另包（嵌套本就 no-op） |
| 6 | QZ 校验 | `run_field_uniformity_validation` | real 分支 fail-closed **直接 raise**（等 XY 平移台 API），不达 primitive | **不包** —— 包了反而在 raise 前多做一次真实 acquire/release，行为倒退（Y > X） |

任务书说的「三个作业入口（measure_probe_pattern / QZ 校验 / path-loss 作业）」
按**作业类**计；`measure_probe_pattern` 在当前代码里的实名是
`_real_pattern_measurements`（⚠ 内审 F1：它是 (probe, pol) 层的入口，不是多探头作业入口 ——
`execute_pattern_calibration` 的 probe×pol 循环仍按组数真建拆；今天无生产调用方，
`/pattern/start` 直接写 mock 数据，报告一次留 triage），path-loss 类有 3 个活入口（#3 chamber-keyed 旧门、
#4 lab-profile 正门、#5 扫频），故障同源、修法同形（一行 `async with`），全属
「path-loss 作业」这一类。只做其中一个会把同一故障留在同文件另两个活入口上。

统一参数（与内层那圈完全一致，嵌套宽窄校验恒过）：

```python
async with instrument_test_lease(
    purpose,                 # 各入口带业务标识，现场能看出谁在占用
    control_f64=True,
    control_uxm=False,       # 同内层：B 路 BSE 出 tone 是 SG 角色，不占小区
    enable_monitoring=False, # 作业期间 1Hz 轮询不得抢 SCPI 锁（与内层单点语义一致）
):
```

- 5 处一律**函数内 lazy import**（`from app.services.instrument_test_lease import
  instrument_test_lease`），与内层 wrapper 同款 —— 防循环依赖，且测试只需
  monkeypatch 源模块一处。
- #3/#4/#5 的 mock/real 分叉在循环体**内**（`self.use_mock` 逐点判），外层条件包用
  `contextlib.nullcontext()`（Python ≥3.10 支持 `async with`，本仓 3.13）：
  条件取 `not self.use_mock and chamber.cable_sgh_to_sa_loss_db is not None`，
  精确对齐「会走 CE+SA 路径」的分支判据（同函数内 10 行距离，一眼可核）——
  mock 与 legacy VNA 分支零行为变化（VNA 不经 CE tone primitive，本不需要
  F64 租约，包了反而让 VNA 作业空占 F64 Remote）。
  **条件错配的最坏后果只是退化回现状逐点取放** —— 内层 wrapper 的租约圈保持
  不动，正确性永不受外层条件影响。
- #1/#2 是 real-only 路径，无条件包，mock 路径零触碰。

## 爆炸半径（Y ≤ X）

- 原故障最坏 X：逐点 socket 建拆 + 缓存复位（性能）；点与点之间存在
  「租约空窗」——park/HAL reload 可插入。
- 修完最坏 Y：作业期间 F64 连续持 Remote、监控连续关闭 —— **既有租约语义**
  （正式测试执行早已这样持有整场）；作业中途任何异常路径由 `hold()` 的
  finally 保证交还 Local；内层要的控制权比外层宽时 fail-loud（`hold()` 已有
  行为 + 测试）。mock 路径零变化。Y ≤ X。
- 不改内层 wrapper、不改 `hold()`、不改任何 SCPI、不需要 alembic 迁移、
  不改 roadmap（集中收口）。

## 非目标

- 不包 `run_field_uniformity_validation`（fail-closed，见上表 #6）。
- 不动 `acquire_sa_power_via_ce_tone` 的内层租约（它仍是无外层调用方的兜底）。
- 不做「跨作业租约」（如 orchestrator 一次全链校准共持一圈）—— 那是真正的
  加机制，收益未证。
- 不修 path_loss docstring 851 行「quiet_zone(3 处)」的计数失真（实际 2 处）——
  与本片无关的既有文档瑕疵，留待 triage。

## 测试（RED → GREEN，新文件 `api-service/tests/test_p2_30_task_level_lease.py`）

行为断言用**引用计数桩**（不是源码 grep）：桩替换
`app.services.instrument_test_lease.instrument_test_lease`，维护 depth，
`depth 0→1` 记一次真 acquire、`1→0` 记一次真 release，并记录每次点级测量
发生时的 depth。5 个入口各一条：

- 断言 A：一次作业 `acquires == 1 and releases == 1`（RED 时 = 点数）；
- 断言 B：每次点级测量发生时 depth ≥ 1（点全部在作业级租约持有期间）。

搭法：#1/#2 桩类级 `_acquire_sa_power_via_ce_tone_inner`（内层 wrapper 真跑，
其租约圈计入 enters 但不计 acquires —— 嵌套语义由桩如实模拟）；#3/#4/#5 桩类级
`_real_path_loss_measurement_via_ce_sa`（在桩内读 depth）。#4 monkeypatch
`resolve_rf_chains` 返回两条 fake chain。

变异（④，逐条实跑，FAILED/ERROR 都算红，内存快照写回还原）：
M1–M5 = 分别摘掉 5 个入口的外层租约（还原为直跑循环）→ 对应测试必须红。

## 验收

- 新测试 5 条全绿；变异 M1–M5 全红；
- 全量 `pytest -q` 零失败、无豁免（原已知基线失败
  `tests/test_p1_36_execution_id.py::test_no_execution_means_default_not_empty`
  已由 P2-35 #357 治掉，本片并入 main 后 4076 passed / 0 failed）。
