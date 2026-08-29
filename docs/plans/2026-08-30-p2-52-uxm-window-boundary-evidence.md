# P2-52 —— UXM 权威测量窗口关闭边界:非现场取证清单与裁决(2026-08-30)

> 本片是 P2-52 的**非现场半**:按 Keysight 原始手册查证 stop/closed 生命周期,
> 有出处才实现并回读,没有则永久声明 clear/read-only、diagnostic。
> **不盲试命令**;UXM 到场复验见 §6。

## 1. 取证底本与方法(双源互证)

- 底本:仓库归档
  `Instrument_API_Doc/Keysight UXM NR SCPI/5G_NR_Test_Application_SCPI_Reference.zip`
  内成员 `5G_NR_Test_Application_SCPI_Reference.html`(约 109 MB)。
- 双源:① 本地 zip HTML 逐字 grep(锚点 id 与原文句均已复核);
  ② NotebookLM「Keysight UXM5G 网络测试 SCPI 编程指南」
  (`236d9621-e3ce-4ed1-a8e1-7819b674dbcd`)。两源一致。
- 手册语义裁决权在原文;NotebookLM 的推断按 P1-32 规矩逐条剥离
  (「这句话在手册原文里有没有依据?」)。

## 2. 手册事实(原文,非推断)

**F1 — NR 域 BTHRoughput 树的控制命令恰 4 条**(其余全 Query only,
无独立 STARt/STOP):

| 命令 | 手册原文要点 | 锚点(`#` 后接于 zip!member) |
|---|---|---|
| `BSE:MEASure:NR5G:BTHRoughput[:STATe]` | "Enables/disables BLER measurement",Boolean,Default 0=OFF,AppMode **NSA \| SA** | `scpi/bse:measure:nr5g:bthroughput(:state)` |
| `...:BTHRoughput:CONTinuous[:ALL]` | Single/Continuous,Default 1 | `scpi/bse:measure:nr5g:bthroughput:continuous(:all)` |
| `...:BTHRoughput:LENGth[:ALL]` | 200..360000,Default 360000 | `scpi/bse:measure:nr5g:bthroughput:length(:all)` |
| `...:BTHRoughput:CLEar` | "Resets the BLER measurement. NB if a measurement is in-progress it will **automatically be restarted**."(Imm Action / No query) | `scpi/bse:measure:nr5g:bthroughput:clear` |

Section = NR BLER/Tput > DL Retransmit > BLER/Tput。
⇒ **窗口边界的最强手册事实是 clear,不是 closed。**

**F2 — ⚠ 推断域(非原文)**:显式 `:STATe` 展开 = 方括号可选节点的 SCPI
标准等价;`BTHRoughput[:STATe]?` **查询形手册未列**(对比 `CSI:STATe?`
显式带 `?` 并标 Query only)—— closed/OFF 回读无原文出处。

**F3 — IRAT 适用性未经查证**:上述条目 AppMode 全标 NSA|SA;
`SYSTem:APPLication` 枚举里 NSA 与 LTE_NR_IRAT 并列互斥;手册**无任何一处**
说明 NSA|SA 命令在 LTE_NR_IRAT 下是否可用(NotebookLM 明确拒绝推断 ——
P1-32 规矩:两个方向都没证据 = 未经查证)。

**F4 — 现场实测证据**:生产驱动已在 IRAT 真机实发
`BSE:MEASure:NR5G:BTHRoughput:STATe ON`(`uxm_base_station.py`
`_enable_kpi_measurements` 序列)与每窗口 `CLEar`
(`measure_throughput_window`),2026-07-03 / 08-27 现场执行链跑通 ——
IRAT 下这两条**写形有效**有可查证现场证据;`STATe OFF` 与 `STATe?`
从未在现场发过。

## 3. 裁决(照条目与 P2-48 契约)

- `BaseStationMeasurementCapability.lifecycle` 值域 =
  {authoritative_closed, clear_read_only, unavailable}
  (`base_station_manifest.py`)。本片把 UXM 从 `unavailable` 升级为
  **`clear_read_only`**:依据 = CLEar 手册原文(F1)+ IRAT 现场实测(F4)
  双证据;manifest `source_reference` 指
  `zip!member#scpi/bse:measure:nr5g:bthroughput:clear`。
- **不升 `authoritative_closed`** —— 两个缺口都在:F3(IRAT 适用性未说明)
  + F2(查询形无原文,closed 回读无路)。P2-48 契约(`base_station.py`)
  同时硬保证:`clear_read_only` 不可 confirm closed、
  `formally_confirmed` 需 `authoritative_closed` —— 正式信任面零扩大。
