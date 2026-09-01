# P2-54 — RAT-neutral MAC Test Profile 实施计划

> 设计依据：`docs/plans/2026-09-02-p2-54-rat-neutral-mac-profile-design.md`
>
> 执行纪律：每个任务先提交能复现旧缺陷的 RED，再做最小 GREEN；每个任务独立提交。
> 不新增/猜测 SCPI，不改变正式 provenance 白名单，不提前实现 P2-55/P2-56。

## Task 1：建立判别联合与 TestCase 迁移边界

**文件**

- 新增：`api-service/app/hal/base_station_mac_profile.py`
- 修改：`api-service/app/schemas/mimo_ota/config.py`
- 新增：`api-service/tests/test_p2_54_mac_profile_schema.py`

**RED**

1. NR/LTE profile 必填/可选字段、枚举、单位与手册来源分别校验。
2. frozen profile digest 对嵌套字段稳定，任意字段变更会漂移。
3. LTE profile 拒绝 NR MCS/TDD/HARQ process/SCS/CSI-RS 字段；NR profile 拒绝 LTE RMC/TM 字段。
4. 旧 NR 扁平配置确定性迁移到 `nr_throughput@1`；旧 LTE 配置迁移到
   `lte_rmc@1`，不携带 NR-only 字段。
5. 显式 profile 与 PCell RAT、LTE TM、NR SCS 或共同 MIMO 意图分叉时 fail-loud。
6. canonical dump 只输出 `mac_profile`，不再输出旧扁平 MAC 真值。

**GREEN**

- 实现不可变 `MacStatisticalWindow`、`MacMetricRequirement`、NR/LTE profile 与
  `FrozenMacTestProfile`。
- 在 `MIMOOTAConfiguration` 的 before-validator 中只做一次 legacy 输入迁移；
  after-validator 只做多方一致性校验。
- `mimo_layers`、`modulation`、PCell identity 继续作为共同真值；MAC 专属值只存在于 profile。

**验证**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_54_mac_profile_schema.py
```

## Task 2：扩展 manifest 与 P1-75 唯一兼容性门

**文件**

- 修改：`api-service/app/hal/base_station_manifest.py`
- 修改：`api-service/app/hal/base_station_compatibility.py`
- 修改：`api-service/app/hal/uxm_base_station.py`
- 修改：`api-service/app/hal/cmw500_base_station.py`
- 修改：`api-service/app/hal/base_station.py`
- 修改：`api-service/tests/test_p1_75_compatibility_gate.py`
- 新增：`api-service/tests/test_p2_54_mac_profile_compatibility.py`

**RED**

1. UXM 仅接受 `nr_throughput@1`，CMW500 仅接受 `lte_rmc@1`。
2. profile RAT 与 requested RAT 分叉、kind/version 未登记、source 缺失均在纯 evaluator 拒绝。
3. preview、LabProfile sync、readiness 与 freeze 产出相同 requirements/profile/verdict/digest。
4. adapter-scoped Mock 不得扩大目标 manifest 接受域；diagnostic_unbound 保持 no-adapter 黄色语义。
5. pre-P2-54 requirements（缺键或显式 null）重算 digest 与历史值一致。

**GREEN**

- 新增 `BaseStationMacProfileCapability` 与 manifest `mac_profiles`。
- `build_measure_execution_requirements_from_configuration` 冻结同一 profile snapshot。
- evaluator 只比较结构化 RAT、operations 与 kind/version，不读取 driver/name。
- 保持旧 None 的 omit-when-none digest 兼容。

**验证**

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p1_75_compatibility_gate.py \
  api-service/tests/test_p2_54_mac_profile_compatibility.py \
  api-service/tests/test_p2_65_shared_compatibility_readiness.py
```

## Task 3：把 BaseStation MAC SPI 收敛为单一 frozen profile

**文件**

- 修改：`api-service/app/hal/base_station.py`
- 修改：`api-service/app/hal/uxm_base_station.py`
- 修改：`api-service/app/hal/cmw500_base_station.py`
- 修改：`api-service/tests/test_p1_32_mac_config_skip.py`
- 修改：`api-service/tests/test_p1_33_manual_command_forms.py`
- 修改：`api-service/tests/test_p2_51_cmw_mac_config.py`
- 修改：`api-service/tests/test_p2_64_adapter_scoped_mock.py`
- 新增：`api-service/tests/test_p2_54_mac_profile_adapter_spi.py`

**RED**

1. 三个 adapter 方法签名只接收 `FrozenMacTestProfile`。
2. UXM/LTE profile、CMW/NR profile、digest 篡改均在首个配置 I/O 前拒绝。
3. CMW500 只收到 LTE RMC 可表达字段，新路径 `no_equivalent=()`；窄 FDD 2×2 full-RB
   行为与 P2-51 相同。
4. UXM 只收到 NR 字段，现有命令拼装、错误队列、拒绝与 fail-loud 行为不变。
5. result/receipt 绑定 profile digest；操作成功与逐字段 evidence completeness 分离。
6. Mock 复用相同 profile 形状但所有回读为 simulated/unknown。

**GREEN**

- 将 `MacThroughputConfigResult` 移到 vendor-neutral `base_station.py`。
- adapter 内部从 profile 映射到已有局部变量；不修改任何 SCPI 字面量或手册裁决。
- CMW receipt 只覆盖 LTE profile 字段；UXM/Mock receipt 如实保留已有证据强度。

**验证**

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p2_54_mac_profile_adapter_spi.py \
  api-service/tests/test_p2_51_cmw_mac_config.py \
  api-service/tests/test_p1_32_mac_config_skip.py \
  api-service/tests/test_p1_33_manual_command_forms.py \
  api-service/tests/test_p2_64_adapter_scoped_mock.py \
  api-service/tests/test_uxm_kpi_readback.py
