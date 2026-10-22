# PC-01A 实施与验证计划

基线：v0.9.2 / cac09bfa。WIP=1，分支 codex/pc-01a-caict-calibration-scope。
设计：../design/2026-10-21-pc-01a-calibration-scope.md。

1. 服务/API RED：真实 SQLite LabProfile+拓扑，经 HTTP 取范围；缺失输入、逐链口变化、改名/顺序不变化、跨 lab、损坏 baseline、未知实物身份和无写入。
2. 最小 GREEN：新增白名单只读快照服务、schema 和两个路由；不改原 resolver/校准执行链。
3. GUI：原总览新增配置盘点卡、逐链表、保留与比较；服务端摘要/影响清单；切 lab、错误/暂停、过期响应保护。
4. 同步 live OpenAPI、checked YAML、generated TS、手写类型；GUI 契约与 production build。
5. 比例验证：本片与 LabProfile/resolver 相关测试；共享 API 契约最终后端全量，由主代理执行。compileall、单 Alembic head、diff-check。独立 reviewer 只读检查，不重复同输入全量。
6. 独立内审后 Ready PR，核 HEAD 走 Codex R1→R2；R2 无 P1 收口，否则仅修 P1 续审。合并后 ff-only main、清理本片工作树/分支。

校准资格、现场验证不因本片完成而解除。验证输出和审查请求/结果写入 PR 台账，不为填写外审时间另造需重审提交。

## 实施记录

- 原入口 6 RED（404/缺响应）→6 GREEN；扩大新增保存资源/路径器件验证后，93 passed。
- 首次内审发现范围白名单漏 transport/器件声明、旧比较覆盖新查询两条 P1；补全现有声明，比较不再写查询缓存，完成后重新读取且摘要一致才展示结论。
- 补充 transport 与 Probe 声明反例 5 RED，修复后本片13项及既有 LabProfile/resolver/rule gates 合计98 passed。
- 首次全量为内审前输入，收到功能修正后主动中止；修正后重新执行最终全量，不把中间结果称为最终通过。
- 实际 CAICT 数据在 READ ONLY 事务经同一服务取数：32条链、32条Probe声明、7条历史binding，3条停用明确提示；formal_eligible=false。没有 HAL I/O 或数据库写入。
- OpenAPI 只更新本片2个路径与6个依赖schema，live/checked结构完全一致，再由checked生成TS；不把既有其它路由差异捎入本片。
- API→浏览器整数值浮点往返补充1 RED→GREEN：规范化 JSON number 后，本片14项及相关链共99 passed。实际CAICT只读快照经 Node JSON.parse/stringify 再交服务器比较也无差异。
- GUI服务契约3 passed；真实App本片8 passed（含延迟比较/失败/切Lab），原LabWorkspace14 passed、零配置写入；production build通过。最终后端输出及外审台账随PR记录。
- 最终默认全后端：7083 passed /17 skipped /1 failed（177.65s）。唯一失败为原有 `test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown`：固定 valid_until=2026-10-23，当前进入 expiring_soon 窗口，却断言 valid。原main cac09bfa同一测试独立复现相同失败；该测试与生产状态判据本片均零diff。按测试意见P2上限记录，不把结果称为全绿，不为日期夹具更改正式校准状态。
- PR #522 的 Codex R1 覆盖 ecc99436：P1（inline4337106141）单链变化被拓扑镜像扩大成全链、P2（inline4337106151）器件声明只有hash不可读，均已核实并严格TDD修复。旧版5 RED；本片20项及相关链105 passed，新增共享器件/删除连接对称验证；独立增量复审CLEAN。
- R1修复后的最终全后端：7089 passed /17 skipped /1 failed（174.48s），仅上述已在原main复现的日期夹具失败。GUI/schema没有变化，其有效构建、交互和镜像验证按输入一致复用；compileall/diff-check通过。后续R2结果在PR原地台账维护，不为完成时间新增提交。

## 操作术语修正

用户确认将保存配置语境的“范围”统一改为“配置”：配置盘点、重新读取配置、保留配置快照、比较配置变化。内部接口标识与专业频率/校准适用范围不改，不改硬件或比较行为。

验证按局部文案档：既有浏览器用例使用新操作名，在旧UI因“保留配置快照”不存在而RED；文案更新后8 passed，服务契约1 passed，production build通过（12.45s，原有bundle大小告警保留），diff-check通过。最终改动未涉及后端/契约，不重复全后端。日志为本机 `/tmp/pc01a-wording-{red,green,unit,build}.log`，外审状态在本片PR原地维护。

## 2026-10-22 复核决策边界与绑定提示

用户批准：配置变化只提醒复核，重校准由操作员判断；不因配置差异自动改变就绪/资格。同步本片设计、整体设计§5.4和PC roadmap，保留独立安全/兼容/证书与必要数据规则。盘点结果仍只由GUI消费，不接readiness或执行门。

局部修复只拆分告警：类别查不到显示已不存在；类别存在但is_active=false显示仪器名称/类别/ID及已停用。保持原配置盘点完整性、正式资格和漂移提示，不写数据库、不启用仪器。真实HTTP入口两例在旧实现2 RED，最小修复后本片+RF resolver+rule gates共99 passed（5.43s）；compileall、diff-check通过。无schema/GUI/依赖或共享执行行为改变，不重跑全后端/GUI构建。证据 `/tmp/pc01-review-warnings-{red,green}.log`，外审台账在PR维护。
