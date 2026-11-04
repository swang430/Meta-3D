# PC-07A 独立校准审计包

基线#559 `df87ecef`，继承整体设计§9.3与连续开发授权，WIP=1。当前报告仅保留run/交换索引指针，审计人员无法在报告入口取得关联原始采集；不改变已有正式报告结论与文件。

## 四行契约

来源：原报告关联的单次MIMO执行快照、冻结来源及其指向的DiagnosticRun.sequence_evidence；不读当前LabProfile/采用指针，不下发仪器命令。
范围：现有报告详情新增独立JSON审计导出；复用原报告读取资格门、现有FixedRouteResult/RouteApplicationRecord模型和原始记录，不新建测量算法/资格规则。
不做：不改原PDF/content_data，不把当前取回的记录说成归档时已内嵌附件；不把新算hash当历史防篡改签名，缺失/跨lab/身份冲突明确不可关联。
验收：原始功率样本/交换、原参考修正声明、冻结净损耗与应用位置同包；后来配置/选用变化不改原来源，撤销后可导出但始终非正式审计；未知旧源不补真。

## 方案与全集

- GET单个报告的calibration-audit，只有关联唯一MIMO执行且原读取资格门通过才可使用，其他报告400，未找到404；旧不可信报告沿原409。不是PDF下载门的绕行，包标识calibration_audit、formal_eligible=False，含当前撤销投影。
- 包含原报告内容与实际应用追溯快照、导出时间及逐来源可取得状态。confirmed_route来源用原snapshot中的lab/run/source身份定位唯一保存记录；原执行id也必须匹配。legacy及不完整来源保留原快照但不找相似/最新记录替代。
- 原始采集先按既有FixedRouteResult验证结构，核对run/lab/链/方法/频率/净损耗、原选择与参考修正声明。仅标为“可取得且身份关联”，不重新解释SCPI或升级real/资格；原始sequence_evidence逐字数据透传，附此次取回内容hash及“非原始签名”说明。索引越界/错误lab/不一致时不附不相关内容。
- 原采集samples/exchanges、request参考修正与missing_items、原来源coverage/reference、原执行applied/selected/value/reference_plane构成审计账目；没有完整预算的仍明确unknown，不造不确定度数字，不外推频率或空间覆盖。
- GUI只在按reportId成功载入的详情显示“导出校准审计包（非正式报告）”，直接contentData无真实报告id不显示；错误可见，忙时禁重复，文件由既有axios连接取得。
- 所有入口枚举：报告list/detail/generate/download保持#559边界；新增audit只读，无写SQL、无迁移、无仪器；API/schema/YAML/生成TS四镜像，GUI封装/详情消费者。原始记录唯一存储仍是sequence_evidence，不复制持久化表。

NotebookLM不适用：不新增SCPI、仪器单位/返回解释或计算公式，只关联已定义模型的保存原文；若实施需要解释新仪器语义，另行查证而非猜测。

## 验证

先RED真实HTTP导出与关联身份负例，独立内审；生产字段/资格/响应共享变化档，相关报告与撤销回归、四镜像、GUI构建、浏览器实际点击与文件取得，稳定生产输入最终全量。R1/R2外审与按SHA合并；用户运行服务/数据库保持原版本。完整现场计量预算与B资格不由软件片关闭。

## 实施验证（2026-11-04）

本片无数据库迁移，用户运行服务保持`7f5bb56b`。本地验证使用隔离SQLite/模拟仪器，浏览器HTTP边界替身不代表真机或现场认证。

- RED：仓库根目录 `DATABASE_URL=sqlite:////tmp/pc07audit-red.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. api-service/.venv/bin/python -m pytest api-service/tests/test_pc07a_audit_evidence.py -q --color=no --log-cli-level=WARNING`，6 failed/129 warnings/15.47s，exit1，`/tmp/pc07audit-red.log`。
- 内审修复：Axios改为保留服务器原始text，仅JSON.parse副本核对，避免重新序列化把2595.0改2595导致内容hash失配；参考声明改为复用原`_application_scope`完整比较，包含分析仪绑定。新增对应负例，无新测量算法/资格。
- 自查与内审确认旧异常标识会使整包400，实际HTTP RED1 failed/58 warnings/3.14s，`/tmp/pc07audit-legacy-red.log`。三个摘要标识仅接受字符串，否则None，异常原值仍保留traceability，不作替代查询；修后真实HTTP通过。不是以捕获异常补真。
- 最终相关：api-service目录 `DATABASE_URL=sqlite:////tmp/pc07audit-final-v2.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc07a_audit_evidence.py tests/test_pc07a_revocation_impact.py tests/test_pc07a1_report_traceability.py -q --color=no --log-cli-level=WARNING`，**36 passed/622 warnings/91.89s**，exit0，`/tmp/pc07audit-related-final-v2.log`。
- 逆变异：仅去掉采集净损耗与冻结来源一致性判据，运行`test_unrelated_or_corrupt_capture_is_not_attached[net_loss]`，1 failed/57 warnings/3.12s，exit1，`/tmp/pc07audit-mutation.log`；finally原文逆替换并assert恢复。后续只收窄异常摘要标识，该核心判据未改。
- GUI `npm run openapi:generate`及`npm run build`通过，Vite built in23.22s，`/tmp/pc07audit-build-final.log`；初次类型别名少import导致构建失败已修正，未隐去。API/schema/YAML/生成TS四镜像通过真实契约测试。
- 浏览器真实ReportViewer：首次503显示失败，重试实际下载`calibration-audit-audit-report.json`，276字节隔离响应已解析核对audit_kind/formal_eligible=False/缺材料null；直接contentData路径无导出按钮。`output/playwright/pc07-audit/download-view.png`已视觉检查，下载文件在同目录；仅HTTP边界替身，真实API行为由上述后端测试独立覆盖。临时入口已移出工作树、浏览器及5178独立服务关闭。
- 初次全量在自查旧异常标识问题后主动中止：4368 passed/5 skipped/3825 warnings/151.49s，exit2，`/tmp/pc07audit-interrupted-full-final.log`。生产变化后重新完整执行，未拿中止结果收口。
- 最终完整全量：api-service目录 `DATABASE_URL=sqlite:////tmp/pc07audit-full-final-v2.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，**6 failed /8569 passed /17 skipped /11195 warnings /1236.64s**，exit1，不称全绿。`/tmp/pc07audit-full-final.log` SHA256 `a5c1d1338dbde2d80ebfca2b52e66f231abd6d316d1146cedceefd9682e223b2`。
- 1433非docs输入起止hash一致；`/tmp/pc07audit-all-inputs.json` SHA256 `4e3c5676b2b4cafbedfa19142ad19b35039a9dd49ad1ea7cccc4b7431d43602f`。六项失败集合与#557[基线清单](2026-11-04-pc05a-target-applicability.md)完全相同，四契约镜像/G8/G11历史文档；#559的时间字段适配在本轮全量已通过。

本片导出材料仍可能缺失，并无历史防篡改证明或完整计量预算。提供原保存证据不等于独立现场参考验证；PC-07B和正式资格不关闭。
