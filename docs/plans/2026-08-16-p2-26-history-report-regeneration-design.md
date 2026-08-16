# P2-26 历史 MIMO 报告恢复设计

## 可观察故障

P1-27 已让缺少可信校准来源的旧 MIMO 报告详情与下载 fail-closed，并保留了服务端安全重生成能力；但报告列表没有暴露“需要恢复”的状态，completed 行也没有重生成入口。操作员点击下载只看到通用 409，无法判断下一步，更无法生成 UNKNOWN/N/A 审计件。

## 方案选择

采用“后端恢复状态 + 复用现有生成链”：列表响应由后端基于 `_is_mimo_report()`、`_mimo_report_is_provenance_sanitized()` 与关联 `TestExecution` 计算是否需要恢复、是否可以恢复及原因。GUI 直接消费该真值；可恢复时调用现有 `POST /reports/{id}/generate`，由 provenance-aware builder 从唯一关联执行重建报告。

不采用 GUI 试下载探测，因为它会制造额外请求、依赖 Blob 错误与自由文本；也不采用启动时批量重生成，因为关联执行缺失或多执行报告无法安全重建。

## 后端契约

`ReportSummary` 增加三个只读字段：

- `requires_regeneration: bool`：仅 MIMO 报告且缺 `calibration_trust_schema_version == 1` 时为真。
- `regeneration_available: bool`：仅需恢复且同时满足当前安全生成链的完整前置条件时为真：`single_execution`、无 `road_test_execution_id`、PDF 格式、恰有一个仍存在且经 `is_mimo_ota_execution()` 权威判定为 MIMO OTA 的关联 `TestExecution`，且当前没有恢复任务占用该报告。报告自身的 `report_family` / `generated_by` 只用于识别候选，不能替代执行来源真值。
- `regeneration_reason: Optional[str]`：稳定的操作说明或不可恢复原因。

列表构造必须复用已有 MIMO/可信判据，不按标题、文件名或 generated_by 单独猜测。非 MIMO 与已 sanitized 报告均不显示恢复动作。

`POST /reports/{id}/generate` 继续作为唯一恢复写入口：completed legacy MIMO PDF 可显式调用；列表与写入口复用同一个安全前置条件判据，非 `single_execution`、VRT 关联、非 PDF、无唯一可用且权威属于 MIMO OTA 的执行均在修改状态/content/file 前 409。从关联执行重建全部 payload，不读取旧报告 KPI 作为真值；缺可信 provenance 时输出 UNKNOWN/N/A；explicit-real 证据完整时才恢复正式值；成功后详情与下载恢复可用。入口通过数据库条件更新原子认领 `generating` 状态，认领失败返回 409，禁止多个客户端同时写同一报告文件。

## GUI 行为

- completed + 需恢复且可恢复：显示“需要恢复”标记和“重生成安全报告”动作，不显示普通下载。
- 需恢复但不可恢复：显示不可恢复标记、稳定原因和禁用动作。
- 恢复进行中：列表明确显示不可再次认领；服务端互斥是权威门，单浏览器 loading 状态不承担并发安全。
- 已 sanitized completed：保持下载。
- 成功后刷新列表；提示“已重建为可审计报告”，不得承诺一定恢复 PASS/KPI。
- 普通 generate 与 Blob download 错误统一优先展示服务端 `detail`；Blob JSON 409 也能解析恢复说明。

## 安全边界

- 不放宽 `_reject_untrusted_mimo_report`；恢复前详情/下载仍 409。
- 不回填或猜测 `use_mock`、校准证书来源与 KPI。
- 不自动批量改写历史报告，不为多 execution 报告拼接证据。
- 非 MIMO 报告不受影响。
- 崩溃后遗留的 `generating` claim 保持 fail-closed；在没有 owner/epoch/lease 存活真值前，不因新进程启动就把它自动判成僵尸。Gunicorn 平滑替换即使配置单 worker 也可能短暂重叠，自动复位会重新放行同一正式报告的并发写。

## TDD 验收

1. legacy single-execution MIMO **PDF**（无 VRT 关联、唯一执行存在）在列表中为需恢复且可恢复。
2. sanitized MIMO 与非 MIMO 不要求恢复。
3. 缺失执行、multi-execution、非 single-execution、VRT、非 PDF 与 generating MIMO 均为需恢复但不可恢复，并有可操作原因。
4. completed legacy 行显示恢复动作而非下载；恢复完成后刷新。
5. 不可恢复状态禁用动作并展示原因。
6. Blob 409 显示后端 detail，不退化成通用 HTTP 状态文本。
7. 既有“恢复前 409、恢复后 UNKNOWN/N/A 可下载、explicit-real 才保留正式 KPI”回归通过。
8. 两个客户端同时请求恢复时，仅一个能原子认领；另一个 409，禁止并发覆盖同一文件。
9. 报告标记声称 MIMO、但唯一关联执行不是权威 MIMO OTA 时，列表不可恢复且生成在任何改写前 409。
10. 已带 trust stamp、会绕过 legacy 前置门的 MIMO 候选，若关联执行不是权威 MIMO OTA，仍在生成端第二道防线拒绝且不调用 builder。

## 非目标

- 不恢复不存在的原始测量或校准 provenance。
- 不批量迁移全部历史报告。
- 不新增报告版本树、任务队列或后台作业系统。
- 不处理 VRT/非 MIMO 报告重生成体验。
- 不新增 report claim owner/epoch/lease，也不在无法证明 owner 已死亡时自动复位 `generating`。
