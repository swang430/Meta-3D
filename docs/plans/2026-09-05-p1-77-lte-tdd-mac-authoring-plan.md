# P1-77 LTE TDD MAC 帧结构配置入口实施计划

> **执行方式：** 单 Agent、WIP=1、严格 RED→GREEN。开发期不重复全量；共享配置与冻结输入稳定后只跑一次最终全后端。

**目标：** 让生产 GUI 能如实打开并补全 LTE TDD TestCase，由服务器生成唯一 frozen MAC profile，消除现有用例启动固定 422。

**架构：** `MIMOOTAConfigForm` 维护 request-only LTE TDD authoring draft；`TestCaseService` 已有 create/update 共用 canonical writer，后者验证 draft、复用既有 CMW RMC bandwidth plan 并生成 `FrozenMacTestProfile`。保存后的 preview/readiness/freeze/execute 不新增分支，继续消费 canonical profile。

**技术栈：** FastAPI、Pydantic v2、SQLAlchemy、React 18、TypeScript、Mantine、pytest、Node test runner。

---

## Task 1：锁定服务器 authoring 契约

**文件：**

- 新增：`api-service/tests/test_p1_77_lte_tdd_mac_authoring.py`
- 修改：`api-service/app/hal/base_station_mac_profile.py`
- 修改：`api-service/app/hal/cmw500_command_profile.py`
- 修改：`api-service/app/hal/cmw500_base_station.py`
- 修改：`api-service/app/schemas/mimo_ota/config.py`

1. 写 RED：B41/TDD/20 MHz + 完整 authoring input 应 canonicalize 成 frozen `lte_rmc@1`，三个值与统计窗口一致，request-only 键不落库。
2. 写 RED：缺 draft、显式 null、bool 冒充整数、越界、额外字段、NR/FDD 夹带、与 frozen profile 双写全部拒绝。
3. 写 RED：复用既有带宽计划，20 MHz 缺 `rmc_version` 拒绝，10 MHz 夹带版本拒绝。
4. 最小 GREEN：增加严格 frozen authoring schema；把 bandwidth→RMC plan 的只读映射收敛到 `cmw500_command_profile.py`，驱动与 canonical writer 共用，不改变任何命令字符串或下发顺序。
5. 最小 GREEN：`_canonicalize_mac_profile` 消费并移除 request-only draft，构造、校验、冻结 profile；既有 frozen/FDD/NR 路径保持不变。
6. 运行定点测试并核对旧实现 RED、新实现 GREEN；变异恢复后确认工作区输入一致。

## Task 2：证明 create/update 生产保存路径

**文件：**

- 修改：`api-service/tests/test_p1_77_lte_tdd_mac_authoring.py`
- 参考且不改：`api-service/app/services/test_plan_service.py`
- 参考且不改：`api-service/app/api/test_plan.py`

1. 写 RED：真实 `POST /api/v1/test-plans/cases` 保存 authoring input，响应和数据库只有 frozen profile。
2. 写 RED：真实 `PATCH` 修复 legacy TDD 行，生成新 digest；失败 PATCH 不改原行。
3. GREEN 只复用 Task 1 canonical writer；若无需改 service/route，不为“对称”增加端点逻辑。
4. 运行 API 定点与既有 carrier truth/case runner 受影响回归。

## Task 3：补齐 GUI 草稿、校验与类型化控件

**文件：**

