"""ProbePattern import: vendor datasheet → ProbePattern row.

业界常态是探头厂商出厂带 .cut/.swe/CSV pattern 数据, 实验室一次性导入,
12-24 个月有效期。本子包是 Phase 2a-import "Path A" 的实现。

Path B (转台实测) 走 app/api/probe_calibration.py 的 /pattern/start 端点,
不在本包范围。
"""
