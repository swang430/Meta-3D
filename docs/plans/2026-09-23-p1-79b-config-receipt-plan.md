# P1-79B BaseStation 配置回执实施计划

**目标：** 让配置回执只要求独立仪表控制字段的权威确认，解除描述字段导致的恒假，同时不放宽任何硬件控制量。

1. 在 `test_p1_73b_cmw_state_machine.py` 和共同回执测试中增加 RED：完整 CMW500 控制字段回读应确认，回执不得包含 `radio_technology`、`channel_kind`、`frequency_mhz`。
2. 增加反例 RED：任一控制字段缺失/错配、错误队列拒绝仍未确认。
3. 最小修改 `BaseStationRequestedConfig.receipt_payload()`，以显式常量/分类排除三个冻结描述字段；保持其余生产路径不变。
4. 更新受影响的 UXM/CMW 合同测试与文档镜像；不修改 manifest 能力声明。
5. 运行定点、受影响链、全后端、compileall、Alembic head、diff-check。
6. 做独立 fresh 功能内审；P1=0 后提交、推送、Ready PR，执行 Codex R1→R2；最新 HEAD 的 R2 无 P1 后合并并同步 main。
