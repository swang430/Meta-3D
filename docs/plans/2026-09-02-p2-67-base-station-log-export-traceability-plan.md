# P2-67 BaseStation 日志与导出可追溯性实施计划

> 执行要求：严格 TDD；每项先在旧实现上看到目标断言失败，再做最小 GREEN。WIP=1，不提前实现
> P2-54，不新增仪器命令，不改变正式 provenance 白名单。

**目标**：让公共租约日志不再硬编码仪表厂商，并让按 execution 筛选的导出文件脱离 GUI 后仍可用服务器
冻结证据独立审计。

## Task 1：冻结租约审计上下文与 vendor-neutral 公共日志

**Files**

- Modify: `api-service/app/services/instrument_test_lease.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/tests/test_instrument_test_lease.py`
- Modify/Create: `api-service/tests/test_p2_67_log_export_traceability.py`

1. RED：CMW500/UXM/第三 adapter 的冻结 validator 在取得与释放日志中分别保留精确
   adapter/binding/execution id；公共文案不得含 `F64/UXM` 或把 baseStation 写成 UXM。
2. RED：commissioning 组合 validator 透传同一审计上下文；普通无 freeze 租约不从 loaded driver、purpose
   或名字前缀猜 adapter/binding。
3. RED：取消、操作异常与释放异常仍保留既有安全语义，新增日志结构不能跳过 Local 交接。
4. GREEN：新增不可变最小审计上下文；复用 validator 属性通道，租约 logger 使用结构化 `extra`，只替换
   公共文案，不改 acquire/release 行为。
5. 运行 lease、BaseStation execution session、commissioning 与 rule gates 相关测试。

## Task 2：execution-filtered 导出权威元记录与独立文件名

**Files**

- Modify: `api-service/app/api/system_logs.py`
- Create/Modify: `api-service/tests/test_p2_67_log_export_traceability.py`
- Modify: `api-service/tests/test_system_logs_tail_filter.py`

1. RED：执行 A/B 各有交错日志；按 B 导出只含 B，文件名含 B 的完整 UUID，首行元记录含时间、源文件、
   完整过滤条件、frozen adapter/binding、requested RAT 与 P2-66 outcome。
2. RED：后续修改 current TestCase/LabProfile/HAL 不改变旧执行的元记录；客户端无 adapter/RAT/verdict 参数。
3. RED：非法 UUID、未知 execution、畸形 freeze 分别得到 400、404、`invalid + null`，不得 500 或补真。
4. RED：无 execution 过滤的普通导出仍是纯匹配日志；`/download` 文件名与字节完全不变。
5. GREEN：只在 execution filter 存在时加载 `TestExecution` 并构造不可变元记录；继续复用 `_group_matches()`
   产生后续日志行；文件名加入完整 execution id。
6. 运行 system log tail/history/export、审计 middleware 与 P2-67 专项。

## Task 3：GUI 同源查询与 API/OpenAPI 镜像

**Files**

- Modify only if contract requires: `gui/src/features/Reports/components/SystemLogViewer.tsx`
- Modify: `api/openapi.yaml`
- Modify only if generated contract changes: `gui/src/types/api.generated.ts`
- Modify/Create: `api-service/tests/test_p2_33_log_ux_pack.py`
- Modify/Create: P2-67 GUI/OpenAPI contract tests

1. RED：屏幕、历史和导出仍恰好消费同一 `buildLogQuery()`；execution id 由同一参数进入，不另拼查询。
2. RED：API 文档明确 execution-filtered 导出的元记录、文件名与 400/404；原始 download 声明不变。
3. GREEN：GUI 若无需行为改动则只加契约门，不为“有改动”而改生产代码；同步 live OpenAPI、checked YAML
   与生成类型中实际受影响的部分。
4. 运行 GUI 契约和 production build。

## Task 4：生产路径门与 roadmap 镜像

**Files**

- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-design.md`

1. RED：公共租约日志不得硬编码 `F64/UXM`；导出元数据必须取自服务器 execution freeze/P2-66 outcome，
   禁止客户端提交 adapter/RAT/verdict；raw download 不得复用 enriched stream。
2. GREEN：只加最小永久门；测试类发现严重度上限 P2。
3. 更新活文档：P2-66 已由 PR #435 合并、P2-67 本地实现状态与下一项 P2-54；历史/现场记录不改写。

## Task 5：验证、fresh 内审与外审闭环

1. 运行 P2-67、lease、system logs、P1-34/P1-36、P2-33、P1-75/P2-65/P2-66 与 rule-gates focused tests。
2. 运行全后端、适用 GUI contract、production build、compileall、单一 Alembic head、
   `git diff --check main...HEAD`。
3. 对“导出错 execution”与“元数据从 current state 补真”两个核心故障做最小变异，确认新测试会红。
4. 按 `.claude/agents/pre-commit-reviewer.md` 做 fresh 独立功能内审；功能 P1 严格 RED→GREEN 后复审。
5. 推送 Ready PR，触发 Codex R1；处理本片功能 P1 与本片内 P2 后触发 R2。
6. 覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks时 merge commit；若仍有 P1，
   继续最小修复与 P1-only 外审直到最新 HEAD 无 P1。
7. fetch 验证 `origin/main`，主目录 ff-only 同步并保留未跟踪仪器资料，清理 worktree/本地分支后才
   开始 P2-54。
