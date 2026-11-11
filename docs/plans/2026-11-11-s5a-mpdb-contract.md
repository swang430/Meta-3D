# P2-16 S5a：离线 MPDB 格式适配与复算

日期：2026-11-11。用户已批准继续实现本片，按逐片内外审及合并流程交付。

## 范围与设计选择

可观察缺口：现有正式执行拒绝多快照，尚无独立保留完整原始帧及来源的离线适配产物。
本片新增读取模块、命令行工具、合成测试、独立算法复算探针及验证文档。正式执行拒绝门不改，
不聚簇、不生成硬件文件、不操作仪器、不改其他仓库。

关系全集：`scripts/inspect_mpdb.py` → `mpdb_input.py` 的白名单解析及时间检查 →
本地版本化 JSON；正式消费者为空。现有 `channel_asset_resolver.py` 及其多快照拒绝测试
仅回归，不接新入口。输入入口只有 manifest ZIP；内层 MPDB 必须为版本3的
portable-row-sharded JSON/safetensors。外层必须恰有上下行各一份，单频、单V/V标量端口、每帧一条LINK；
拒绝不支持的版本、列、张量、重复身份、缺口、未知LINK及上下行不对应位置。

安全解析只使用 JSON、ZIP 和显式数值类型数组，不执行 pickle、不解包到磁盘。
ZIP成员路径、重复名称、解压大小和分片覆盖均检查；缓存索引不作为真值，按原始LINK_ID关联。
附属 LAURAYCS_POWER_CHANNEL 保留为独立原始表，不与 CHANNEL 混合。未知表/列直接拒绝。

## 文件约定 `s5-raw-paths/1`

- 文件身份：源ZIP及每个MPDB的SHA256、原manifest、原mpdb.json、适配版本和参数。
- 每个方向保留原始各表的按列数组；H用 `{real: [...], imag: [...]}` 保留二进制浮点值，
  不取模、不合并、不改相位。缺少可选传播字段明确为null，来源表记缺失。
- 帧保留原FRAME_ID、LINK_ID、LINK行号、所属CHANNEL原始行号和time_s。行号只是样本编号，
  不是跨帧物理路径身份。原TX/RX/TX_ANT/RX_ANT与极化元数据原样保留，不能由编号猜H/V。
- 单位与来源集中声明。原值不换算；DELAY秒、PATH_LENGTH米的数值交叉差只作候选单位证据，
  不作为厂商语义确认。角度候选度；DOPPLER单位、符号及产生方法未知；H归一化与相位约定未知。
- 坐标参考系、变换、生成版本未知时null。显式假设坐标单位为metres才允许用速度推时刻，
  不由坐标量级猜UTM/ECEF。原meta仍完整保留，避免丢失后续可调查证据。
- 时间二选一：显式JSON时刻列表（秒，按原LINK行顺序），或显式恒速及metres声明。
  后者按相邻帧三维Euclidean距离/速度累计，从0开始；要求全程同一端移动、另一端静止，
  零位移、双端运动、运动端切换均要求显式时间。速度推导还要求FRAME_ID按原行严格递增，可跳号；乱序时要求显式时刻，不排序。相邻时间差及首末跨度须有限。无时间依据拒绝，不编造零间隔。
  时刻有限且严格递增；保留非均匀间隔、最后短段和原帧顺序，不重采样。
- 上下行FRAME_ID及交换后的TX/RX位置逐帧精确一致才接受；频点一致。
  结果仅为离线输入，不具正式测量、物理绝对精度或设备播放资格。

## 验证计划

先RED后GREEN；小型合成ZIP独立构造静止、正反匀速、双径及已知轨迹。
参考按 `delay=L/c`、`h=a exp(jφ0−j2πfc(L−L0)/c)` 独立计算；核复数/相位、时间、
非均匀间隔/末段及来源。覆盖安全解析、结构/形状/身份、缺失、运动含混负路径；实跑核心逆变异。
测试显式全Mock及全新临时SQLite；离线模块无数据库/仪器依赖。新功能最终后端全量由主代理在代码稳定后唯一执行，子任务不自行启动；
如既有失败如实记录，不将其称全绿。真实样本及大产物仅在仓库外本地artifact目录，不提交GitHub。

