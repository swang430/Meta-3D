# P1-51 实施计划

1. 新增行为测试：地址解析、全部真实驱动缺配置前置失败、registry auto、bootstrap fresh/preserve。
2. 运行定点测试，记录旧实现使用默认 IP 或写入 seed 地址的 RED。
3. 在 HAL 基类实现显式地址解析与缺配置失败 helper。
4. 逐一替换真实驱动的默认 IP，并在 connect 外部 I/O 前接统一门。
5. 收口 DriverRegistry 与 bootstrap；删除旧 F64 compatibility controller 默认参数。
6. 运行定点、相关 HAL/bootstrap 回归、完整 rule gates、compileall 与 diff-check。
7. 内审 P1=0 后开 PR，执行最多两轮 Codex 外审；R2 无 P1 即合并。

