# P1-38 活动告警卫生与主控台收窄设计

## 背景与可观察故障

主控台右侧“活动告警”占据 5/12 的底部区域，但现场数据库中的 674 条告警全部来自
`test_feature_gaps.py`：337 条活动 `Test alert` 与 337 条已 dismissed 的
`Alert to dismiss`。数据库不存在其它来源的告警，生产执行失败当前只写日志。

P3-15 已把该测试文件改为内存 SQLite，并通过 `get_db` override 与开发库隔离；污染源
已断，但历史存量仍在，且没有常驻规则阻止未来另一个测试文件再次以
`source=test_suite` 写真实数据库。

## 方案比较

1. **只删 674 行、保留大面板**：能暂时变干净，但没有锁住测试隔离，也继续浪费界面空间。
2. **本片同时建设生产告警引擎**：能让大面板有内容，但会把执行失败、校准门、DUT attach
   等多类生产者塞进同一 PR，超出 P1-38 的可观察故障。
3. **锁隔离 + 精确清理 + 只留计数徽章（采用）**：保留告警概念和 summary 契约，移除无真实
   数据支撑的详情面板；生产告警接入继续留在 P3-19。

## 数据治理

新增一次性清理工具，默认只 dry-run，只有显式 `--execute` 才提交。删除谓词采用白名单：

- `source = created_by = 'test_suite'`；
- 创建时间早于 2026-08-02（污染存量固化日）；
- 内容严格匹配两类已核实测试产物：
  `WARNING: Alert / Test alert / warning / active` 或
  `INFO: Alert / Alert to dismiss / info / dismissed`。

任何近似行、较新行或其它来源都保留。`alerts` 当前无外键消费方，因此无需级联删除；工具仍在
单事务内执行，异常回滚。测试覆盖 dry-run 不变库、execute 只删白名单、近似真实行保留。

常驻门枚举全仓测试中的 `source=test_suite` 写入站点，只允许出现在拥有独立 SQLite engine、
`get_db` dependency override 和 teardown 的测试模块中。这样来源断开的事实不会只靠注释维持。

## 界面

删除 `ZoneLogsAlerts` 内的告警列表查询和 5/12 宽详情卡，只保留
`/dashboard/alerts/summary` 的十秒轮询。计数在实时日志卡标题栏显示为单个紧凑徽章：

- 0：绿色“无活动告警”；
- >0：按最高严重度着色，显示“活动告警 N”，tooltip 给出严重/错误/警告/信息分布；
- 查询失败：红色“告警计数不可用”；
- 加载中：小型 loader。

实时日志卡占满原底部区域。详情 REST API 与数据模型保留，为将来生产告警接入提供兼容面。

## 验证

- 后端定点测试：清理谓词、dry-run/execute、近似行保留、测试写入隔离门。
- 原告警 API 与 summary 路由回归继续通过。
- 前端契约门：页面不再请求告警详情，只请求 summary；无大面板；日志区域全宽。
- GUI TypeScript production build 通过。
