# BaseStation 分型号保存与 LabProfile 同步实施计划

## Task 1：持久化与严格 schema

- 新增 `InstrumentConnection.base_station_model_presets` JSON 与单一 Alembic migration。
- 新增后端 Pydantic preset schema；只允许合法 UUID、endpoint 与 manifest-validated profile。
- RED：当前型号初始 backfill、UXM/CMW500 两份 preset 共存、客户端不能直接写 map。

## Task 2：原子保存服务

- 抽取 BaseStation 专用原子保存 helper，先保存旧活动快照，再校验并保存目标快照，最后投影活动 connection。
- 修复 endpoint 解析：目标无 port 时必须清除旧型号 port，禁止保留跨型号残值。
- RED：切换保存成功、profile 不适用、profile 缺失/非法、endpoint/manifest 错误全回滚。

## Task 3：GUI 草稿语义

- 型号 `onChange` 只切换本地 draft，并从目标 preset 初始化所有字段。
- “保存配置”携带 `modelId + connection/profile`；成功后以响应重置草稿。
- RED：型号切换零 PUT；保存单次 PUT；CMW→UXM→CMW 保留各自 endpoint/profile；未保存草稿不能污染目录缓存。

## Task 4：同步只消费已保存 resolver 真值

- 后端同步继续零硬件 I/O，但必须在同一事务内从已保存活动 connection 构造 binding 并走 resolver。
- RED：未保存草稿无输入通道；混合/非法保存态回滚；有效已保存态同步后的 digest 与 preview/freeze 一致。

## Task 5：API 四镜像与现场恢复

- 同步 live OpenAPI、`api/openapi.yaml`、generated TS、手写 GUI 类型。
- 新增受控、幂等的数据修复脚本/命令，只恢复已核对的本地历史 CMW500 preset；不声明正式七字段回读成功。

## Task 6：验证与收口

- 相关后端与 rule gates。
- 全后端。
- GUI 契约与 production build。
- OpenAPI 镜像、compileall、单一 Alembic head、base-to-HEAD diff-check。
- fresh 功能内审 P1=0 后开 Ready PR，Codex R1→R2；覆盖最新 HEAD 的外审无 P1 才合并。
