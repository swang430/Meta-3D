# PC-05A 目标频点逐链选源预览

按已批准总设计§5.3与用户连续开发授权推进；基线#556 `44b4b50d`，WIP=1。现有HAL摘要只反映绑定证书期限，不能回答本次目标频点各条链是否有可选净损耗来源。本片新增精确目标查询，供PC-06工作台消费；不改仪器或历史。

## 边界与生产关系

- GET实验室的route-calibration-availability，明确frequency_mhz与operating_mode；缺少/非正/非有限频率拒绝，不能默认成“某个常用频率”。
- 直接消费现有 `resolve_effective_route_compensation` 的选择结果，不复制条件。返回逐链source_kind/id、value_db、provenance、reason和选源计数/时间/警告。
- `all_chains_have_sources`只表示非空目标链集合全部有来源；不是完整带宽/空间/不确定度已覆盖。`formal_scope_status`固定unknown，明确不是认证或放行硬件执行的门。相同参数、相同数据库下与执行冻结所选来源一致。
- 当前查询不获取执行提交锁；解析器增加仅内部使用的 `lock_sources` 参数，默认True，GET显式False。正式冻结保持默认True，#556事务排序不削弱。GET不写库；并发变更可能令预览过时，执行仍重新检查/冻结。
- 原HAL绑定证书期限摘要保留其独立含义，不将它当这次目标适用性；GUI整合/解释在PC-06。此片不因配置差异自动失效来源，沿既有物理链/频点判据。

## 实施/验证

四镜像schema/API/YAML/生成TS及API导出同步。测试先RED：无来源、精确新采用、撤销后缺口、旧独立来源、不同频点、缺失/非有限参数；真实HTTP响应与创建冻结对位，GET无写语句；原撤销并发测试保持通过。接口不接受客户端校准结果或资格。

共享解析器与新增契约功能档：相关回归、真实序列化、build、稳定输入最终全量（主代理唯一执行），独立内审、R1/R2、按SHA合并。NotebookLM不适用：无SCPI/仪器语义改动，选择范围来源为已批准设计；memory及目标禁令已核对。

范围：route_calibration API/schema、route_calibration_freeze解析器、契约镜像/类型、新测试、本计划与roadmap。不改采集、撤销记录、历史报告或质量政策，不新增第二套选择引擎。

## 2026-11-04 实施验证

基线#556 `44b4b50d`；测试使用隔离SQLite和模拟仪器，未迁移用户数据库，主目录运行服务仍在`7f5bb56b`。

- RED：api-service目录 `DATABASE_URL=sqlite:////tmp/pc05target-red.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc05a_target_applicability.py -q --color=no --log-cli-level=WARNING`，接口未实现时2 failed / 59 warnings / 4.19s，日志`/tmp/pc05target-red.log`。
- 相关：相同环境、数据库`/tmp/pc05target-tests.db`，`pytest tests/test_pc05a_target_applicability.py tests/test_pc05a_revocation.py tests/test_pc04a2_route_freeze.py -q --color=no --log-cli-level=WARNING`，32 passed / 401 warnings / 50.07s，exit0，`/tmp/pc05target-related.log`。
- 逆变异：仅将GET调用的`lock_sources=False`改为True，上述测试模块的`test_target_preview_matches_execution_sources_without_writes`失败，1 failed / 52 warnings / 3.00s，exit1，`/tmp/pc05target-mutation.log`；finally双向assert恢复。原撤销并发测试在相关回归及全量中通过。
- GUI目录 `npm run openapi:generate`及`npm run build`：exit0，Vite built in20.25s，保留chunk大小警告，`/tmp/pc05target-build.log`。
- 最终全量：api-service目录 `DATABASE_URL=sqlite:////tmp/pc05target-full-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，**6 failed / 8545 passed / 17 skipped / 10835 warnings / 1121.78s**，exit1，非全绿。日志`/tmp/pc05target-full-final.log` SHA256 `838a25ee1ff73815e8b98c945c15ea59f9abb81314ba97cbcb9de3f499547335`。
- 1425项非docs输入前后hash未变，清单`/tmp/pc05target-all-inputs.json` SHA256 `1d16396f27d6d1b095f1fc06daf8d5aafb4d260269c2280dc4b1811351178bfa`；全量期间未编辑文件。

六个失败nodeid与基线#556最终全量完全相同；此前在未改主目录`7f5bb56b`也逐项对照同红，命令及原因见[撤销片验证记录](2026-11-04-pc05a-revocation.md)。本片不把已知失败当作全绿，也不修改无关门：

1. `tests/test_pc04a2_gui_contract.py::test_topology_calibration_public_schemas_and_routes_match_live_openapi`
2. `tests/test_pc04a4a_nominal_properties.py::test_checked_crud_and_schema_closure_match_live_contract`
3. `tests/test_pc06a1_batch_api.py::test_batch_contract_models_live_and_handwritten_openapi_agree`
4. `tests/test_pc_04a_fixed_route_api.py::test_live_checked_openapi_and_generated_types_cover_all_pc04_routes`
5. `tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes`
6. `tests/test_rule_gates.py::test_g11_docs_cite_live_api_routes_full_domain`
