# PC07A1 全量发现的两项有限修复

## 输入、范围与根因

- 基线 `0f7d69434158c6d90c0236a7f29f80662cec04c8`；本次只有 PDF 短参数缺值展示和两份验证报告归档位置纠正。不重做 Task3，不改 JSON 真值、数值 0、资格门、`.gitignore` 或 rule gate，不 push。
- 主代理唯一全量在该基线已 RED：`/tmp/pc07a1-final-0f7d6943.log`，exit 1，`2 failed, 7466 passed, 17 skipped, 7289 warnings in 587.84s`。本任务读取并复用这条原始失败证据，没有重跑全量，也不宣称修复后全量通过。
- PDF 根因：`executors/report.py::_calibration_traceability_parameters` 在渲染前用 f-string 把 None 转成完整字符串中的 `None MHz`/`None`，使既有 PDF 缺值处理无法识别原 None。
- 归档根因：已跟踪的 Task1/Task2 报告处于 `.superpowers/sdd/.gitignore` 的 `*` 之下。守门失败真实有效，不能用放宽忽略规则或修改守门断言解决。

## 最小修复与消费全集

1. 仅短参数函数引入 None 专用展示格式化：None → `—`，非 None 使用原值字符串表示，不用 `or` 抹掉 0，不回写输入。
2. 枚举该函数新增短参数的 13 项消费：执行频率；链 ID、来源类型、来源 ID；应用状态、方法、参考面、认证资格；来源频率、前序、来源名称；采集 run、交换索引。全部在拼接前格式化。唯一生产调用方仍为同文件报告 builder 的参数构建，JSON 投影生成路径未变。
3. Task1/Task2 报告从 Git 跟踪位置移至本目录；原 `.superpowers/sdd/2026-10-25-pc07a1-calibration-traceability/task-{1,2}-report.md` 文件均保留本地，只从索引移出，未删除证据。
4. Task1 原文逐字保留；Task2 仅把“同目录 brief”明确为实施时本地 scratch 的完整坐标，不改历史数值/统计/结论。实施计划增加本目录两份归档链接。新路径不被 ignore 命中；原本的忽略规则和守门代码均未改。

## RED / GREEN

所有 pytest 工作目录为本工作树 `api-service`；显式临时 SQLite、全 Mock、`BOOTSTRAP_ON_STARTUP=true`。日志由原 conftest 独立隔离。

新增定点 RED：

```sh
env USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-pdf-null-red.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc07a1_report_traceability.py -k short_traceability -q -o log_cli=false --tb=short
```

exit 1；`1 failed, 12 deselected, 40 warnings in 0.09s`。失败为实际短参数仍含 None，不是 import/fixture 错误；日志 `/tmp/pc07a1-pdf-null-red.log`。

修复后相关 GREEN：

```sh
env USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-pdf-null-green.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_p2_21_report_flags_cert_cjk.py tests/test_rule_gates.py tests/test_pc07a1_report_traceability.py tests/test_pc07a1_calibration_traceability.py tests/test_mimo_ota_report_verified_backcompat.py -q -o log_cli=false --tb=short
```

exit 0；**171 passed, 532 warnings in 78.05s**。日志 `/tmp/pc07a1-full-failures-related-green.log`。包含原来两个失败文件的完整测试、新增全字段缺值/0/JSON 不变断言，以及原 PDF 实际渲染、PC07 报告关联可信门与旧报告兼容性覆盖。

验证运行输入为基线加本修复，写入本说明前的精确 Git 索引树为 `95ed325b59e501beb4bdf26d7b23e30a5ccd45f2`；运行期间代码/测试未再修改。随后只新增本报告，不改变运行输入。代码/测试 SHA256：

```text
0417dfaf79ffdd8e3936cdcdfb351c477f85c0605d8c0f2c2cd3e1da226af0f3 api-service/app/services/mimo_ota/executors/report.py
63327b3f5fbd1c21d940df170d061f93dbbb6f4fc2fd4f880b775f467269176a api-service/tests/test_pc07a1_report_traceability.py
```

`git diff --check` exit 0；Task1 scratch 与归档 `cmp` exit 0；新归档路径 `git check-ignore --no-index` exit 1（未被忽略，符合预期）。没有删除或覆盖原全量、scratch 或浏览器证据。

## 自查与后续

执行者顺序自查，非独立内审；没有派子代理/审查者，没有全后端或硬件验证。主代理随后安排独立增量复核和唯一修复后全量，旧全量结果不得归到新提交。
