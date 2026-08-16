# P1-50 日志留存失败告警隔离设计

## 可观察故障

`ExecutionFileHandler.close_execution()` 先关闭并移除当前执行流，再调用 `purge_expired()`。
若清理另一个过期执行日志时 `unlink()` 失败，`_module_logger.warning()` 会传播到根 logger。
根上的执行文件 handler 通过 `ContextFilter` 读取仍有效的 `current_execution_id`，于是这条运维
告警会重新打开刚关闭的 `exec-<execution_id>.log`：当前执行继续被误判为 active，且每次失败
留下一个文件描述符。

## 全集

- 留存清理入口：handler 初始化与每次 `close_execution()`。
- 删除失败告警写点：`purge_expired()` 内唯一一处 `_module_logger.warning()`。
- 执行关联真值：`current_execution_id`；根 handler 的 `ContextFilter` 在 emit 时注入。
- 执行流生命周期：`_streams`、`active_execution_ids()`、`close_execution()`。
- 运维可见性：告警仍须传播到 console/app 日志；不能退回 `handleError()`，生产配置会静默。

## 方案比较

### A. 临时隔离执行上下文（采用）

发留存失败告警前把 `current_execution_id` 临时设为 `-`，在 `finally` 中按 token 恢复。
同步 logging 会在隔离窗口内完成所有 handler 处理，因此执行文件 handler 会按现有首行门直接忽略，
console/app handler 仍正常记录告警。

优点：只收窄错误记录的关联来源；不新增 logger、handler 或过滤机制；原执行上下文可恢复。

### B. 新建不传播的运维 logger

需要复制或引用 app/console handler 配置，容易产生初始化顺序与重复输出问题，范围过大。

### C. 让执行文件 handler 永久排除 logging_config namespace

能挡住本故障，但条件比故障宽，会改变该模块所有未来记录的执行关联语义。

## 错误与状态安全

- `unlink()` 失败仍不抛出，不掩盖执行收尾；返回的 purged 数量维持原语义。
- 运维告警仍可见，不使用 `handleError()`。
- 无论 logger 自身是否异常，`current_execution_id` 都通过 token 恢复。
- 告警不得重新写入 `_streams`，`active_execution_ids()` 在 `close_execution()` 返回后不含已关闭 ID。

## TDD 验收

在真实根 logger 上挂待测 `ExecutionFileHandler`：

1. 先为当前执行打开流。
2. 制造另一个已过期日志并让 `Path.unlink()` 抛 `OSError`。
3. 保持 `current_execution_id` 为当前执行，调用 `close_execution()`。
4. 旧代码应重新打开当前执行流，RED。
5. 修复后断言当前 ID 不在 active 集合、流字典为空、上下文恢复、告警仍被 `caplog` 捕获。

相关回归覆盖现有留存 16 测、完整 rule gates、compileall 与 diff-check。

## 范围边界

本片只处理留存清理失败告警的执行上下文回流，不修改留存期限、清理调度、日志查询 API、
重复抑制或其他 logger namespace。
