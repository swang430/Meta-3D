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

`POST /reports/{id}/generate` 继续作为唯一恢复写入口：completed legacy MIMO PDF 可显式调用；列表与写入口复用同一个安全前置条件判据，非 `single_execution`、VRT 关联、非 PDF、无唯一可用且权威属于 MIMO OTA 的执行均在修改状态/content/file 前 409。从关联执行重建全部 payload，不读取旧报告 KPI 作为真值；缺可信 provenance 时输出 UNKNOWN/N/A；explicit-real 证据完整时才恢复正式值；成功后详情与下载恢复可用。入口通过数据库条件更新原子认领 `generating` 状态，认领失败返回 409，禁止多个客户端同时写同一报告文件。VRT start/pause/resume/stop/complete 全部以请求读到的当前状态做数据库 CAS，任何陈旧的非终态操作都不能覆盖已经提交的终态；只有唯一终态 winner 能进入自动归档。归档是单次、不可重开的终态产物，已有同 execution 报告即直接退出，不能在延迟请求中重新认领并用另一份本地快照覆盖。首次归档以 `pending`、无生成完成时间落库，只保存可恢复的输入快照；只有 ReportService 的 writer winner 才能发布 `completed`，因此插入后崩溃不会留下“已完成但无 PDF”的假产物。非空 `road_test_execution_id` 数据库唯一索引保证同一 execution 只有一行；插入败方回滚、确认 winner 后直接退出。首次创建后的 PDF 生成若输掉 claim，冲突败方也不得再写 winner 后续的任何状态。通用 `POST /reports` 禁止携带 `road_test_execution_id`，不能用客户端 `content_data` 抢占 VRT 唯一归档槽；GUI 的 VRT 恢复动作改走服务端专用 terminal archive 入口，只接受 completed/stopped 并从权威 `TestExecution` 重建。专用入口只对最终 `completed` 返回成功；`pending`/`failed` 以 409 指向显式 `/reports/{id}/generate` 重试；在没有 owner/lease 存活真值时，`generating` 同样 409但只能提示人工核对，不得给出必然再次冲突的自动重试指引，更不能把崩溃残留假报为“正在生成”。陈旧列表或并发创建冲突稳定返回 409，不冒泡 500。历史重复行不自动猜测删除，迁移须 fail-loud 交由操作员保全并核对正式产物。

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
- 历史 JSON 列只有字典形态才可作为 `content_data` / `TestExecution.config` 判据读取，关联 ID 与 `step_descriptors` 只有数组形态才可遍历；其他形态按无 trust marker / 无描述符 / 无安全关联 fail-closed，不得让一条旧记录毒化整个报告列表。恢复/生成要求关联数组全量合法，任一坏 ID 即整组拒绝；读取侧的 MIMO 候选识别则保守扫描所有可解析项，坏项不能抹掉已经确认的 MIMO 证据并绕过详情/下载门。trust schema 只接受服务端写入的精确 JSON 整数 `1`，布尔值 `true` 与浮点 `1.0` 不得借 Python 等值规则冒充可信版本。
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
11. 并发 VRT 归档不得覆盖已有 `generating` claim；归档触发生成输给另一 writer 后，异常路径也不得把 winner 的 claim 改回 `pending`。
12. `content_data`、关联执行 `config`、`step_descriptors` 或 `test_execution_ids` 为历史错误 JSON 形态时，单行按无可信标记/无 MIMO 描述符/无安全恢复关联处理；混合关联中的有效 MIMO 证据仍必须触发读取可信门，`true`、`1.0` 不得冒充 trust schema 整数 `1`，同页健康报告仍可列出与恢复。
13. 普通单执行报告的关联 ID 数组若含任一非法项，生成入口必须在 claim、权威 collector、旧 `content_data` 复用和文件写入前拒绝；不得把“关联损坏”折叠成“无关联”后重新发布旧 PASS。
14. 两个 VRT stop/complete worker 遇到同一既有归档时必须直接退出；自动终态归档不可被延迟 worker 重新打开或改写，显式报告生成入口才承担恢复。
15. 同一 execution 的首次 VRT 归档并发只能产生一行；唯一插入败方确认 winner 后必须直接退出，不得重新生成。收到 claim 冲突的败方即使观察到 winner 已从 `generating` 转成 `completed`，也不得把它降回 `pending`。
16. 并发 stop/complete 只有一个数据库终态 CAS winner 能进入归档，报告快照必须对应这一权威终态；任何通过通用创建接口声明 VRT 关联的请求都返回可操作 409，不能抢占唯一槽、生成第二行或 500。
17. 首次自动归档行在 writer claim 前必须保持 `pending` 且没有生成完成时间；start/pause/resume 的陈旧请求与 stop/complete 一样必须 CAS 失败，不能把已提交终态改回非终态。
18. 通用报告创建不得写 `road_test_execution_id` 或客户端 VRT `content_data`；completed/stopped VRT 的手工恢复必须走服务端归档入口，从权威执行重建，非终态请求 409；没有 owner/lease 真值时，专用入口不得把 `generating`/`pending`/`failed` 假报为生成成功或进行中。

## 非目标

- 不恢复不存在的原始测量或校准 provenance。
- 不批量迁移全部历史报告。
- 不新增报告版本树、任务队列或后台作业系统。
- 不处理 VRT/非 MIMO 报告重生成体验。
- 不新增 report claim owner/epoch/lease，也不在无法证明 owner 已死亡时自动复位 `generating`。
