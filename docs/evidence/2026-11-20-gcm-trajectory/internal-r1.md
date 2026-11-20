# 独立内审：2条功能发现

审查档位：全套。累计基准4d8fac47，范围为轨迹脚本、测试、五份样本材料及实施说明；未修改工作树文件。主代理要求所有结果只写文件，已遵守。

## F1 [P1] 输出时间没有核对实际来源时间，已核验的源时间被包装层静默替换

- 文件：scripts/gcm_trajectory.py:156–157（相关来源比较在102–109）。
- 失败场景：三份实际材料保持原样；model.common.TIMESTAMP仍为来源导出时间15:02:33.324。只把wrapper的time_seconds改成0、2、4…74并重绑身份文件，即成功输出末帧00:01:14.000，清单还称74为original_time_seconds。源文件时间与输出矛盾未拒绝；当前正例本身所有model来源时间相同，而wrapper已有38个不同时间。实际证据比对通过后立刻覆盖它，不能证明保留了原始非均匀时间，也使独立来源中的帧时序无法核对。
- 修法形状：换判据来源。
- 建议方向：原始精确时间和原始帧索引应来自实际读取的逐帧来源记录，并与wrapper逐项核对；CSV毫秒时间从该已核验值派生。如果来源TIMESTAMP采用绝对钟时、精确秒采用相对时间，必须有来源绑定的明确起点换算，不能无条件覆盖。
- 实跑证据：/tmp/gcm-trajectory-review-probe.py及/tmp/gcm-trajectory-review-probe.log。输出：source_timestamp 15:02:33.324 output_timestamp 00:01:14.000 claimed_original_seconds 74。这是功能数据错误，不是测试建议。

## F2 [P2] 十进制半入运算受默认28位上下文影响，长精度输入会取错毫秒

- 文件：scripts/gcm_trajectory.py:45。
- 失败场景：允许的原始字符串1.0004999999999999999999999999999999999应向下取成1000ms，但seconds*1000先被默认Decimal上下文舍入，实际输出1001ms。此实现会在调用方修改Decimal全局上下文时进一步受影响。
- 修法形状：收窄过宽的条件或换计算来源。
- 建议方向：使半入换算对输入十进制位数保持精确（局部精度从输入长度确定，或用整数十进制位计算）；不要依赖进程全局Decimal默认精度。
- 实跑证据：同一probe日志的round_actual为1001，使用70位局部精度的独立复算round_expected为1000。

## 验证

- 命令：PYTHONPATH=/Users/Simon/Tools/MIMO-gcm-frame/scripts python3 -m unittest discover -s scripts/tests -p test_gcm_trajectory.py
- 实跑输出：Ran 14 tests in 0.275s / OK，见/tmp/gcm-trajectory-review-tests.log。单帧最新_convert已允许真实类别，本轮没有此前依赖门错误。
- 核心保护变异：只在临时目录副本删除生命周期固定槽位门，anchor命中断言一次，14项测试出现1失败（slot_change）；源文件前后字节一致。日志/tmp/gcm-trajectory-review-mutation.log，source_unchanged True。核心固定身份保护有效，无测试缺陷意见。
- 本轮读取脚本内容SHA256：6d8519042189913b56911c6f8944ae0ebd2b90fa2e60aebb17c4ce4db2c048b4（若主代理继续编辑，以实际最新内容复审）。
- 独立离线脚本未接生产后端、GUI、API或共享契约；后端全量及GUI构建不适用。未启动任何应用、网络连接或硬件。

## 域枚举与失败方向

CLI与convert_trajectory共用同一转换入口；来源文件/身份文件从_load_bound进入_verify_evidence，批次、方向、帧ID、原始逐径、最终成员和簇导出均有显式比较；持续簇标识、槽位、成员分别由映射消费并输出CSV和清单。真实与合成仅在单帧数值转换入口有分支，二者此前同走材料核验。下载/历史重算/报告/KPI没有新增消费者。未知、文件缺失、摘要不符、映射缺项默认拒绝；不调用HAL。出生消失与槽位数变化拒绝，不虚构功率。坐标0.3m和25波长门有明确手册出处；时间§13.2.2厂商后续可能调整已如实说明。

## 可考虑的改进（非缺陷，本轮不实现）

无。

状态：独立内审完成，待主代理处理F1/F2并对最新脚本做增量复审；不得把本报告称为CLEAN。
