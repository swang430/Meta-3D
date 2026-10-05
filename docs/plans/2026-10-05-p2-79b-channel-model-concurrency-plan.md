# P2-79B 实施计划

> 使用 executing-plans，由主代理顺序完成实现与验证；fresh 独立 reviewer 只读。用户已授权完整 P2-79，不再请求逐项批准。

**目标**：并发增删/切换不会丢失其他型号 preset，旧 ORM 缓存不能覆盖锁后真值。
**架构**：复用 category→connection 行锁事务；刷新写前对象；扫描保留 namespace 锁但顺序一致。
**技术**：Python、SQLAlchemy、PostgreSQL、FastAPI、pytest；不改 GUI/API 请求形态或 migration。
**设计**：[设计稿](../design/2026-10-05-p2-79b-channel-model-concurrency-design.md)。

## 全局约束

WIP=1；base e2dee1a8；不新增/猜测 SCPI，不操作硬件，不改正式 provenance，不补未知 owner；PostgreSQL 仅隔离库 p279a_owner_20261005。

## Task 1：复现 PostgreSQL 原并发故障并修 W2/W3

文件：既有 app/services/channel_asset_ownership.py、app/api/instrument.py；新 tests/test_p2_79b_channel_model_concurrency.py。
- [x] 双 session 测试：B 预加载旧 category/conn；A 持 category/conn 锁并保存新型号 map，B 调真实 add/remove API。A 释放后断言 B 保留两型号键并修改锁后的活动清单。旧代码应 RED。
- [x] 加共享 lock_channel_emulator_rows(db, connection_id=None)，返回 (category, connection)：no_autoflush 导航 category_id；category 查询 populate_existing().with_for_update()；connection 同序重读。以现有错误类型受控拒绝失效连接。
- [x] W2/W3 仅 CE 分支复用 helper，再修改 params 和 sync preset；原非 CE 分支保留。
- [x] 运行 PostgreSQL 定点 GREEN，相关 CRUD/preset 通过，提交。

## Task 2：SCD 投影对称写方

文件：app/services/standard_channel_service.py；同一并发测试文件。
- [x] 写 RED：预加载 SCD/connection，另 session 改 owner/清单或切型号；associate/delete 必须重读，不能基于旧 owner 更新错误 preset。
- [x] create/associate/delete 在 source 修改前加同序锁；已取得锁后使用 db.get(..., populate_existing=True) 重读 source。_sync_projection_for_binding 用锁后连接，不在 flush 前刷新掉本事务 source 改动。
- [x] PostgreSQL 验证 owner 隔离、保留无关手工项/其他型号键、失败 rollback 后无残留，提交。

## Task 3：现代资产与 owner 确认

文件：app/services/channel_asset_service.py、app/services/channel_asset_ownership.py；同一并发测试文件。
- [x] RED：预加载旧 selected/source 的批量确认在另一 session 切型号后必须拒绝；派生 source owner cache 漂移必须剔除。
- [x] vendor create/update/confirm/delete 在 mutation 前锁 CE，并 refresh source；validate owner 在锁内读 selected。owned_channel_model_params 使用 populate_existing 取现代优先/legacy source。软件源不强加 owner。
- [x] 真实批量/编辑入口失败回滚；相关资产/归属测试 GREEN，提交。

## Task 4：PUT 与扫描同序刷新

文件：app/api/instrument.py、app/services/smu_project_inventory.py；同一并发测试文件。
- [x] RED：预加载旧 map 的真实 PUT 不得覆盖随后已存的其他型号；扫描锁不能先 connection 后 category。
- [x] CE PUT category/connection 查询加 populate_existing。扫描先共享 category 锁，再既有 namespace 表锁，再 connection/source 锁；保留二次预览。
- [x] PostgreSQL 并发等待与 lock_timeout 内释放、扫描已有回归 GREEN；提交。

## Task 5：全集对账与镜像

- [x] 全仓搜索 CE connection_params/preset 写点，对照设计表；只读 resolver 不加写锁、helper 不自 commit。确认 get_db 对异常 rollback/close。
- [x] roadamp 统一 A 已合并、B 实现/验证状态；历史 Discovered 记录不伪改，只在当前 triage 标注去向。
- [x] diff-check、单一 Alembic head、compileall；API shape 未变，无需生成无差异镜像。

## Task 6：最终验证与 fresh 内审

- [x] 隔离 PG：P2_79_TEST_DATABASE=p279a_owner_20261005 USE_MOCK_INSTRUMENTS=true .venv/bin/pytest -q -o log_cli=false --show-capture=no --tb=short tests/test_p2_79b_channel_model_concurrency.py。
- [x] 相关：tests/test_p2_79a_channel_model_ownership.py、test_standard_channel.py、test_smu_project_inventory.py、test_channel_models_crud.py、test_p2_58_2_channel_emulator_model_presets.py、test_p2_58_2_channel_emulator_preset_api.py、test_p2_58_2_channel_emulator_preset_sync.py、test_rule_gates.py。
- [x] 最终全后端：DATABASE_URL=sqlite:////tmp/p2-79b-final.db USE_MOCK_INSTRUMENTS=true .venv/bin/pytest -q -o log_cli=false --show-capture=no --tb=short。
- [x] GUI production build（仅现有契约回归，不改 GUI）；fresh 只读功能内审 P1=0。记录版本、退出码、统计行与耗时；同输入不重复全量。

## Task 7：完整交付

- [ ] 提交/推送 Ready PR；记录 request、HEAD、reviewid/结果；R1处理本片 P1/P2，最新 HEAD R2 无 P1 合并，仍有 P1 则续审。
- [ ] fetch/main ff-only、核单一迁移 head/运行库未改归属、保留仪器资料；清理本片工作树/分支。P2-79 完成后汇总，不启动 P2-80+。

## 最终验证记录（本次稳定功能输入）

Task 1–4 的同根写方合并为一个功能提交，避免中间锁序版本独立发布。旧实现 PostgreSQL 反例先后 2+2+2+1+1+1 项 RED；最终 9 passed（0.75s，exit 0）。相关命令按 Task 6 列出的 8 个文件执行，200 passed（14.56s，exit 0）；全后端使用 Task 6 的独立 SQLite URL，6807 passed/15 skipped（154.07s，exit 0），其中 9 个 opt-in PostgreSQL 项已单独执行。`npm run build` 11.37s，exit 0；`python -m compileall -q app`、`alembic heads`（c1e3f5a7b9d2 单一 head）与 base-to-working diff-check 通过。以上生产代码输入一致，文档记账不触发无意义全量复跑。fresh 独立累计功能审查未发现 P1/P2；审查者未另跑全量，测试结论由主代理核验日志。未调用仪器；API shape 不变，未生成无差异镜像。
