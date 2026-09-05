# P1-77 LTE TDD MAC 帧结构配置入口设计

## 1. 可观察故障

生产 TestCase 编辑器无法创建或修复 LTE TDD MAC profile。服务端正确拒绝从 legacy 字段或 CMW500
`*RST` 默认值猜出 ULDL configuration 与 special subframe，但 GUI 同时把缺 profile 的 LTE 配置
投影成 FDD、禁用双工切换并跳过 LTE MAC 保存校验。结果是已有 B41/TDD/20 MHz 用例启动固定 422，
操作员没有可达的修复动作。

本片只补齐配置入口与服务器 canonical writer，不改变 P2-56 已实现的仪器下发、回读、证据或现场
认证边界。

## 2. 选择的方案

采用用户批准的 A 方案：GUI 提供类型化 LTE TDD 帧结构控件，服务器接收一次性的 authoring input，
在 TestCase create/update 共用边界生成并冻结 `mac_profile`。浏览器不生成 digest，数据库不持久化
authoring input。

拒绝的替代方案：

- 不建独立“修复旧记录”端点或向导：它会复制 TestCase 保存语义并增加第二套状态机。
- 不要求操作员手写完整 frozen profile JSON：浏览器或人工不应制造服务器摘要。
- 不自动回填 23 条旧记录：历史执行没有 ULDL/SSUBframe/RMC version 权威值。

## 3. 单一真值与请求形态

新增 request-only `lte_tdd_frame_structure`：

```json
{
  "uldl_configuration": 0,
  "special_subframe": 0,
  "rmc_version": 0
}
```

- `uldl_configuration` 只接受 `0..6`。
- `special_subframe` 只接受 `0..7`；8/9 仍因当前 profile 没有 normal cyclic prefix 维度而不可达。
- 20 MHz/B200 的既有满配 RMC 计划要求 `rmc_version=0|1`；其他已支持带宽要求该字段缺失。
- 该对象只允许与 LTE TDD 且没有并行 frozen `mac_profile` 的请求一起出现；冲突双写 fail-loud。
- canonical writer 成功后只输出 `mac_profile`，请求对象从持久化形态消失。

已有完整 frozen TDD profile 打开时，GUI 从服务器 profile 投影三个字段。用户修改任一 LTE MAC、PCell
或统计窗口字段后，GUI 移除旧 frozen profile，提交新的 authoring input，由服务器重新冻结。未修改的
完整 profile 可以原样保存。legacy TDD 没有 profile 时，GUI 从 PCell 显示 TDD，三个选择保持空，
不填则保存前阻断。

## 4. 生产关系全集

| 生产入口 | 权威判据/写方 | 正式消费者 | 可观察断言 |
|---|---|---|---|
| 新建 MIMO_OTA TestCase | `TestCaseService` 共用 canonical writer | 数据库 `TestCase.configuration.mac_profile` | TDD authoring 输入落成 frozen profile，request-only 对象不落库 |
| 编辑完整 TDD TestCase | GUI 从 frozen profile 投影；服务端重验 | 同一 TestCase 行 | 三字段可见可改，改后 digest 由服务器变化 |
| 编辑 legacy TDD TestCase | PCell `duplex` 是显示真值 | GUI 保存按钮/错误区 | 如实显示 TDD；空选择明确提示，不显示 FDD |
| 切换 FDD/TDD | PCell duplex + GUI draft | canonical writer | FDD 不携带 TDD input；TDD 不完整不能保存 |
| 20 MHz 与其他带宽 | 既有 `CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH` 计划 | 保存与后续驱动 | B200 缺版本拒绝；非 B200 多余版本拒绝 |
| preview/readiness | frozen `mac_profile` + manifest evaluator | API/GUI 三判 | 只消费服务器 profile/digest，不读 authoring input |
| execution freeze | canonical TestCase configuration | frozen requirements | profile/digest 与保存值一致，配置后改草稿不影响已冻结执行 |
| Mock/真实执行 | frozen profile | adapter 单参数 SPI | 不新增命令；Mock 只验证形态，不替代现场验收 |

对称路径判定：非 MIMO_OTA 用例不变；NR authoring 不变；LTE FDD 继续由 legacy 输入生成固定 FDD
profile；raw JSON 入口与类型化 GUI 最终都经过同一服务端 writer；create 与 update 共用同一函数。

## 5. 失败语义

- legacy LTE TDD 缺 authoring input：422，提示在 TestCase 编辑器选择 ULDL、special subframe，20 MHz
  还需 RMC version。
- 显式 null、越界、布尔冒充整数、额外字段：422，不猜意图。
- frozen profile 与 authoring input 双写：422，避免两个真值。
- LTE FDD/NR 携带 LTE TDD input：422。
- B200 缺 RMC version或其他带宽夹带版本：保存前/服务端均拒，零仪器 I/O。

## 6. GUI

- LTE 双工控件开放 FDD/TDD，不默认把已有 TDD 改成 FDD。
- TDD 时显示三个离散选择；RMC version 仅在现有计划判定需要时显示为必填。
- 统计窗口在 TDD 下恢复可编辑，因为修改后由服务器重新冻结，不再保留旧 profile 与新 count 的冲突。
- readiness 继续只展示已保存服务器 verdict；未保存修改仍显示未保存，不在浏览器重算兼容性。

## 7. 验证与 P3-23 试行记账

档位为“共享配置/冻结 + GUI 生产入口”：严格 RED→GREEN；开发期只跑定点与受影响链；最终测试输入
稳定后跑一次全后端、GUI 契约、production build、compileall、单一 Alembic head 与 diff-check。
主代理顺序自查并在 PR 明记“非独立内审”。外审按唯一 `(PR, HEAD, Rn)` 请求，先读状态、确认三方
HEAD，再触发；活跃等待每 30–60 秒读取结果，不固定多等一轮，不重复请求。R1 处理功能 P1 与本片
P2，R2 无 P1即合并；R2 若有 P1，修复后继续 P1-only 至覆盖最新 HEAD 无 P1。

PR 记录：开发定点/受影响/全量各运行次数与耗时、同输入重复全量次数、R1 后功能缺陷数、每轮请求
与结果时间、无结果等待时长、重复请求次数，用于验证 P3-23 是否真正降低等待和重复验证。

## 8. 实现状态（2026-09-05，✅ PR #461）

A 方案已按设计落地并完成本地验证。服务器新增的 authoring 对象只在请求边界存在，成功保存后只
留下既有 `lte_rmc@1` frozen profile 与服务器 digest；GUI 不生成摘要。23 条缺损历史记录保持原状，
操作员必须逐条打开并选择真实 ULDL、special subframe，20 MHz 还需选择真实 RMC version。

本片未新增或修改 SCPI、未改变正式 provenance 白名单、未提升 P2-56 现场状态。OpenAPI 中
`TestCase.configuration` 继续是自由对象，没有新增可生成的公开 schema，因此四镜像不适用。

验证结果：受影响链 282 passed；全后端在正确工作目录下 6409 passed / 5 skipped；GUI 新契约
12 passed，production build、compileall、单一 Alembic head 与 diff-check 通过。主代理已按本设计
的生产关系全集逐项自查；该检查不是独立内审。

Codex R1 无 P1、有 1 条本片 P2，已按 RED→GREEN 收口并以 406 项受影响回归验证；R2 覆盖最终
HEAD `eae3b97a` 且无 P1。PR #461 已以 merge commit `1001f1c7` 合入。
