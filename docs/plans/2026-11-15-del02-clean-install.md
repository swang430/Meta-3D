# DEL-02：隔离安装与公开入口核验

用户已批准连续完成三片；驱动匹配#586、空库迁移#587已合并。本片解决公开npm入口覆盖安装者路径、接口文件生成错误目录且失败返回成功、安装说明端口与依赖要求错误。NotebookLM不适用；沿用现行规则和memory的实证边界。

## 改动与范围

- 启动与接口生成入口沿用安装者显式CHANNEL_ENGINE_PATH，不写死个人目录。
- 接口生成从脚本自身定位项目和服务，直接读取路由；不启动服务、不伪装计算库；异常退出非零。
- 根README和服务README给出独立环境、依赖、先迁移后预置、标准端口及手动启动命令。
- Node要求来自锁定Vite7.3.0的engines：^20.19.0 || >=22.12.0；只同步根声明/锁文件元数据和文档，不升级依赖。
- 不改后端业务、迁移、仪器命令或Lauraycs；不开放多快照正式执行。

## 隔离验证

基点Meta-3D 4427b5a4及本片工作区改动，外部ChannelEgine d12ff3f。源码用git archive导到/tmp/meta3d-del02-install-hutjdovh；未复制用户.env或旧node_modules。
API复用第一片新建并按requirements安装的独立fresh-api-venv（非日常开发venv）；计算服务重新建venv并安装服务与ChannelEgine两份requirements。Node22.17.0/npm10.9.2/Python3.13.7，SQLAlchemy2.0.57，PostgreSQL14.20。

- 原入口测试两个路径覆盖断言失败；原生成脚本实跑ModuleNotFoundError却退出0。完整原代码反例2个测试共3处失败，修复后2个测试通过（其中入口测试含两个子例）。失败生成不会改已有接口文件。
- 根目录与gui分别npm ci成功；两个Python环境pip check均无依赖破损。
- 新空install_audit库alembic upgrade head成功；bootstrap第一次成功导入预置，第二次全部up-to-date跳过。曾先直接bootstrap因缺表失败，已按正确顺序重跑并修文档；没有改bootstrap的既定职责。
- 新环境真实npm run generate:schema成功；生成物仅在临时副本验证，不提交无关接口变更。GUI生产build通过（20.27秒，既有大包提示）。
- 实跑npm run dev:all，七类驱动均为Mock；CE8001与API8000健康200且明确可用，API数据库已连接、mock_instruments=true；GUI localhost:5173页面及其/api/v1/health代理200。Vite本机绑定IPv6 localhost，验证使用文档localhost地址；不把127.0.0.1探测不通算产品失败。
- CE启动路径正反例：正确绝对路径退出0；不存在路径退出1，MOCK_ASC_MODE=false，不降级伪装可用。

本机日志目录：/Users/Simon/.codex/artifacts/2026-11-15-del02-install/，含entrypoint-all-red.log、schema-red/green.log、ce-install.log、npm-root/gui.log、migrate.log、bootstrap-after-migrate/repeat.log、dev-all.log、health.json、gui-build.log及pip-check日志。连接凭据只在权限600本机文件，不入仓库。

本片属于局部安装入口/说明修复：运行行为正反例、独立安装与GUI构建；后端业务/依赖未变，不重复22分钟后端全量。上一片完整回归的未定位模拟测试失败仍保留原结论。本轮不是正式部署、历史客户数据库全量恢复、现场校准、算法精度或S5c验收。


## 预置应用库备份恢复补充

使用既有scripts/backup_db.sh，显式指向本轮隔离容器的install_audit及独立备份目录，pg_dump和pg_restore均退出0，恢复目标为新建install_restored，未覆盖源库。
恢复前后62张public表逐表比较行数及排序后整行JSON摘要全部一致；25条预置用例保留。恢复后真实API进程生命周期读取用例接口200、total=25；健康检查数据库true、mock_instruments=true；因测试CE已停止，channel_engine_available=false且status=degraded，负例如实报告。
证据：backup.log、restore.log、restore-comparison.json、restored-api.log/json。只验证新初始化的合成应用库，未覆盖历史客户数据、外部报告文件或灾备切换；这些仍属DEL-02后续交付验收。
独立内审已完成代码与安装证据核验，最后新增本段只需记录复核。测试服务已停止；临时容器在本片证据收口后删除，不影响现有meta3d_db。