- 修改：`gui/src/types/macTestProfile.ts`
- 修改：`gui/src/types/macTestProfile.test.ts`
- 按实际契约决定是否修改：`gui/src/types/api.ts`
- 修改：`gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- 按需新增：`gui/src/components/TestCaseConfig/lteTddMacAuthoringTruth.test.ts`

1. 写 RED：legacy LTE TDD 从 PCell 投影为 TDD，三个值保持 null，不得默认为 FDD或仪器默认。
2. 写 RED：完整 frozen TDD 投影三个值；修改后移除 frozen profile并发送 `lte_tdd_frame_structure`；FDD 不携带该键。
3. 写 RED：TDD 缺 ULDL/SSUBframe、20 MHz 缺版本、非 20 MHz 多余版本给出保存前错误。
4. 最小 GREEN：扩展 `LteMacProfileDraft` 与 patch；开启 FDD/TDD 选择，增加三个离散 Select，TDD 统计窗口恢复可编辑。
5. 保持 readiness “未保存”门；GUI 不生成 digest、不重算 adapter compatibility。
6. 跑 GUI 定点测试与 production build。

## Task 4：执行链与镜像回归

**文件：**

- 修改：`api-service/tests/test_p1_77_lte_tdd_mac_authoring.py`
- 按实际契约决定是否修改：`api/openapi.yaml`、`gui/src/types/api.generated.ts`

1. 用 canonical writer 产出的 profile 进入现有 requirements/evaluator/freeze，断言 digest 同一且 CMW manifest compatible。
2. 证明 incomplete draft 在零仪器 I/O 前拒绝；Mock 只验证请求形态，不改变 simulated provenance。
3. 核对 TestCase configuration 在 OpenAPI 中仍是自由对象；若 live schema没有新增公开组件，则记录“四镜像不适用”，不制造无消费方 schema。
4. 跑 P1-77、P2-54、P2-56、P1-75、P2-65、P2-66 与 TestCase API 受影响链。

## Task 5：文档镜像与主代理自审

**文件：**

- 修改：`docs/roadmap-first-call.md`
- 修改：`docs/plans/2026-09-05-p1-77-lte-tdd-mac-authoring-design.md`
- 修改：本计划

1. 全仓搜索旧声明“GUI 没有 TDD 入口”“只保留 frozen profile”“双工只有 FDD”，区分历史记录与活承诺；只更新活文档和紧邻代码注释。
2. 对每个改动文件标记“修/顺带/越界”，撤回越界改动。
3. 主 Agent 顺序自审所有生产入口、对称路径与失败状态；PR 明记“主代理自查，非独立内审”。
4. 运行 `git diff --check`、链接/编号检查与受影响规则门。

## Task 6：最终验证、PR、Codex 外审与合并

1. 在最终测试输入稳定后运行一次全后端，记录命令、退出码、统计与耗时；不因 push 或审查身份重复。
2. 运行 GUI 完整受影响契约、production build、compileall、单一 Alembic head、base-to-HEAD diff-check。
3. 推送分支，创建 Ready PR；记录定点/受影响/全量次数、同输入重复全量次数、主代理自审身份。
4. 读取 PR HEAD、comments、reviews、inline、checks；确认本地 HEAD = 远端分支 SHA = PR headRefOid，再按唯一 `(PR, HEAD, R1)` 请求 Codex。
5. 活跃等待每 30–60 秒读取一次；R1 处理功能 P1 与本片 P2，必要增量验证后推送并回复，确认新 HEAD 再请求 R2。
6. 覆盖最新 HEAD 的 R2 无 P1且可合并/checks 通过或无必需 checks时，以目标 SHA 合并；若仍有 P1，按同一流程继续 P1-only 外审。
7. 合并后 fetch 验证 `origin/main`，主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料，清理 worktree/本地分支。
8. 汇报 P3-23 试行数据：外审请求次数、重复请求、等待时长、重复全量、R1 后功能缺陷及是否出现“多等一轮”。

## 执行记录（2026-09-05）

- Task 1–4 已完成：服务器 authoring→frozen canonical writer、真实 create/update 保存、GUI 类型化
  TDD 控件、compatibility/freeze 回归均按 RED→GREEN 落地；没有新增或修改 SCPI。
- Task 5 已完成：生产入口与对称路径由主代理顺序自查，未发现功能缺陷；这是主代理自查，非独立
  内审。活文档与紧邻代码说明已同步，历史记录未改写。
- `TestCase.configuration` 在 OpenAPI 中仍为自由对象，未新增公开 schema；`api/openapi.yaml`、
  generated TS 与手写 `api.ts` 无需修改，四镜像不适用。
- 最终受影响链 282 passed；全后端第一次因从仓库根目录启动导致既有 Alembic fixture 4 个 setup
  errors，改从 `api-service` 启动后 6409 passed / 5 skipped。相同产品输入重复全量 1 次；这是
  P3-23 试行暴露的流程浪费，PR 中保留原因，不把第一次包装成产品回归失败。
- GUI 新契约 12 passed、production build、compileall、单一 Alembic head 与 diff-check 通过。
- Task 6 的本地阶段完成；待 Ready PR、Codex R1→R2、覆盖最新 HEAD 无 P1后合并与同步清理。
