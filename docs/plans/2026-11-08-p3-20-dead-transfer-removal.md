# P3-20 失效数据搬运方法清理

用户于2026-11-08批准上一轮提出的连续维护方案；本片采用删除无调用旧方法的推荐方向。

## 契约与影响全集

- 问题：CalibrationOrchestrator末尾两个数据搬运方法读取已删除逐探头字段，误用会失败或授予不实的新有效期。
- 只删除该类export_calibration_data/import_calibration_data及仅它们使用的timedelta导入，不增加替代机制。
- git grep逐个核对同名项：path_loss_calibration API调用CEInternalCalibrationService.import_calibration_data；CalibrationReportGenerator有自己的export方法，均保留。编排器两方法无实际调用方。
- 不改数据库、活API、现行审计包、校准生成/补偿及仪器行为。历史设计/发现记录保持原文。

## 前置与验证

memory检索未找到针对这两个方法的额外决策，当前roadmap优先。NotebookLM不适用：无SCPI或仪器语义变更。
局部删除档：静态调用全集、模块编译与相关编排器回归；不新增仅断言代码不存在的测试，不触发全后端。

验证命令：`DATABASE_URL=sqlite:////tmp/p320-isolated.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=api-service api-service/.venv/bin/python -m pytest api-service/tests/test_path_loss_calibration.py api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py api-service/tests/test_p1_70_channel_validation.py api-service/tests/test_channel_model_real.py -q --color=no`。退出0，结尾：`====================== 131 passed, 654 warnings in 6.96s =======================`。同版本源码AST解析及diff-check通过。
