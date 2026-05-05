"""TRP (Total Radiated Power) test_type schema.

3GPP TS 38.521-2 / CTIA OTA Test Plan §A.6 定义的整机辐射功率测试。
DUT 在转台上以 UL grant 向 BS 发射, 信号分析仪在球面网格上扫描接收
功率, 积分得到 TRP (单位 dBm)。

Phase 3a (2026-05-05): 第二个使用 TestCase.configuration JSON 路径的
test_type, 用来验证 RECONCILIATION NOTE 命名约定经得起新场景。
"""
