# P3-21 UXM诊断前置错误队列

## 获批范围与具体故障

用户批准连续完成P3-21。两条既有诊断uxm_config_truth_probe和uxm_manual_spelling_probe各自硬编码查询并读取最多100条；达到上限却没读到0仍继续，前者可能继续ARFCN写操作。方案：抽取共同有界读取，查询换源当前profile.ERR；仅明确0后继续。空/畸形/异常/上限/连续相同-113均拒绝。后续单次错误检查也换源profile。保留原始回复和失败原因，不新增命令或正式资格。

共享函数用于替换两份循环，不增加后台任务/状态缓存/自动重试。重复-113停止是应用层保守规则，不声称设备不支持。漏判停止仅使诊断提前结束，误放行会把旧错误错误归属后续命令并允许写动作，因此保守拒绝。

## 全集与边界

两条原循环及各自后续单次错误读取为本片消费全集。RealUxmDriver._drain_errors保留正式业务契约；uxm_scpi_compatibility负责不同逐命令探测，原有_parse_err复用。其他F64/FSVA队列不改。existing测试中的UXM fake接受profile长形式；F64 fake不改。

## 前置证据

memory检索未有本片特定新增决策，以当前规则与原发现为准。NotebookLM 2026-11-08 conversation adfb5e02-4f11-450b-a91d-801d22667604；并对照本机手册提取原文：UXM5G_SCPI_03_LTE.md，LTE System > App Info > System error queue，Section PD 1.9.1：空队列返回 +0,“No error”；Application Mode仅列NSA/SA，不据此推断IRAT。General > Miscellaneous commands指出每读一次弹出最旧错误。裸0并未由该原文证实，本片复用原诊断解析器仍需带逗号消息；不扩展为裸0。既有方言查询只保留诊断用途，不证明正式支持；P2-52/54仍待匹配资料。

## 验证

隔离SQLite、USE_MOCK_INSTRUMENTS=true，无真机访问。新双入口反例首次6 failed；修后相关三文件205 passed /39 warnings /0.47s。取消上限失败的变异被新用例抓到，finally双向核对恢复。因涉及前置保护，恢复后单次最终后端全量已完成，结果见下文。

最终全量：api-service目录 `DATABASE_URL=sqlite:////tmp/p321-full.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING`，8617 passed /17 skipped /6 failed /11381 warnings，1207.75s，退出1，不称全绿。最终失败为：test_pc04a2_gui_contract的public schemas、test_pc04a4a_nominal_properties的schema closure、test_pc06a1_batch_api的contract models、test_pc_04a_fixed_route_api的generated types、test_rule_gates的G8/G11路由文档门。六项均在未修改main@1184d869、同虚拟环境、各自新SQLite中定点复现相同错误，日志/tmp/p321-baseline{,2,3,4,5}.log；不是本片引入。无新增失败归因已通过受影响输入隔离与主线对照核实，不解释为硬件结果。

定点命令为同环境 `python -m pytest api-service/tests/test_p3_21_uxm_diagnostic_queue.py api-service/tests/test_f64_state_machine_sequence.py api-service/tests/test_uxm_kpi_readback_sequence.py -q --color=no`（仓库根目录，PYTHONPATH=api-service）。独立审查功能CLEAN，额外8项假驱动边界检查通过；测试后源码/测试未变，仅补本文档。
