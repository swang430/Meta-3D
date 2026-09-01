# P2-65 共用兼容性 Preview / Readiness 实施计划

> 执行要求：严格 TDD；每项先看见新断言在旧实现上失败，再做最小 GREEN。WIP=1，不提前实现
> P2-66/P2-67/P2-54，不新增仪器命令。

**目标**：让保存预览、LabProfile sync、Readiness 与 execution freeze 共用 P1-75 的需求投影、
判定器和 digest，并由 GUI 分别展示 resource、binding、TestCase compatibility。

## Task 1：共用纯 projection 与 digest 换源

**Files**

- Modify: `api-service/app/hal/base_station_compatibility.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`
- Modify: `api-service/app/services/base_station_binding.py`
- Create: `api-service/tests/test_p2_65_shared_compatibility_readiness.py`

1. RED：覆盖 raw saved TestCase configuration → requirements、UXM/CMW 对账、no adapter、非法 RAT，
   并证明 freeze 与 preview 得到相同 requirements/verdict/digests。
2. GREEN：新增纯 configuration projection 与 resolved-binding compatibility helper；freeze 只调用它。
3. 把 `base_station_adapter_profile.py`、`base_station_binding.py` 的同算法 digest 换源到
   `canonical_payload_digest()`，不得改变既有 digest 值。
4. 运行 P1-75/P2-44 与新专项。

## Task 2：Preview、Sync、Readiness API 同一投影

**Files**

- Modify: `api-service/app/schemas/base_station_binding.py`
- Modify: `api-service/app/api/lab_profile.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/tests/test_lab_profile_api.py`
- Modify: `api-service/tests/test_hal_readiness.py`
- Modify/Create: P2-65 API 专项测试

1. RED：preview/sync/readiness 对 UXM+LTE、CMW+NR 返回 `incompatible`；兼容 real 返回
   `compatible`；Mock/no adapter 返回诊断态；无 `test_case_id` 返回 `not_evaluated`。
2. RED：TestCase 不存在、非 MIMO OTA、binding/preset/manifest 漂移返回结构化红，不连接仪器。
3. GREEN：三个 API 只调用同一个 service projection；sync 的数据库事务与回滚边界保持不变。
4. 证明 preview/sync/readiness/freeze 的 requirements/verdict/digests 完全一致。

## Task 3：GUI 三判展示与未保存草稿门

**Files**

- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/api/labProfileService.ts`
- Modify: `gui/src/components/TestPlanManagement/TestCaseEditModal.tsx`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/features/Dashboard/ZoneReadiness.tsx`
- Modify: `gui/src/features/Dashboard/baseStationBindingTruth.ts`
- Modify/Create: 对应 Node contract tests

1. RED：总判有任意红即红、有任意黄且无红即黄；不再只识别 binding 黄灯。
2. RED：compatibility `incompatible/invalid/not_evaluated` 显示红；simulated/no adapter 黄；real
   compatible 绿。
3. RED：TestCase configuration 或 LabProfile 草稿未保存时显示红且不请求草稿判定；已保存后只传
   `test_case_id + lab_profile_id` 给服务器。
4. GREEN：渲染服务端 status/reasons；禁止 GUI 出现 Adapter/RAT/operation 兼容矩阵。

## Task 4：OpenAPI 与四镜像

**Files**

- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（由 live OpenAPI 生成）
- Modify: `gui/src/types/api.ts`
- Modify/Create: `api-service/tests/test_p2_65_openapi_contract.py`
- Modify: `gui/src/types/baseStationBindingApiTruth.test.ts`

1. RED：live OpenAPI、checked-in YAML、generated TS、手写 GUI 类型缺 compatibility schema/字段/
   `test_case_id` 参数时失败。
2. GREEN：从 live schema 同步 YAML 并重新生成 TS；手写类型只镜像，不另扩展语义。
3. 运行 OpenAPI contract、GUI contract 与 production build。

## Task 5：生产路径门与 roadmap 镜像

**Files**

- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-design.md`

1. RED：新增门确保 preview/sync/readiness/freeze 都调用共同 projection；GUI 不得含 vendor/RAT
   兼容性分支；三判字段不得再被 aggregate 绿灯绕过。
2. GREEN：只增加最小永久门；按规则测试类发现严重度上限 P2。
3. 更新活文档：P2-65 本地实现完成、下一项 P2-66；现场 blocker 不变。

## Task 6：验证、fresh 内审与外审闭环

1. 运行 focused P2-65/P1-75/P2-44/readiness/lab-profile/rule-gates 测试。
2. 运行全后端、GUI contract tests、production build、compileall、单一 Alembic head、
   `git diff --check main...HEAD`。
3. 按 `.claude/agents/pre-commit-reviewer.md` 做 fresh 独立功能内审；P1 严格 RED→GREEN 修复并复审。
4. 推送 Ready PR，触发 Codex R1；处理本片功能 P1 与本片内 P2 后触发 R2。
5. 覆盖最新 HEAD 的 R2 无 P1且 PR mergeable/checks 通过或无必需 checks 时 merge commit；
   若仍有 P1，继续最小修复与 P1-only 外审直到最新 HEAD 无 P1。
6. fetch 验证 `origin/main`，主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料，
   清理 worktree/本地分支后才开始 P2-66。