- manifest `measurement.metrics`(adapter 级保守交集,区别于 P2-49 的
  profile 级 registry):取 `lte_nr_irat` 与 `nr5g_test` 两 profile
  `resolve_metric_registry()` 的 key 交集 = **{cqi_index, ri_index}**
  (pcell / index / authoritative,两方言的 CQI/RI 命令各有手册出处,
  锚点 `scpi/bse:measure:nr5g:(cell):csi:cqi:statistics?` 与
  `...:csi:ri:histogram?`)。交集由 test_p2_52 的不变量门守着
  (声明 ≠ 派生交集即红),满足 manifest `:239`「非 unavailable 需
  metrics 非空」。消费方核过:执行端只取 lifecycle/cardinality/scopes,
  窗口逐指标走 profile 级 registry(P2-49),GUI 仅展示投影 —— 交集声明
  不进任何正式取数路径。
- per-window 真相分离:lifecycle 是**上界声明**(本 adapter 永不声称
  closed),每个窗口里 clear 是否真的发生由 trust 的 stage receipt
  逐次记账 —— CLEar 写命令终态 `ok` 且非模拟 → `clear=confirmed` 携
  exchange 证据;发不成 / 方言无 CLEar(5G_NR_Test)→ 如实
  `unavailable`。run/ready/closed 恒不 confirmed(理由分别为 F2 /
  手册无 readiness 边界 / F1 无 stop 边界)。
- `STATe OFF` / `STATe?` **不进正式路径**,落两处:
  ① `uxm_command_profiles.py` 增 `MEAS_BTHROUGHPUT_STATE_QUERY`
  (显式形,注释带「⚠ 推断:方括号展开 + 查询形无原文」+ 手册锚点;
  基类与 5G_NR_Test 保持 None —— BSE 树在该方言认不认未经查证,禁盲试);
  ② 新诊断序列 `uxm_window_boundary_probe`(照 `rs_fsva_iq_capability`
  前例:只读、每步错误队列归属、推断形显式标注、出发前载体)——
  剧本 = 预排水 → `STATe?` 读现状 → 归属错误队列 → 收尾排水;
  **零写命令**(读到 ON 也不动,绝不发 OFF;条目明令不盲试)。

## 4. 改动清单(修 / 顺带)

| 文件 | 类别 | 内容 |
|---|---|---|
| `api-service/app/hal/uxm_base_station.py` | 修 | manifest measurement 升级(lifecycle/metrics/source_reference + 裁决注释);`measure_base_station_window` 冻结校验改 `clear_read_only`、clear 阶段按 CLEar exchange 终态记账、`preclear_off_confirmed` 镜像 trust、evidence 措辞与出处更新 |
| `api-service/app/hal/uxm_command_profiles.py` | 修 | 基类 + IRAT 增 `MEAS_BTHROUGHPUT_STATE_QUERY`(推断标注 + 手册锚点);`MEAS_BTHROUGHPUT_STATE/CLEAR` 注释补 P2-52 取证出处 |
| `api-service/app/diagnostics/sequences/uxm_window_boundary_probe.py` | 修(新文件) | 现场复验探针,零写命令,G18 品类声明 `baseStation` |
| `api-service/tests/test_p2_52_uxm_window_boundary.py` | 修(新文件) | 门 A-D(见 §5) |
| `api-service/tests/test_p2_48_measurement_window_plan.py` | 修 | UXM 冻结计划断言随契约升级(clear_read_only + 交集) |
| `api-service/tests/test_p2_48_adapter_window_truth.py` | 修 | UXM 窗口 trust 测试升级 + 新增「请求与 manifest 漂移 fail-loud」用例 |
| `api-service/tests/test_p2_46_base_station_capability_manifest.py` | 顺带 | UXM manifest 断言随契约升级;锚点门纳入本片新增的 measurement 出处(同源:新 authoritative 出处不纳入即无人验证) |
| `docs/plans/2026-08-30-p2-52-uxm-window-boundary-evidence.md` | 修(新文件) | 本文档 |

下游全集核对(改 lifecycle 值前先 grep 全部读写方):
`_measurement_window_requests`(measure.py,自动从 manifest 传导)、
驱动冻结校验(同步)、trust/receipt 契约(`base_station.py`,值域已含
clear_read_only,closed 禁 confirm 校验既有)、evidence 模型
(`base_station_execution_evidence.py` / `execution_scpi_evidence.py`,
按结构对账无值特判)、P2-50 执行计划(不消费 lifecycle,零改动)、
GUI(`baseStationManifest.ts` 已有 clear_read_only 渲染分支「清零/读取
窗口」,零改动)、openapi/api.generated(枚举已含三值,零改动)、
mock(`MockBaseStation` 回声请求,零改动)。历史 P2-46/P2-48 计划文档
按落款语境保留(其中「留给 P2-52」的预告即本片兑现),不改写历史。

## 5. 门与变异(⓪④,全部实跑)

门(`tests/test_p2_52_uxm_window_boundary.py`,9 用例):

- **门 A(不变量)**:manifest 交集声明 == 两 profile registry 派生交集
  (key 集 + 逐字段语义)。
