# P2-83C：受控激活与显式同步

批准设计：[B/C生效工作流](../design/2026-10-06-p2-83bc-effective-workflow.md)。B已由PR #506合并为`6d335aa5`。C从该基准独立实施，主代理顺序开发，独立只读内审。不启动P2-84。

## 可观察故障与四行契约

1. 保存已成功、HAL激活失败时，重试只能重新保存或整体reload；增加仅重试该类别激活，不PUT配置、不自动同步Lab。
2. 当前同步点击即写且服务器没有操作员确认版本；确认后保存配置漂移可能把未确认值写入Lab。目录提供服务器计算的保存配置摘要，确认窗口冻结目标Lab/类别/摘要；同步在category→Lab→model→connection锁范围内核验，不匹配409且binding不改。
3. 摘要只表达当前数据库保存配置，不是HAL状态、执行binding或正式资格；不新增数据库列、版本账本或客户端摘要真值。运行时连接状态/现场认证/BS detected_test_app不进入保存配置摘要。
4. 探头/暗室、拓扑继续原保存端点，显示各自草稿/保存阶段；不一键保存，不自动同步，不跨HAL/DB事务，不改历史freeze或provenance。

## 全集与实现形状

| 改动 | 产生方与消费方 | 必须处理的对称路径 |
|---|---|---|
| savedConfigurationDigest | instrument API `_convert_category`/catalog及PUT响应；共享纯服务器helper；sync-current锁内重算 | selected model、endpoint/controller/notes/持久params、selected preset、driver mode、启用状态；null/损坏明确无可确认版本 |
| 同步确认请求 | lab_profile API request schema，GUI service与EquipmentManager确认窗口 | 缺失/畸形422、确认正确成功、保存后漂移409、目标Lab捕获、故障反馈和readiness刷新 |
| 分类激活重试 | 既有activateHALCategory端点 | 不PUT、不sync；成功/拒绝/inactive/simulated；旧编辑会话回调不复活回执；在途阻止Lab切换 |
| 子视图保存阶段 | ProbeManager和TopologyEditor既有dirty/mutation | 草稿未保存/保存中/保存成功/保存失败；保持原错误和入口，不复制配置 |

服务器摘要为canonical JSON SHA256；只从同一category/selected model/connection的持久配置计算，选中preset纳入校验。锁定对象使用populate_existing防旧identity-map缓存；不把updated_at（可能被连接观察更新）当保存版本。摘要为空时GUI禁止确认，服务器拒绝。确认请求字段为`expected_saved_configuration_digest`，必填。原endpoint/preset语义门先保留422，随后锁内比对保存版本（漂移409），再复用现有resolver与写操作。

## Task1：后端确认版本（严格RED→GREEN）

- [x] 保存配置摘要纯helper，目录及PUT输出同源；运行观察不改摘要，持久配置任一漂移改摘要，坏数据无摘要。
- [x] 真实API RED：缺确认拒绝；正确摘要同步；同端点但params/model/mode漂移409，旧binding保持；坏preset不给可确认版本。
- [x] 最小GREEN复用现有锁/解析器，不查询硬件，不新增数据库真值。

## Task2：GUI操作与子视图（严格RED→GREEN）

- [x] 当前保存配置可用且无草稿时，只重试分类HAL激活；既有保存仍save→activate。
- [x] Mantine确认窗口明示目标Lab、型号、endpoint、模式、服务器摘要；取消零写，确认只单PUT捕获目标与摘要，漂移错误清晰、不暗中重试。
- [x] 复用OperationalLabContext.beginWork阻止在途切Lab，registerSwitchGuard保护未保存编辑；不把同步/激活回执当正式资格。
- [x] 探头/暗室、拓扑独立阶段与未保存提示，原端点不变。内审后删除探头/暗室卡片拼接旧mutation终态的提示；当前阶段只说明草稿/服务器来源，保存结果保留对应操作反馈，避免旧Lab回执串入当前目标。

## Task3：契约四镜像与验证

- [x] live OpenAPI、api/openapi.yaml、generated TS、手写GUI类型与service同改。枚举所有sync-current调用并迁移为明确确认，旧测试setup补确认不改断言契约。
- [x] 真实App HTTP/WS隔离交互、受影响后端/正式消费者回归、最终全后端、GUI契约/build、compileall、单一Alembic head、diff-check。共享契约档，由主代理执行，reviewer复用结果不重复全量。
- [ ] 核心反例保护与恢复核对；独立只读功能内审，Ready PR，Codex R1→R2，覆盖最新HEAD无P1且合并条件通过才合并，同步/清理。

memory已轻量查询并以现代码复核；NotebookLM不适用（无仪器命令、范围、单位或前置条件改动）。不触碰现场API/硬件、不安装依赖。保留用户未跟踪资料。

## 验证记录（外审前稳定实现）

- 后端有效RED：`test_p2_83c_confirmed_sync.py`旧实现11失败；四镜像与坏preset各另1失败。最小修复后相关API/规则门106 passed。全后端6923 passed / 17 skipped（251.96s）。
- 真实App浏览器：`p2_83bEffectiveState.browser.js`保留B的12场景，增加分类激活重试和显式确认2场景，总14通过。HTTP/WS替换，不写现场库，不操作硬件。
- GUI完整契约291 tests / 282 passed / 9 failed；9项与B及main已有失败相同，不声明全绿。新service与子视图源码接线测试5 passed；子视图测试不是完整浏览器证明。
- 内审：先0 P1、1功能P2（子视图旧回执串目标），删除错误提示逻辑后增量复审CLEAN。该收口旧实现2 RED；没有增加全局回执机制。
- compileall通过；单一Alembic head实际为`c1e3f5a7b9d2`，本片无migration。完整命令/末尾输出与build结果随PR台账保留，不以历史head编号代替当前输出。
- 最终production build通过（12.35s）；内审提示收口后的真实App重新运行14场景通过。源码层阶段测试只保护接线；不冒充现场或完整子视图浏览器验收。

## Codex R1收口

PR #507 R1覆盖`d1c82c8d`，无P1、1条功能P2（inline4195770469）：分类激活重试未刷新同抽屉的channelModels/topologyProfiles缓存。最小修复将目录/HAL/readiness失效统一至onSettled，并按请求捕获类别补齐两卡真实queryKey，成功和失败均刷新；没有新状态机制、PUT或sync。旧实现接线断言RED；修复定点14 passed，真实App14场景通过，production build11.83s，增量只读复审CLEAN。后端与OpenAPI输入未变，复用同输入的全后端结果；完整GUI292 tests/283 pass/9既有失败。R2实际覆盖/结论和合并记录在PR台账维护，不为填审查时间新增提交。
