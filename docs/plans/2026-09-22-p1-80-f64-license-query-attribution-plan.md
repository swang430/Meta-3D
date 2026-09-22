# P1-80 F64 许可查询错误归属实施计划

1. 在 `test_p1_65_propsim_f64_license_truth.py` 先加入现场空回复 + 归属错误、开场 residue、非法值域和
   错误队列不可判的 RED；保留原只读与禁止手册查无探针断言。
2. 在 `propsim_f64_license_truth.py` 抽出同一 recorder 内的开场排水、逐查询排水与证据投影；复用现有
   `_parse_err`、`parse_f64_sys_info`、`classify_state`，并严格校验命令返回值形状；不新增仪器命令或数据库真值。
3. 在诊断 API 只对该序列关闭租约实时监控，并以 F64 现有可重入 SCPI 锁包住整个序列，保证已启动
   或新启动的后台 SCPI 都不能插入“业务查询 + 紧随排水”；其他序列继续使用既有监控默认值。
4. 让许可、校准、用户对齐分别生成子判决；顶层 verdict 只聚合子判决和收尾 residue，许可成功不再
   补真其他状态。
5. 同步 roadmap 与 2026-09-16 现场 runbook：P1-80 软件半完成，P1-2 继续 Hardware Blocked，关闭条件
   仍是同一 F8800A 的干净队列复验。
6. 运行专项、受影响链、全后端、compileall、单一 Alembic head、diff-check；完成 fresh 内审、Ready PR
   与覆盖最新 HEAD 的外审闭环。