```

## Task 4：执行、commissioning、统计窗口与 evidence 只消费冻结 profile

**文件**

- 修改：`api-service/app/services/base_station_adapter_profile.py`
- 修改：`api-service/app/services/mimo_ota/executors/measure.py`
- 修改：`api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- 修改：`api-service/app/services/execution_scpi_evidence.py`
- 修改：`api-service/app/services/execution_evidence_outcome.py`
- 修改：`api-service/app/api/commissioning.py`（仅在现有入口需要显式镜像时）
- 新增：`api-service/tests/test_p2_54_mac_profile_execution.py`
- 修改：`api-service/tests/test_p2_66_execution_evidence_outcome.py`

**RED**

1. MEASURE 从 execution freeze 读取 profile；冻结后修改 TestCase/topology profile 不影响本次执行。
2. session、saved phase、run-all、adhoc 全部产生同一 profile digest；adhoc legacy overrides 也先迁移。
3. 统计等待、P1-74 `SFrames` request、窗口 evidence 与结果摘要使用同一个 frozen window count。
4. NR MCS consistency 只在 NR fixed-MCS profile 运行；LTE RMC 不读 NR MCS。
5. 新执行 evidence 保存 profile digest 与 MAC receipt；simulated/unknown 不进正式 KPI。
6. pre-P2-54 compatibility snapshot 保持可读并分类 `legacy`，不是 no-snapshot，也不是 malformed；
   新 profile digest/receipt 漂移 fail-closed。

**GREEN**

- 在 attempt/freeze 边界解析一次 profile，后续只传 frozen snapshot。
- 记录 profile-scoped MAC receipt，不用 `operation_succeeded` 代替字段 evidence。
- P2-66 outcome 显式识别 pre-profile compatibility snapshot。

**验证**

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p2_54_mac_profile_execution.py \
  api-service/tests/test_p2_66_execution_evidence_outcome.py \
  api-service/tests/test_p2_50_execution_plan.py \
  api-service/tests/test_p1_74_cmw_ebler_subframes.py
```

## Task 5：GUI 与 OpenAPI 四镜像

**文件**

- 修改：`api-service/app/schemas/base_station_binding.py`
- 修改：`api/openapi.yaml`
- 修改：`gui/src/types/api.generated.ts`（生成）
- 修改：`gui/src/types/api.ts`
- 修改：`gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- 修改：`gui/src/features/TopologyProfileEditor/TopologyProfileEditor.tsx`（边界提示）
- 新增：`gui/src/types/macTestProfile.ts`
- 新增：`gui/src/types/macTestProfile.test.ts`
- 修改：`gui/src/features/Dashboard/baseStationBindingTruth.test.ts`
- 新增：`api-service/tests/test_p2_54_openapi_contract.py`

**RED**

1. live OpenAPI、checked YAML、generated TS、手写类型的判别联合完全一致。
2. NR/LTE 切换只改变 profile kind 草稿，不出现 model/adapter 名称判断。
3. LTE 表单不提交 NR-only 字段；NR 表单不提交 LTE RMC 字段。
4. readiness/preview 只渲染服务器 verdict/reasons，不在 GUI 重算。
5. topology editor 明示其参数是仪表 bootstrap，不是 TestCase execution MAC profile。

**GREEN**

- 表单按 RAT/profile kind 渲染公共区与专属区。
- 从 checked-in OpenAPI 重新生成 TS；同步手写类型。

**验证**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_54_openapi_contract.py
node --test \
  gui/src/types/macTestProfile.test.ts \
  gui/src/features/Dashboard/baseStationBindingTruth.test.ts
npm --prefix gui run build
```

## Task 6：生产路径门与 roadmap 镜像

**文件**

- 修改：`api-service/tests/test_rule_gates.py`
- 修改：`docs/roadmap-first-call.md`
- 必要时修改：`CLAUDE.md` 中当前架构镜像（只在确有对应声明时）

**RED**

1. 共同执行器出现 UXM/CMW profile 分支、旧扁平 MAC 消费、adapter 旧多参数 SPI 时规则门失败。
2. CMW 新路径产生非空 `no_equivalent`、Mock receipt 被正式确认、manifest 未声明 profile 时失败。
3. P2-66 旧 snapshot 被归到 no-snapshot 或 invalid 时失败。

**GREEN**

- 增加最小稳定行为/结构门；测试类发现上限 P2，避免把门本身当交付物扩张。
- roadmap 标记 P2-54 本地完成事实，并保持 P2-55/P2-56 范围与现场缺口不变。

## Task 7：全验证、fresh 内审、Ready PR 与外审闭环

1. 运行 P2-54 focused、P1-75/P2-50/P2-51/P2-65/P2-66 相关链与所有 rule gates。
2. 运行全后端、GUI 契约与 production build、`compileall`、单一 Alembic head、
   `git diff --check` 与 base-to-HEAD diff-check。
3. fresh 独立功能内审按 `AGENTS.md` 输出“缺陷 / 建议”分栏；功能 P1=0 才推送。
4. 开 Ready PR，触发 Codex R1；按规则处理功能 P1 与本片内 P2，回归、回复并触发 R2。
5. 覆盖最新 HEAD 的 R2 无 P1且 PR mergeable/checks 通过或无必需 checks 时 merge commit；
   若 R2 仍有 P1，继续最小修复与 P1-only 外审到最新 HEAD 无 P1。
6. fetch 验证 origin/main，本地主目录 ff-only 同步并保留未跟踪仪器资料，清理 worktree/分支。
7. 从最新 main 开始 P2-55，继续保持 WIP=1。