输入：用户ZIP SHA256 `6cada6a493b04bbf05725ffdeaac61956e382a18897fad5c3efce94113a0037d`。
只读盘点为每方向38帧合计36359条CHANNEL路径（非每帧36359条）。
用户明确恒速5m/s并授权位置推时刻；采用显式metres假设（不是用户已确认单位），地理参考系和生成版本未知不阻塞本片。
验证日志、命令及最终边界在完成后补于本文。

## 来源与验收责任补充

CLI显式传速时`parameters.speed_source=user_confirmed`；库调用默认`declared`。
`coordinate_unit_source=explicit_assumption`，与用户确认速度分开。
时间依据分别是显式时刻、距离/速度推导、缺依据（拒绝）；不从帧编号生成时间。
显式时刻内容及规范JSON校验值进入输出；CLI还保存时刻文件原始字节校验值。
`adapter_source_sha256`记录实际读取模块源码；源文件与适配版本分开。
全部已读取数值（含JSON元数据）非有限即拒绝，不填零、不写NaN JSON。
元数据提及但未附的mpgeom保留原引用，输出missing_attachments，不声称几何完整。

本片合成解析构造仅证明读取、时间计算及复数/相位保真，不证明原RT多普勒物理意义、
源单位或算法物理准确性。另以真实算法入口完成四类独立解析参考，见[核查结果](2026-11-11-s5a-reference-results.md)，
包含已知轨迹误差及统一帧间隔接口限制，不以无出处容限判通过。S5c接线尚未完成。

## 初版子任务验证交接（2026-11-11，内审收窄前）

基准HEAD：`a115a35dfbc58d41fcf3ee854e233788e884b564`。四个新增文件均归本片；
既存未跟踪`.playwright-cli/`及`api-service/.venv`未改，不包含在交付中。
实际入口为仓库根目录`scripts/inspect_mpdb.py`，不在api-service/scripts下。

- RED：模块不存在时专属测试收集失败（1 error），日志`red.log`；随后实现。
- GREEN及逆变异恢复后：专属45 passed。相关现有resolver回归14 passed（含多快照拒绝）。
  首次相关回归使用内存SQLite因连接池参数不兼容而未收集；改用全新临时文件SQLite，未改应用配置。
- 7组逆变异：复数虚部反号、速度时间缩半、取消上下行位置核验、缺DOPPLER填0、
  放行非有限数值、放行双端运动、篡改最后时刻，均为目标测试1 failed/退出1。
  每组独立恢复，最终源码SHA256恢复一致；原文替换及命令见`run_mutations.py`和`mutations.json`。
- 真实CLI输出`adapted-final.json`重新加载后，独立解码原ZIP全部三张表逐值比较，
  每方向364460个张量元素（复数逐实虚分量比较）一致，完整覆盖36359条路径及38帧。
  输出15,118,908字节，不提交GitHub。原始输入hash复核不变。
- 独立`math.dist`复算时间一致：跨度36.17493937675094秒，末段0.145913773532115秒，
  最大间隔1.0222835113559228秒；非均匀间隔及末段均保留。这不是设备播放时长。
- DELAY/L候选单位交叉差：显式float64计算最大0.0001387662396155065，
  与float32算式所得0.0001220703125有舍入差异，输出记录实际公式，不冒源单位确认。
- `R0B0S0D.mpgeom`及`R0B0S0U.mpgeom`缺失已列出；引用键是`multipathGeometry.file`。

证据目录：`/Users/Simon/.codex/artifacts/2026-11-11-s5a/`。
读取模块SHA256：`e44b6663cb37e0ba29b944704ed828f568515800a71705ebe9f2cd37afce04b2`。
输出SHA256：`9b210c1388b072610f17715f2b22c04b6579e55f383a205287e76c8c155fd6d0`。

复跑命令（仓库根目录，专属无conftest，不导入应用，不连接数据库；全部显式Mock）：

