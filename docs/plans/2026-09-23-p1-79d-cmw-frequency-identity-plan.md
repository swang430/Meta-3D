# P1-79D 实施计划

1. RED：证明 CMW500 默认缓存不能报告身份；成功回执、错误队列拒绝、回读漂移、取消、旧入口、
   重连、释放与断连分别具有预期的提升/清除行为。
2. GREEN：在共同 HAL 增加 fail-closed 接口；CMW500 仅从同次配置回执的已确认
   Band/EARFCN/BW 提升不可变身份。
3. 接线：频率一致性执行器直接调用共同 HAL，删除频率身份的 `hasattr` 分叉；UXM 行为不变。
4. 核验：枚举全部产生方/消费方与失败复位路径；运行 CMW 状态机、频率一致性、P1-79C 证据链、
   rule gates、全后端、compileall、单一 Alembic head 与 diff-check。
5. 交付：fresh 功能内审后开 Ready PR；Codex R1 处理功能 P1 与本片内 P2，再触发 R2；覆盖
   最新 HEAD 的 R2 无 P1 后合并、同步并清理。P1-79E 仍保持 Hardware/Vendor-Protocol Blocked。
