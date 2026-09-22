# P1-79C 实施计划

1. RED：覆盖 CMW/UXM 共同配置与吞吐投影，以及模拟、attempt/lease、manifest、
   registry、exchange provenance 的 fail-closed 反例。
2. GREEN：在 execution evidence 服务内实现只读共同投影和冻结环境构造；不解析厂商
   命令、不查询 current HAL。
3. 接线：删除 `MeasureExecutor` 的专用 builder `hasattr` 门；配置在 attach 后投影，
   吞吐在持久化窗口后投影。
4. 清理：执行器不再按 UXM 专用 builder 分叉；共同回执优先，只有 UXM 共同配置
   回执不足以形成 E3 时才复用既有、已核验目录证明。历史兼容 wrapper/translator
   仅读保留，CMW500 不得借该回退升级。
5. 验证：定点、对称 adapter 链、强制证据终判、rule gates、全后端、compileall、
   单一 Alembic head、diff-check、fresh 功能内审。
6. 交付：Ready PR，Codex R1；处理本片功能 P1 与本片内 P2 后触发 R2；覆盖最新
   HEAD 的 R2 无 P1 后合并、同步、清理，再进入 P1-79D。