```sh
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:///:memory: api-service/.venv/bin/python -B -m pytest --noconftest api-service/tests/test_mpdb_input.py -q --color=no
api-service/.venv/bin/python scripts/inspect_mpdb.py /Users/Simon/.codex/artifacts/2026-11-11-s5-mpdb/original.zip --output /Users/Simon/.codex/artifacts/2026-11-11-s5a/adapted-final.json --speed-m-s 5 --coordinate-units metres
api-service/.venv/bin/python /Users/Simon/.codex/artifacts/2026-11-11-s5a/verify_roundtrip.py
```

输出采用独占创建，复跑CLI须选一个尚不存在的新输出文件，不能覆盖已留证据。
相关回归在api-service目录执行`.venv/bin/python -m pytest tests/test_channel_asset_resolver.py -q`，
运行器用`TemporaryDirectory(prefix="s5a-related-")`创建全新目录，并设置
`DATABASE_URL=sqlite:///<临时目录>/fresh.db`、`USE_MOCK_INSTRUMENTS=true`；日志`related.log`。

当前仅为子任务实现及自查交接，不冒独立审查或S5a全部验收：主代理负责唯一全后端、
独立review结果处理和研究agent解析算法证据合并，再按内外审流程交付。
正式消费者仍为空，S5c及实机验证未完成，不修改路线图状态。

## 内审收窄后的最终专属验证

读取模块增加速度推导的帧顺序检查和时间差有限性检查；先RED（3 failed）后GREEN（50 passed），10组逆变异全部目标失败并恢复。显式时刻按原行对应，允许乱序帧编号；速度推导允许跳号但拒绝乱序。

最终证据目录为`/Users/Simon/.codex/artifacts/2026-11-11-s5a/p2-final/`；读取模块SHA256为`8e3cda1ae37e2ea9c120b5d1a11e5bd7b31ad23a442f1b587b1d6f04a726b6c0`，最终适配文件SHA256为`bba63f0ca0b4450070c8e904bb14b04b88cb2ac932492690c80853403d61a919`。新版再次逐值核对全部原张量及时间一致。

独立参考探针同时收窄为从0秒起的有限递增时刻，CRLF CSV实际复跑与JSON结果完全一致，非零起点两探针均明确拒绝。修正后两探针再跑，固定JSON结果未变；源码校验值见引用的versions.json。

旧版本全量在内审修正后主动中止：6819 passed、17 skipped，退出2（KeyboardInterrupt），不是完成结果。最终版本使用另一个全新SQLite重新全量，结果另列。

## 最终完整回归与内审

最终源码内审无P1，前述收窄问题均落实。唯一完成的最终全后端在全新`/tmp/pc04a8-4gh41bsj/full.sqlite`及七类全Mock配置上执行；源模块、测试和CLI校验值在运行前后相同。命令为api-service目录中`DATABASE_URL=sqlite:////tmp/pc04a8-4gh41bsj/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a8-4gh41bsj/logs .venv/bin/python -m pytest -q --color=no -o log_cli=false`。

结尾：`2 failed, 8790 passed, 17 skipped, 11541 warnings in 1320.05s (0:22:00)`，退出1，**不是全绿**。失败仅G8/G11文档引用检查，未改动main基线`a115a35d`上用新SQLite、显式Mock单独复跑同两测试亦为`2 failed, 39 warnings in 1.39s`。它们指向旧PC07A-1及PC04A-4E/5D验收记录，本片不改写历史记录。新功能与现有正式拒绝门回归没有新增失败。

完整日志、基线对照、启动审计和输入校验值保留在`/Users/Simon/.codex/artifacts/2026-11-11-s5a/full-final/`。未触碰现场PG或仪器。Alembic只有一个head：`d5e7f9012345`；Python编译、Node语法检查及diff-check通过。本片没有GUI或依赖改动。

最终文档补齐后规则检查复跑：`tests/test_rule_gates.py -q --color=no -o log_cli=false`为68 passed、2 failed（仍仅同两处历史文档引用），日志`full-final/finaldocs.log`。
