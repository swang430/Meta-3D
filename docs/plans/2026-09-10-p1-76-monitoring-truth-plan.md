# P1-76 实时监控观测真值实施计划

## 可观察故障

测试租约开放实时监控时，HAL 聚合器按错误的 snake_case 品类键分流，导致四项指标落入固定
`0/0/0/23`；HAL 空结果或异常又由 API 生成随机值。GUI 进一步用硬编码范围计算“指标合规率”，
因此缺测、模拟或无判据的值可以被展示成正常/绿色结论。

## 产生方与消费方全集

- 产生：`InstrumentHALService.get_aggregated_metrics`、`_build_monitoring_data`、API 异常/空闲分支。
- 传递：HAL 指标缓存、`GET /monitoring/feeds`、`WS /ws/monitoring`、后台 broadcaster。
- 契约：FastAPI schema、`api/openapi.yaml`、generated TypeScript、WebSocket 手写类型。
- 显示：`RealtimeMetricsCard`、`ExecutionMetricsCard` 及 `App.tsx` 的诊断监控入口。

## 已批准的 A 方案

1. 删除固定/随机 fallback、无依据 EIRP 推算与固定温度；缺测和异常输出显式 N/A。
2. 统一每项观测为 `value | null + status + provenance + reason + timestamp`。
3. 只允许真实 BaseStation 驱动中 `kpi_valid.dl_throughput_current=true`、有限且非负、
   scope 明确为 `pcell` 或 `nr_all_cells` 的瞬时下行吞吐进入数值显示；unknown、缺失与 simulated
   均 fail-closed，不以 Channel Emulator 同名字段替代。
4. SNR、EIRP、温度在没有各自权威来源前保持 unavailable；Mock 只显示 simulated，不读取随机指标。
5. REST、WS、缓存与两个 GUI 卡片共用上述形态；移除不绑定 TestCase 的硬编码合规率。
6. 保留空闲态零 HAL I/O；租约结束后仍向已连接客户端发 N/A，以清除陈旧数值。
7. 不新增/猜测 SCPI，不改变正式 provenance 白名单，不把实时监控扩大为正式 KPI。

## TDD 与验证

- RED：两组真实输入仍显示同一固定值；缺测补零；异常生成随机值；Mock 被轮询；空闲返回空对象；
  REST/WS/GUI 不支持 nullable provenance；GUI 存在硬编码合规判定。
- GREEN：最小替换产生方与各镜像，逐项验证上述反例。
- 回归：P1-76、P1-64、仪表租约、OpenAPI G11、规则门、完整后端、GUI 契约与 production build、
  compileall、单一 Alembic head、diff-check。

## 非目标

系统 INFO 日志降噪不与 P1-76 混做；只在 Discovered 登记实际分布和未来的成功轮询摘要策略。

## 实现与验证记录

- 初始 RED：旧生产实现下新增后端合同 10 条全部失败，覆盖固定值、随机 fallback、Mock 轮询、
  空闲空对象及契约缺 provenance；GUI 源码合同同样先证明旧组件仍含硬编码合规率。
- 提交前功能审查发现 scope 仅排除 simulated 仍会放行 unknown/缺失；两条新增反例在旧判据下 RED，
  生产门随后收窄为只接受 `pcell` / `nr_all_cells`。
- 最终受影响链 21 passed；全后端 6475 passed / 5 skipped；GUI 合同 17 passed、production build、
  compileall、单一 Alembic head `c5e7f9a1b3d6` 与 diff-check 通过。
- 相同最终产品输入只运行一次全后端；先前 6473 passed 的全量发生在 scope 收窄之前，不复用为
  最终结论，也不因后续纯文档镜像更新再次机械重跑。
- 独立只读功能内审结论 P1=0；其唯一 P2/P3 均为当前文档镜像：旧 Discovered 仍建议三仪表
  机械换 camelCase、指南仍写旧开发端口。两处均已按现状收口，不触发产品回归重跑。
- PR #469 外审：Codex R1 对 `558b88ee`（2026-09-10 10:27:06Z 请求 → 10:33:22Z clean）与同 HEAD
  独立 R2（10:33:43Z 请求 → 10:38:54Z clean）均无 P1、零 inline，重复请求 0 次；10:39:24Z 以
  merge commit `b4e840e0` 合入，无审后尾提交。roadmap / 指南状态由独立纯文档收口 PR 回填。
