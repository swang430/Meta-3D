# P2-79B：信道型号配置并发完整性

用户已批准完整 P2-79，本片沿用 A→B 授权，不再逐步确认。A 为 PR #498，merge e2dee1a8；本片唯一 WIP。

## 可观察故障与实证

两个操作员同时切型号和增删文件时，W2/W3 先读取旧 connection/preset map，UPDATE 等 PUT 释放连接锁后覆盖新 map；即使补 FOR UPDATE，identity map 中预加载对象仍可保留旧 selected/params。
旧反例见 roadmap Discovered 的 W2/W3/W4 描述，历史文字不修改；本片必须重新用隔离 PostgreSQL 双 session 复现，不以 SQLite 代替。
基线相关 48 passed（1.71s），来源为 e2dee1a8 原样代码。memory 已查，仅使用仓库当前代码；NotebookLM 不适用，不改仪器语义。

## 选择：收窄既有事务锁边界，不增加另一份归属或修复服务

1. 所有会改变 CE selected model、connection_params、preset map、vendor owner/source 内容的写方，先锁 category，再锁 connection；从数据库重新加载 selected/params，不能消费请求前缓存。
2. 共享锁函数放在既有 channel_asset_ownership.py。普通查询得到 connection.category_id 只作稳定导航；该导航在 no_autoflush 内，随后 category→connection 的 populate_existing/FOR UPDATE 才是写方真值。不改变只读 owner validator 的行为，不给普通执行解析加长事务写锁。
3. W2/W3 保留其他类别原行为，只为 CE 写入启用相同锁序；无 connection 的新增仍在 category 锁内创建。
4. SCD create/associate/delete 在修改 source 前取得类别/连接锁；关联/删除重读 SCD，投影复用同一锁内的 connection/category，不在修改后 refresh 掉本事务改动。
5. vendor create/update/confirm/delete 在 source 修改前加相同锁；重读 owner/source。未知无连接 vendor 仍锁 CE category，不猜归属。非 vendor 内容编辑不新增 CE 依赖。
6. PUT CE 的 category/connection 锁必须 populate_existing。扫描先取得 category，然后保留原保护全局 canonical namespace 的表锁，再连接/资产锁；不删掉既有 phantom 防护，不反向等待 category。扫描二次预览使用刷新对象。
7. 派生项 source 查验使用 populate_existing，排除同 session 旧 owner 缓存；确认端点原子事务不变。

## 全集与验收关系

| 生产入口 | 权威判据 | 正式消费者/写出 | 可观察断言 |
|---|---|---|---|
| PUT 仪器保存 | locked saved selected＋完整 preset map | 活动连接和目标 preset | 预加载旧 map 后保存不丢另型号键 |
| W2/W3 增删模型 | category→connection 重读 | 活动清单＋selected preset | 等待后只修改锁后活动型号，不覆盖新 map |
| SCD 新建/关联/删除 | locked owner/source | 对应 owner preset，活动仅匹配时写 | 切型号后不跨 owner 写；并发派生/手工项互不丢失 |
| vendor 创建/编辑/确认/删除 | locked saved model＋source | 实体 owner/content | 过期确认拒绝、批量失败不留部分更新 |
| 扫描发布 | category→table→connection→asset | 当次二次预览、asset＋投影＋preset | 缓存/型号变化后重算，不反序死锁 |
| 派生清单查验 | 当前持久 source，不信条目标记 | preset、目录、投影 | 旧 identity-map owner 不能补真 |

## 安全与验证

无 SCPI/真仪器 I/O，无新 migration，无正式 provenance 修改，无 SMB 正式依赖。并发测试只允许 P2_79_TEST_DATABASE=p279a_owner_20261005；dbname 前缀必须校验，不使用运行库做并发试验。
隔离库已有 CE category 仅测试可临时改动，fixture 保存/恢复 selected、connection_params、preset，并删除专属测试行；测试 finally rollback/恢复，不影响运行库。每个 session 设置有限 lock_timeout，失败不可挂死。
先 RED→GREEN 验证原 PostgreSQL 丢更新、预加载缓存、SCD 对称入口、过期确认与失败回滚；然后所有相关读写方与最终全后端。固定输入只由主代理跑全量一次；fresh reviewer 只读审生产关系，不重复全量。Ready PR 后 Codex R1→R2，最新 HEAD 无 P1 才合并/main同步/清理。P2-80+ 不启动。
