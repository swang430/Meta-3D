# PC-04A 修订回退：恢复原可编辑射频拓扑

## 用户决定与范围

用户明确批准撤销PR #528，再在改动前的原编辑器上增加校准。此片只完成第一步，不在错误界面上继续打补丁，不提前开始第二个开发项。

- 对merge `d44cab41579f4340701393ecf086e87b6c4bd60e`执行`git revert --no-commit -m 1`，不reset主目录、不改已合并历史、不强推。
- `api-service`、`api`、`gui/src`逐字恢复到#527的`192dd9d02bdcade9ad2aa51ff473b26d47ceb3c7`，原拓扑的节点、连接、编辑与保存逻辑均不改写。
- 保留#527自动采集/取消/共享证据能力，撤除#528新增的只读替代图与参考选择接口；数据库无迁移、不删除任何采集记录或旧参考元信息。
- 总览暂时恢复改动前的校准入口。这是用户批准的回退中间状态，不是重新认可独立表格作为最终体验。
- 用户主目录未提交的规则及仪器资料保留；验证只用独立SQLite、全Mock服务，不重启用户现有API、不接现场仪器。

## 失效原因和保护

#528默认进入一张新只读图，禁止拖动和连线，编辑器藏在另一入口后面；采集历史错误也会阻断那个入口。此前验证只检查能切进编辑界面，没有实际拖动和保存。

新增`gui/test/topologyEditing.browser.js`，走真实浏览器、真实前后端，先在#528看到“默认只读图，原拖动/编辑画布不可直接使用”失败，再回退验证：

1. 默认就是原编辑器，没有替代只读图。
2. 实际鼠标拖动节点，页面标记草稿未保存。
3. 在连线上操作打开原参数编辑面板，修改并应用。
4. 保存后由服务器回读节点位置和连接参数。
5. 刷新页面仍保留参数且能够再次编辑。

原版是单击连线触发参数面板；本片不凭用户描述额外制造新的节点双击编辑机制。脚本在真实连线非标签位置操作，不使用force或派发DOM事件绕过鼠标命中。测试数据的节点位置仅在临时数据库布置，不写用户拓扑。

## 验证责任与记录

主代理负责最终验证；独立内审只读核对恢复全集和共享历史，不重复全量。
回退撤除共享响应字段，按共享契约档做最终后端全量一次；GUI契约/build及实际交互必须重新验证，不把旧版输出称为本次结果。NotebookLM不适用：没有新仪器命令或量值解释。

证据目录：`/Users/simon/.codex/artifacts/restore-topology-20261024`。

- 恢复全集：`git diff 192dd9d0 --exit-code -- api-service api gui/src`，退出0。
- GUI：`npx --yes tsx --test test/*.test.ts`，182 passed / 0 failed。
- 构建：`npm run build`，成功13.72s。
- 原拓扑浏览器：`playwright_cli.sh -s=restoretopo run-code --filename=.../gui/test/topologyEditing.browser.js`，`browser-final.log`的实际Result为**5 passed**，节点位置由`(30,60)`实际拖到`(72.2992700729927,87.27189781021897)`；连接损耗1.25由服务器回读并刷新保持。
- #527浏览器：运行原`gui/test/pc04FixedRoute.browser.js`，`acquisition-browser.log`实际Result为**8 passed**，包括真实POST/数据库记录、模拟无实测、取消、历史、跨实验室及共享完整证据。运行编号`10053271-9f85-412d-a37a-8908a6bf5931`、`802e1bc3-29d7-4b77-920c-33d2cb7d217a`。
- 受影响后端：`.venv/bin/python -m pytest tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_p2_28_diagnostic_sequence_evidence.py tests/test_rule_gates.py -q --tb=short --show-capture=no -o log_cli=false`，**107 passed in23.88s**，`affected.log`。
- 最终全后端：`.venv/bin/python -m pytest tests -q --tb=short --show-capture=no -o log_cli=false`，**1 failed,7177 passed,17 skipped in293.40s**，退出1，`backend.log`；唯一失败为下述已在main独立复现的日期样本，不宣称全绿。运行期间生产/测试/生成契约输入未改，仅补非测试输入文档和独立浏览器脚本。
- main独立复现：`tests/test_p1_64_quiet_zone_evidence_truth.py::test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown`，**1 failed in0.08s**，`expired != valid`，`main-date-baseline.log`。
- compileall、单Alembic head `c1e3f5a7b9d2`、diff-check通过；无迁移。独立内审功能CLEAN，未重复全量。外审/合并的实际状态以本片PR为准，不为回填完成时间额外制造一轮新提交。
- 已知日期fixture在main过期，不放宽生产有效期规则来让测试变绿。

## 后续施工约束

回退PR完成内审、Codex R1→R2、合并、main安全同步与清理之后，才开始第二片。
第二片在**同一张原可编辑拓扑图**增加通路选择、测量侧栏和结果，不替换原节点显示及交互、不做另一张默认只读图。
实测经操作员确认后应更新该通路后续测试真正使用的校准值，保留旧值及适用频率/端口/探头；不能把整条路径量值写成单段电缆再重复叠加。执行消费的具体落点需在第二片动手前追全，不把“选了参考记录”冒充实际应用完成。
