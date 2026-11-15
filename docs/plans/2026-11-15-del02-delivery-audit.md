# DEL-02：新客户部署、升级与恢复核查

日期：2026-11-15。依据用户批准的“先收口S5c接口片，原生环境受阻则推进DEL-02”计划。
本片是交付差距核查，不修改业务实现、不启动仪器、不修改现有数据库。

## 当前结论

**不能把当前版本宣布为新客户可直接部署。** 空白PostgreSQL数据库执行现有迁移会失败。
本次已形成差距清单；DEL-02整体交付验收仍未通过，不用一次合成数据备份成功替代完整恢复验收。

核查基线：Meta-3D main `8870c52408a497b6e6af7f90974262e156e68890`；
ChannelEgine main `d12ff3fdd8c917f882618b98dd604bc07389e7b0`。
前者为#584、后者为#45，已于本日合并并同步两个本地主目录。
Lauraycs保持原版main `53ea4cf97842d8e9c18d97e07d081b2b98fbc316`，没有改动。

## S5c交接

现有接口采集与CE直接读取的软件片已经交付，完整S5c仍未完成。
本日重新尝试原版接口依赖的正常原生导入：

- Lauraycs现有 `.venv` 缺少 `torch`，报 `ModuleNotFoundError`。
- 上次为评估建立的 `/tmp/s5c-lr-adapter-venv` 已有torch，但导入仍在 `HyperRT/CG.py` 的 `AbstractCamera = AbstractCameraF` 报 `NameError`。
- 本机未发现运行的Lauraycs服务；没有取得可调用远端服务地址。本次没有验证远端部署。
- 这不是本次许可证验证结论，也不证明Lauraycs本身不支持聚簇。
- 不修改HyperRT、不构造原生成功结果。待可运行的原版服务提供原38帧聚簇结果后，继续精度评估、非均匀时间合成及正式接入。多快照正式拒绝保护保持不变。

#584第二轮的一条P2仍披露在PR：带Content-Length的部分响应可能未留存正文；失败帧与后续采集保留。按现行R2无P1规则收口，不自动把这条意见排入新开发队列。

## 核查结果

| 项目 | 本次证据 | 判定及未验部分 |
|---|---|---|
| 已有依赖环境 | 现有API Python3.13环境执行pip check：No broken requirements found | 只说明该环境已安装依赖内部一致，不替代新客户安装 |
| 新依赖环境 | 独立Python3.13 venv按api-service/requirements.txt安装退出0，pip check通过；但使用默认postgresql://形式导入API时报缺少psycopg | 新环境默认数据库驱动与已声明依赖不匹配，API导入失败；不能将安装包成功当服务可启动。Docker Python3.11与GUI/CE整套安装未验 |
| 配置及数据隔离 | 读取docker-compose.yml：固定容器meta3d_db、卷meta3d_postgres_data，端口5432绑定所有接口 | 适用于现有单站开发；仅换compose项目名不能形成独立客户隔离。此次演练使用独立名字、临时内存数据目录、随机凭据及本机随机端口 |
| 空库迁移 | PostgreSQL14.20空库执行alembic upgrade head，退出1 | 迁移c73a19f4e602重复建立ck_scd_rat_channel_identity，阻塞空库安装 |
| 初始化与重复启动 | 迁移失败即停止，没有继续bootstrap或启动API | 尚未通过；不采用手工stamp绕过失败 |
| 备份与恢复基础路径 | 另一个空的临时PG数据库，仅建一张合成证据表；现有backup_db.sh导出custom格式备份，pg_restore --exit-on-error恢复至另一数据库；证据行一致 | 通过合成数据的脚本/恢复基础路径，不代表应用全表、约束、文件附件或历史版本恢复通过 |
| 备份失败返回 | 指向不存在的临时容器，退出1 | 无假成功 |
| 升级及失败回退 | 本次没有历史客户版本数据集；现版本空库链已失败 | 未验证历史升级、数据库降级、旧应用兼容；不能据备份文件存在宣称可回退 |
| 访问控制及默认凭据 | compose/config有开发默认数据库密码；auth/config有开发JWT默认值；API目录没有require_auth调用，test_plan路由只挂数据库等依赖 | 静态确认“设置AUTH_MODE=required”不能代替业务接口保护；本轮未做全接口匿名访问攻击测试，也未验证客户外部网关 |
| 版本识别 | Git提交可追踪；API配置app_version为0.9.0，根package.json为1.0.0；health取settings.app_version | 运行版本字段不能独立识别本次代码提交；未验证部署产物与实际运行进程的完整对应 |
| 外部CE依赖 | 根package.json的dev:channel-engine及generate:schema写有本机ChannelEgine绝对路径 | 新客户机照用此入口可能找不到CE；须明确客户安装入口及CE版本配套 |
| 持久文件 | Dockerfile明确要求挂calibration_data及certificates，数据库脚本只做pg_dump | 整套恢复还要覆盖文件与数据库一致性；本轮没有替代客户文件恢复验收 |

