# DEL-02：新安装数据库驱动匹配

用户已批准按“驱动匹配→空库迁移→隔离整套安装”连续完成。本片只修第一个可观察故障：
按requirements新安装SQLAlchemy2.1时，postgresql://默认选未安装的psycopg，API在导入时失败。

## 实现契约

- Settings默认明确postgresql+psycopg2://；旧参数、环境变量、.env中的postgresql://仅替换前缀，仍使用已声明的psycopg2。
- 保留地址其余字符（含编码密码和查询参数）；不解析再序列化密码，不修改用户.env。
- 显式选择其他驱动或SQLite地址不被改写；这不表示替调用方安装其他驱动，也不表示整套启动支持SQLite。
- SQLAlchemy支持范围收窄为>=2.0,<2.1；不是固定2.0.44。今后升级须验证完整数据库链。
- API运行与Alembic默认配置共享Settings；显式Alembic sqlalchemy.url按原行为由调用方负责。
- 当前配置示例同步。历史核查日志及归档保留原状。

无数据库结构/数据修改，不改变仪器代码；NotebookLM不适用。独立生产消费方核查覆盖SessionLocal、预检、数据库检查脚本与Alembic。
下一迁移片单独修约束重复，本片不掩盖那个失败。

## 验证

- 修复前配置行为测试：4 failed、3 passed（default/argument/environment/dotenv四条失败）。
- 修复后配置与数据库预检：12 passed。
- 独立新环境原SQLAlchemy2.1.8：修复后的旧postgresql://地址选择psycopg2成功。
- 新环境按本片requirements重新安装：SQLAlchemy2.0.57，pip check无依赖破损。
- 后端全部收集项已覆盖：首次独立PG环境运行中断，7037 passed/17 skipped/139 errors；139项均为校准fixture要求/tmp SQLite而环境不符，不能称通过。随后仅排除已明确通过的6842项，在/tmp独立SQLite补跑：1955 passed/17 skipped/2 failed（852.30秒）。合计覆盖8797项通过、17跳过、2失败；这是分段覆盖，不是单次全量全绿。
- 两项失败为G8/G11旧文档接口引用；未改main f2dd8c5d同两项均失败、内容一致（1.43秒）。不在驱动修复中改历史文档或放宽检查。
- 慢速64项模拟校准矩阵在修改分支通过，未改main单独对照同样通过（357.26秒）；不代表真机验收。
- 命令：api-service下运行`.venv/bin/python -m pytest -q --color=no`；补跑追加临时`-p partition_plugin`仅排除首次已通过nodeid。环境为`USE_MOCK_INSTRUMENTS=true`和独立`DATABASE_URL`；未连接现有meta3d_db。日志目录为本机`/Users/Simon/.codex/artifacts/2026-11-15-del02-driver/`，含full.log、remainder.log、baseline-doc-gates.log和baseline-pc04a8.log。
- 验证输入：基于f2dd8c5d的本片config.py、requirements.txt和新增配置测试；随后仅增加本记录及roadmap状态，未改变生产或测试输入。独立内审功能CLEAN；最终证据复核另见PR。
