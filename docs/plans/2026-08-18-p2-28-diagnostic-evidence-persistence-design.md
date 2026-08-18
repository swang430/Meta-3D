# P2-28 诊断序列完整证据持久化设计

## 可观察故障

`POST /api/v1/diagnostic-sequences/{key}/run` 的 live response 会返回完整
`summary/log/steps/raw/extra`，但 `DiagnosticRun` 只保存最多约 2KB 的
`output_excerpt`。诊断序列入口也没有一个生命周期可证明的 `hal_trace_log_path`。
操作员离开当前页面后，历史记录可能只剩截断摘要，无法重新核对仪器原始回复；现场若未及时
复制 live response，本次诊断证据永久丢失。

## 入口与消费全集

- 产生方：只有 `api/diagnostic_sequence.py::run_diagnostic_sequence()` 能同时拿到序列的
  `summary`、人读日志、逐步 `detail/raw`、结构化 `extra` 与总耗时。
- 通用写方：`DiagnosticContext.record_run()` 同时服务 SCPI command、诊断序列、commissioning；
  本片不能改变后三类已有的 `result_extra` / 2KB 摘要语义。
- 读取方：`GET /diagnostic-runs` 是轻量列表，不应携带大载荷；
  `GET /diagnostic-runs/{id}` 是完整详情的权威读取点。
- GUI：`SequenceRunnerPanel` 的 live 结果已经能显示逐步 raw 与日志；“最近运行”目前只有摘要，
  没有重新打开详情的动作。
- 历史数据：既有 `DiagnosticRun` 没有完整载荷，不能从截断摘要反推或伪造；必须显式为缺失。

## 备选方案

1. **推荐：独立结构化 `sequence_evidence` JSON 载荷。** 诊断序列完成后，把与 live response
   同源的 `schema_version/summary/duration_ms/log/steps/extra` 原样保存到新增 nullable JSONB
   字段；详情 API 暴露，列表不暴露，GUI 历史按 id 获取并复用 live 结果展示。优点是证据与
   审计行同生命周期、无需解析文本、旧记录可明确区分；代价是一列迁移与每次序列运行多一份
   结构化存储。
2. **只保存完整 Text 输出。** 改动较少，但重新展示时必须解析人读文本，空 raw、引号、换行和
   嵌套 extra 都会丢结构；拒绝。
3. **只写 `hal_trace_log_path`。** 可避免数据库大载荷，但日志会轮转、清理，且当前没有可证明的
   运行起止边界或受控下载链；指针存在不等于证据仍存在。若要可靠需新增日志保留、切片身份、
   访问与清理机制，范围和失败面都更大；拒绝。

## 数据契约

`DiagnosticRun.sequence_evidence` 仅在 `kind=scpi_sequence` 的新记录中写入：

```json
{
  "schema_version": 1,
  "summary": "...",
  "duration_ms": 123,
  "log": ["..."],
  "steps": [
    {
      "label": "...",
      "success": true,
      "detail": "...",
      "duration_ms": 12,
      "raw": "仪器原始回复，空串也保留"
    }
  ],
  "extra": {}
}
```

- `raw=null` 表示该步没有仪器回复；`raw=""` 是已观测到的空回复，必须原样保留。
- 成功、设备拒绝、序列异常、HTTP 取消都写同一 envelope；若序列未返回 partial result，
  `steps=[]` 且 `extra.partial_result_available=false`，不虚构中间结果。
- 新字段 nullable、不回填；旧行详情返回 `sequence_evidence=null`。
- `result_extra` 保持原义和原形，避免已有 P1-56 等消费者/测试被新 envelope 包裹后漂移。
- 列表响应仍只有 2KB 摘要；完整载荷只在按 id 详情读取时返回。

## GUI 行为

- “最近运行”每行增加“查看完整证据”。点击后读取详情并显示与 live 结果同形的 summary、steps/raw、
  log 与 extra；不使用 `output_excerpt` 猜完整内容。
- 新记录有 `sequence_evidence` 时显示“完整证据”；旧记录为 null 时明确显示“旧记录未持久化完整
  证据”，仍保留摘要，但不把摘要标成完整。
- 详情加载失败显示服务端可操作错误，不清空当前 live 运行结果，也不自动重跑硬件诊断。

## 失败与安全边界

- 证据与审计行在同一次数据库提交中落地；若完整 JSON 无法序列化/提交，本次审计写入失败应
  明确暴露，不能静默只留下成功摘要。
- 本片不修改序列执行、硬件租约、成功判词或 `safe_during_test`；只持久化已经产生的观测。
- 不把完整证据塞进列表，避免 20/500 行历史查询放大响应。
- 不为旧行回填，不从日志或摘要猜测 raw，不新增日志留存承诺。

## 验收

1. 含长 raw、换行、引号、空串与嵌套 extra 的序列运行，live response 与详情
   `sequence_evidence` 逐字段一致，2KB 摘要即使截断也不影响完整证据。
2. 设备报告 failure 与序列异常同样保留已知 envelope；取消明确标记无 partial result。
3. 列表不携带 `sequence_evidence`，详情携带 nullable 字段；旧行明确为 null。
4. SCPI command 与 commissioning 写入不新增或伪造 sequence evidence，既有 `result_extra` 不变。
5. GUI 可从最近运行重新打开完整证据；旧行不显示为“完整”。
6. greenfield/brownfield 迁移、诊断链、GUI build、compileall、单一 Alembic head 与 diff-check 通过。
