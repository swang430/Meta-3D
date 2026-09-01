# P2-65 — Preview / Readiness / Freeze 共用兼容性判定设计

**日期**：2026-09-01
**状态**：已批准设计的实施细化
**Roadmap**：P2-65（依赖 P1-75、P2-64）

## 1. 可观察故障与本片目标

错误的 `TestCase × BaseStation Adapter` 组合在执行冻结时已经由 P1-75 拒绝，但执行前的
Readiness 仍只证明驱动在线和 LabProfile binding 可解析，曾对 UXM + LTE TestCase 报出
`5/5 instruments ready`。操作员因此会先看到绿灯，真正启动时才由后台拒绝。

本片让四个展示/执行站点消费同一份服务端真值：

1. 已保存 TestCase 的 BaseStation 保存预览；
2. LabProfile `sync-current` 结果；
3. `GET /instruments/hal/readiness`；
4. execution freeze。

它们共同使用 P1-75 的 requirements projection、纯 evaluator、requirements digest 与
manifest digest。资源在线、binding 可解析、TestCase 兼容性是三个独立结论，不再由前两项推导
第三项，也不折叠成一个“全绿即可开测”的假结论。

## 2. AGENTS.md 0.5 全集

| 事实 | 唯一真值 / 产生方 | 消费方全集 |
|---|---|---|
| TestCase BaseStation 需求 | 已保存 `TestCase.configuration.component_carriers[0].radio_technology`；缺省精确沿用 MIMO OTA schema 的 `nr5g` | 保存预览、sync 结果、Readiness、freeze |
| Adapter 能力 | `resolve_base_station_binding(...).manifest` 的已注册、不可变 manifest | 同上；禁止读 driver 自报能力、TestCase 名、型号前缀 |
| Binding | `resolve_base_station_binding()` / `build_base_station_binding_preview()` | preview、sync、Readiness、freeze、GUI binding 灯 |
| Resource readiness | HAL `ReadinessReport.drivers` | Readiness API、Dashboard 驱动链灯 |
| 兼容性结果 | P1-75 `BaseStationCompatibilityVerdict` | 新 compatibility preview、API 三镜像、GUI compatibility 灯、freeze payload |
| Digest | `BaseStationExecutionRequirements.digest` 与 `manifest_compatibility_digest()` | preview/sync/readiness/freeze/measure 锁内复核 |
| TestCase 上下文 | API 的显式 `test_case_id`；只能读取数据库已保存行 | TestCase 编辑器、Readiness；全局 Dashboard 无上下文时必须显示未评估，不能绿 |
| GUI 草稿 | TestCase 编辑器本地状态 | 只用于显示“草稿未保存”红灯；不得提交给兼容性 evaluator 冒充已保存真值 |

对称失败形态：TestCase 缺失/非 MIMO OTA、LabProfile 缺失、binding invalid、saved preset 漂移、
manifest/registration 漂移、非法 RAT、UXM+LTE、CMW+NR 都必须返回结构化红灯；
`diagnostic_unbound` 或 simulated binding 只有在结构化组合兼容时显示黄色“可诊断”。

## 3. 方案比较

### 采用：独立 compatibility projection，绑定与资源保持原模型

新增不可变 `BaseStationCompatibilityPreview`，状态为：

- `compatible`：组合兼容；real binding 可显示绿色；
- `incompatible`：evaluator 明确拒绝，红色；
- `no_adapter`：diagnostic_unbound，无 Adapter 可对账，黄色；
- `not_evaluated`：没有显式已保存 TestCase 上下文，红色“不可声明可开测”；
- `invalid`：TestCase、LabProfile、binding 或 manifest 真值无法解析，红色。

投影携带 `test_case_id`、`lab_profile_id`、`binding_digest`、execution mode、完整 requirements、
verdict、reasons 与 detail。`requirements_digest` / `manifest_digest` 只来自 P1-75 模型，不另造算法。
freeze 改为调用同一个 projection helper；不兼容时仍在建执行后的首次 I/O 前 fail-loud。