- **门 B(行为)**:lifecycle == clear_read_only 且出处锚点真实存在于
  归档 HTML;CLEar 真发成(write/ok/非模拟)→ clear confirmed 携该
  exchange、run/ready/closed unavailable、formally_confirmed False、
  preclear 镜像 True;终态非 ok / 模拟交换 → 拒绝 confirm;请求与
  manifest 漂移 → fail-loud(在 test_p2_48_adapter_window_truth)。
- **门 C(行为 + 存在性粗筛)**:探针 SUCCESS 路径零写命令、只发
  {STATe?, SYSTem:ERRor?};被拒(-113)判定为答案;5G_NR_Test 方言
  ABORTED 且一条不发;推断标注 + 全仓消费方白名单
  {uxm_command_profiles, uxm_window_boundary_probe}。
- **门 D(源码)**:`measure_base_station_window` / `measure_throughput_window`
  不引用 `MEAS_BTHROUGHPUT_STATE*`(STATe 写形/查询形不进正式窗口路径)。

变异实跑(内存快照还原、old 串 assert 唯一命中、还原后基线复验绿):

| # | 变异 | 结果 |
|---|---|---|
| M1 | manifest 交集换 key(ri_index→sinr_raw) | 红 ✓(门 A) |
| M2 | manifest lifecycle 回退 unavailable | 红 ✓(门 B) |
| M3 | 驱动冻结校验漂移回 `!= "unavailable"` | 红 ✓(门 B) |
| M4 | clear 证据不查写终态 ok | 红 ✓(门 B timeout 变体) |
| M5 | 模拟交换冒充硬件证据 | 红 ✓(门 B simulated 变体) |
| M6 | 无 CLEar 证据也宣 confirmed | 红 ✓(receipt 契约 + 行为门,2 failed) |
| M7 | 探针盲发 STATe OFF | 红 ✓(门 C 零写命令) |
| M8 | 定义处删「推断」标注 | 红 ✓(门 C 存在性) |
| M9 | 探针方言门被绕(5G_NR 不再拒跑) | 红 ✓(门 C ABORTED) |
| M10 | 正式窗口路径引用 STATe | 红 ✓(门 D) |
| M11 | preclear 镜像与 trust 不一致 | 红 ✓(base_station mirror 契约) |

还原后基线:`test_p2_52 + test_p2_48_adapter_window_truth +
test_p2_48_measurement_window_plan + test_p2_46` = **53 passed**。
`test_rule_gates.py` = **59 passed**(基线 59;G18 对新探针品类声明放行)。

## 6. UXM 到场复验清单(现场半,本地测试不替代)

1. **跑 `uxm_window_boundary_probe`**(诊断面板,LTE_NR_IRAT 下):
   - `state_query_supported=True` ⇒ 推断查询形 `BTHRoughput:STATe?`
     真机成立,归档 `bthroughput_state` 原样 token —— F2 缺口关掉一半
     (查询形实测成立;IRAT 适用性 F3 随之得到该条的正面样本)。
   - `SUCCESS` + 被拒(-113)⇒ 查询形不成立**也是答案**:closed/OFF
     回读无路,lifecycle 永久停在 clear_read_only,探针与本清单归档即止。
2. **STATe OFF 写形复验(操作员人工,不入探针)**:仅在非测试时段、
   探针先行判定查询形成立后,由操作员手动 `STATe OFF` → `STATe?` 回读
   → `SYSTem:ERRor?` 归属 → 立即 `STATe ON` 恢复并回读。写形被拒或
   回读与写入不符,原样记录字面值。
3. **每窗口 CLEar 生效佐证**:正式执行链跑一个窗口,对照 P2-48 evidence
   里 `trust.stages.clear`(应 confirmed 携 exchange id)与
   吞吐量 progress-count 在 CLEar 后归零重累积。
4. 若 1+2 两个缺口都取得正面证据(查询形成立 + OFF 写形有效且回读一致),
   届时才有资格讨论 `authoritative_closed` 升级 —— 仍需先解决 F3
   (IRAT 适用性)的书面依据或系统性实测,并按 P2-48 契约补 closed
   阶段的权威回读实现。**本片不预支。**

## 7. Discovered 候选(待 triage,不自动启动)

- `[discovered 2026-08-30 during P2-52]` **5G_NR_Test 方言 KPI/窗口命令
  全缺**(既有事实的本片视角重述):`MEAS_BTHROUGHPUT_STATE/CLEAR/
  STATE_QUERY` 等在该方言全 None(BSE 树认不认未经查证)→ 该方言下
  measure_throughput_window 退化为累积读数、窗口 clear 阶段恒
  unavailable。出发前若确认现场跑 5G_NR_Test,需先用
  `uxm_scpi_compatibility` 普查补齐。
- `[discovered 2026-08-30 during P2-52]` **`BTHRoughput:LENGth[:ALL]` /
  `CONTinuous[:ALL]` 全仓未驱动**:统计窗口长度与单次/连续模式取决于
  仪器旧状态(Default 360000 / Continuous),与 P2-51 发现的 CMW
  `EBLer:SFRames` 统计基缺口同形态。若 triage 决定处理,归测量窗口层,
  换源到 TestCase 声明。
