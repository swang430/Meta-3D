# 现场日志冲刺设计

**日期：** 2026-08-07
**分支：** `codex/onsite-20260807`
**范围：** P1-44、P1-42、P1-40、P1-37

## 目标

在一个 Draft PR 内补齐当前 roadmap 中剩余的四个日志项，使现场日志同时满足：最新信息容易找到、请求与执行可关联、每次执行可独立归档、Mock 环境也能提供可信的 SCPI 下发意图。

## 交付顺序

1. **P1-44：日志排序与续行归组。** Python traceback 等 RAW 续行先并入父记录，再对父记录排序。系统日志和实时日志默认最新在上；展开态使用由完整字段构造的稳定身份，详情紧跟父行。
2. **P1-42：审计日志进入执行链。** `AuditMiddleware` 改为纯 ASGI，中间件与异步端点共享 ContextVar；请求汇总行读取端点产生的 `execution_id`。每个请求显式初始化并在 `finally` 复位，WebSocket 同步获得 `request_id`。
3. **P1-40：执行日志分流。** 常驻 `app.log` 只记录 INFO 及以上；存在 `execution_id` 时，DEBUG/SCPI 详情同时写入扁平文件 `exec-<execution_id>.log`。执行结束关闭动态 handler，删除执行记录时同步删除日志文件；重复消息在窗口内折叠为汇总行。
4. **P1-37：Mock SCPI 可观察性。** Mock 与真实驱动共享命令构造入口，Mock 记录真实 SCPI 命令意图；模拟回复明确携带 `simulated=true`。模拟值不得进入 measurement、KPI 或报告真值链。

## 数据流

`HTTP/WebSocket 请求 → request_id/execution_id ContextVar → 业务与 HAL 日志 → 常驻 INFO 日志 + 按执行分流日志 → API tail/history → 前端续行归组 → 排序与展示`。

Mock 驱动只在传输边界替换真实 I/O：命令构造和 TX 日志继续走生产路径，返回值通过来源字段标记为模拟。该标记沿日志展示传播，但在测量与报告入口被拒绝。

## 错误处理与边界

- 纯 ASGI 中间件必须捕获 `http.response.start` 获取状态码，同时保留现有异常传播和排除路径语义。
- 动态执行日志文件名保持扁平且只接受规范化 execution UUID；后台 runner 与 HTTP/WebSocket ASGI 边界都负责收口，handler 创建、关闭失败不得中断测试执行或改变连接断开结果。
- 速率限制只压缩不带证据身份的重复日志，不吞第一条、最后汇总或不同 logger/消息模板；带唯一 `exchange_id` 的 SCPI 原始往返 fail-open，绝不折叠。
- traceback 页首没有父记录的 RAW 行暂时独立；加载更早历史页后在合并快照上重新归组。
- P1-37 不模拟完整仪器状态机，不把模拟回读解释成真实设备状态。

## 测试与提交策略

四项分别执行 RED → GREEN → 回归，并形成四个可独立回退的功能提交。规则门覆盖关键不变量；后端跑专项测试及完整测试，GUI 跑生产构建。全部完成后统一进行内部审查与 GitHub Codex 外审。

## 明确不在本轮

Discovered 区的日志表列宽、执行快照 UTC 命名、告警路由遮蔽，以及新的全文索引/跨轮转文件搜索不进入本 PR。