### 空库故障根因

基线迁移 `40fd1c51ff40` 调用当前模型的 `Base.metadata.create_all()`，已经创建模型声明的
`ck_scd_rat_channel_identity`。后续 `c73a19f4e602` 再无条件创建同名约束，
PostgreSQL返回 `DuplicateObject`，迁移停止。

这个结论来自真实空库运行和两处源码核对；不是SQLite测试推断。现有数据未参与演练。
没有顺带修迁移：按DEL-02范围先交付具体差距，再另立修复片，防止把交付核查变成无边界重构。

## 后续顺序（沿DEL-02，不另造一套todo编号）

1. **先修新环境启动与空库安装故障**：新环境按默认postgresql://选择psycopg，而requirements声明psycopg2-binary；须确定兼容驱动和版本，再验证导入。空库约束问题须同时验证新库完整迁移及已有表升级，不能靠跳过全部迁移或stamp冒充成功。
2. **再跑整套安装、升级和恢复**：明确API/GUI/CE配套版本；验证bootstrap重复执行、历史数据库升级、文件持久化、恢复后关键对象及失败回退。
3. **客户开放前解决部署隔离及访问边界**：明确客户配置/数据目录、凭据、绑定地址、网关或应用鉴权责任；按真实部署方式逐项实测，不把开发默认配置交给客户直接暴露。
4. S5c原生环境就绪后回到原S5c范围；S6设备验收及PC真实采集继续等待各自前置。

以上为核查后的修复建议，本片不修改业务代码、不宣称这些后续项已经实现。

## 复现及证据

原生日志对应命令（在Lauraycs根目录）：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=HyperRT/PyHyperRT .venv/bin/python -c 'import HyperRT.MiRT.MPDB.MPUDF'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=HyperRT/PyHyperRT /tmp/s5c-lr-adapter-venv/bin/python -c 'import HyperRT.MiRT.MPDB.MPUDF'
```

数据库演练采用postgres:14.20，单独容器meta3d-del02-audit-20261115，数据库audit_source/audit_restored，
随机凭据不入日志，映射127.0.0.1随机端口，使用tmpfs而非用户现有volume。
在api-service目录，以仅指向该临时库的DATABASE_URL运行：

```sh
.venv/bin/python -m alembic upgrade head
```

结果：退出1，DuplicateObject，约束ck_scd_rat_channel_identity已存在。
备份独立演练通过META3D_PG_CONTAINER/META3D_PG_DB/META3D_PG_USER/META3D_BACKUP_DIR指向合成库与独立输出目录，
调用原有 `sh scripts/backup_db.sh`；恢复调用 `pg_restore -U audit -d audit_restored --exit-on-error`。
恢复前后证据行为 `1|synthetic audit only`；不存在容器的负例退出1。两个临时容器均已清理，
原meta3d_db仍在运行。没有复制客户数据，没有修改既有备份或轮转目录。

机器日志与合成dump在本机 `/Users/Simon/.codex/artifacts/2026-11-15-del02/`：
`migration-head.log`、`results.json`、`fresh-install.log`、`backup-only/results.json`及对应步骤日志。
这些是本机复现证据，不是其他机器可直接访问的共享附件。本文件保留命令、精确错误和结果边界。

### 独立依赖安装补充

新venv由python3 -m venv建立，pip install -r api-service/requirements.txt退出0，pip check报告No broken requirements found。完整版本表见fresh-freeze.txt。随后以显式的隔离占位PostgreSQL地址（127.0.0.1:1，不指向现有数据库）导入app.main，未进入服务生命周期，报ModuleNotFoundError: No module named 'psycopg'。SQLAlchemy按postgresql://选择psycopg，而requirements只声明psycopg2-binary。日志fresh-api-import.log。先前用SQLite内存地址的尝试因max_overflow参数不适配该连接池失败，不作为PostgreSQL交付故障依据。

同一新venv改用显式postgresql+psycopg2://隔离占位地址后，导入输出API import OK 0.9.0并退出0，说明默认驱动选择是本次导入失败的直接原因；仅导入，没有执行lifespan、连接仪器或验证服务可用。完整日志fresh-explicit-driver-import.log。此次解析安装版本SQLAlchemy==2.1.8、psycopg2-binary==2.9.13；这不宣称所有版本都存在相同行为。