API 采用加法式扩展：

- binding preview 接受可选 `test_case_id`，响应增加独立 `testcase_compatibility`；
- BaseStation sync 接受可选 `test_case_id`，响应总是返回 compatibility；没有上下文即
  `not_evaluated`，绝不假装兼容；
- HAL Readiness 接受可选 `test_case_id`，新增独立
  `base_station_testcase_compatibility`，与 drivers/binding 并列。

GUI 只把 `test_case_id` 传给服务器并渲染 status/reasons。TestCase 编辑器若 configuration 或
LabProfile 仍是未保存草稿，直接显示红色“保存后再评估”，且不把草稿送入服务端 evaluator。
全局 Dashboard 没有 TestCase 上下文时显示独立红色“未选择已保存用例”，总判不得绿色。

### 拒绝：把 compatibility 塞进 binding resolver

Binding 是 `LabProfile + model + connection + loaded driver` 的稳定真值；TestCase 是另一个维度。
把 TestCase 放进 `binding_digest` 会导致同一硬件绑定因切换用例而漂移，破坏 P2-44/P2-45 的
site certification 与 execution qualification 合同。

### 拒绝：GUI 自行判断 RAT / operation

这会复制 manifest 能力矩阵并重新引入 UXM/CMW 分支，未来第三 Adapter 必须修改生产 GUI，正是
本片要消除的分叉。

### 拒绝：只在 execution freeze 保留硬门

P1-75 已保证安全拒绝，但无法修复操作员先看到绿灯、启动后才失败的可观察故障。

## 4. 数据与错误语义

1. compatibility helper 零仪器 I/O；只读数据库与已加载对象的 resolver 身份。
2. evaluator 的结构化 `reasons` 原样进入 API；GUI 不从文本反推状态。
3. `compatible=true` 不是正式资格。simulated / diagnostic binding 仍为黄色，site certification 与
   Diagnostic/Formal qualification 继续由 P2-45 单独管理。
4. `not_evaluated`、`invalid`、`incompatible` 一律不能使总判绿色。
5. sync 仍只消费 PR #426 的已保存、resolver-valid preset；可选 TestCase 也只读已保存行。
6. execution freeze 的 outer digest 继续覆盖 compatibility payload；本片不回填历史 execution。

## 5. 安全方向

- 把“不知道是否兼容”误判为兼容，会让不可能组合进入执行并产生误导证据；
- 把兼容组合误判为不兼容，只会阻止启动并给出显式原因。

代价不对称，因此未知、缺失、漂移全部 fail-closed。唯一保留的黄色路径是既有
simulated/diagnostic 诊断语义，且其数据仍不得进入正式 KPI。

## 6. 非目标

- 不新增、修改或猜测任何 SCPI；
- 不改变 Adapter manifest 的能力声明与正式 provenance 白名单；
- 不实现 P2-66 的历史证据/终态分类，也不实现 P2-67 日志导出；
- 不扩展 P2-54 MAC profile 判据；`mac_profile` 仍为 `None`；
- 不用本地测试替代任何现场复验。

## 7. 验收

1. UXM+NR、CMW+LTE 在 real binding 下 compatibility 绿；反向组合红。
2. compatible Mock 仅黄；diagnostic_unbound 为黄，不形成正式可开测绿灯。
3. 缺 TestCase、未保存 TestCase/LabProfile 草稿、stale preset、binding/manifest 漂移显式红。
4. preview、sync、Readiness 与 freeze 的 requirements/verdict/digests 字节级同源。
5. Dashboard 分别展示驱动链、BaseStation binding、TestCase 兼容性；任一红不得总绿。
6. GUI 源码不出现新增的 UXM/CMW/RAT/operation 兼容矩阵分支。
7. OpenAPI live、checked-in YAML、generated TS 与手写类型一致。
