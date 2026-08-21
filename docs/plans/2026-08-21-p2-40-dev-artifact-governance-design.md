# P2-40 开发环境 DB / 日志沉积治理设计

## 可观察故障

开发与测试产物长期写入主工作区和旧 worktree，当前没有一份能回答“它是谁、由谁产生、
是否正在使用、为何可清、如何恢复”的清单。直接按文件名或目录清理会把现场仪器往返、
手工测试数据或正在运行的数据库当成垃圾；继续不治理又会让日志、固定路径测试 SQLite 和
匿名 Docker volume 持续占用空间并混淆手工测试环境。

2026-08-21 的只读盘点实证：

| 类别 | 当前观测 | 初始裁决 |
|---|---:|---|
| 主工作区 `api-service/logs` | 338 个文件，约 2.6 GB | 多个文件被运行中的 Python 进程打开；全部保护，先归档再谈清理 |
| P1-59 worktree 日志 | 15 个文件，约 242 MB | 来源可定位，但可能含回归/仪器证据；进入人工复核，不自动清 |
| Claude worktree 日志 | 9 个文件，约 11 MB | 同上 |
| 四组固定路径测试 SQLite | 主工作区、API 目录和旧 worktree 均有副本，单份约 1 MB | schema 已被测试 teardown 清空且产生方可定位；修复产生方后列入可恢复隔离候选 |
| 活跃 `meta3d_postgres_data` | Docker volume 约 79.7 MB，容器健康且正在挂载 | 正式开发库，必须备份并保护 |
| 匿名 Docker volumes | 14 个未挂载 volume，其中 12 个约 43 MB | 标签只能证明 anonymous，不能证明属于 Meta-3D；身份未知，默认保护 |
| 注册 worktree | Codex `.worktrees` 约 1.9 GB，Claude worktrees 约 732 MB | Git 元数据是归属真值；不把整个 worktree 当清理目标 |

厂商手册、现场文件、`debug_report_dump.txt` 和其他用户未跟踪文件不在本片扫描/清理
白名单内，不能因为位于仓库目录就改变其状态。

## 目标与边界

本片交付两类能力：

1. 一条默认且只能只读运行的 inventory 命令，生成确定性的 JSON/Markdown manifest；
2. 阻止四组校准测试继续在调用目录留下固定名称 SQLite。

本 PR 不移动、不删除任何现存 DB、日志、Docker volume 或 worktree。实际治理分成 PR 后的
操作批准点：先展示精确目标、大小、身份依据、备份/隔离路径和恢复命令，用户批准后才执行。

## 方案比较

### A. 手工 `find` / `du` 后维护一份文档（拒绝）

成本最低，但清单会立刻漂移，无法稳定复算 Git/worktree 归属、SQLite 结构与 Docker 挂载
状态，也不能成为后续批准单的输入。

### B. 仓库内只读 inventory + 独立批准后的隔离操作（采用）

脚本只读取注册 worktree 和 Docker 元数据，输出结构化 manifest；分类默认 `protect`，只有
精确命中已知测试产生方、SQLite 文件且 schema 已清空的对象才能成为
`quarantine_candidate`。日志、活跃数据库、未知 volume 均不能自动晋级为候选。

优点：身份与裁决可复算；默认保守；本 PR 没有删除入口。缺点：真正回收空间需要用户批准后
再执行一次操作，但这是保护现场证据所必需的边界。

### C. 同一 CLI 提供 `--execute` 删除（拒绝）

即使默认 dry-run，误传参数也会把分类错误直接变成不可恢复删除；而日志与匿名 volume 当前
仍有身份未知项，尚不具备安全执行条件。

## 资产全集与真值来源

| 资产 | 产生方 / 权威身份 | inventory 行为 | 默认裁决 |
|---|---|---|---|
| 注册 worktree | `git worktree list --porcelain` | 记录路径、HEAD、branch、dirty；不跟随依赖 symlink | `protect` |
| `api-service/logs` 文件 | worktree 归属 + 文件元数据 + 当前打开句柄（平台可用时） | 记录类型、大小、mtime、是否打开；不读日志正文 | `protect` / `review` |
| SQLite 文件 | SQLite header、只读 schema、Git 状态、精确产生方路径 | 使用 read-only URI；未知/非空 schema 不做用途猜测 | `protect` |
| 已知固定测试 SQLite | 四个测试模块的精确旧路径 + 空 schema | 记录产生方测试和空库证据 | `quarantine_candidate` |
| Docker volume | `docker volume inspect`、容器 mount 反向引用、size（可用时） | 命令不可用时显式 `unavailable`，不改变分类 | mounted=`protect`，unmounted anonymous=`review` |
| 用户未跟踪资料 | 不属于扫描白名单 | 不枚举、不分类、不触碰 | `out_of_scope` |

名称只能用于定位产生方，不能单独证明身份。`test_*.db` 若 schema 非空、路径不在四个精确旧
站点中或被进程打开，必须保持 `protect`。

## Manifest 契约

filesystem 条目至少包含：

- 绝对路径、`kind`、字节数与 mtime；
- worktree path / branch / HEAD，以及 manifest 的 worktree 清单所记录的 dirty 状态；
- Git 状态（tracked / ignored / untracked / unknown）；
- 身份证据数组，而不是单一推断标签；
- `disposition`：`protect` / `review` / `quarantine_candidate`；
- 裁决理由与当前打开状态；无法检测时显式 `unknown`。

Docker 条目使用 volume id、创建时间、labels、容器反向引用和可用时的只读 size 证据；探测
失败或畸形记录显式降级，不用缺失字段猜身份。恢复前置条件与逐文件校验和只在合并后的批准单
中生成，因为本 PR 没有任何可执行的隔离或恢复动作。

JSON 用稳定 key 和排序，便于前后 diff；Markdown 只从同一内存模型渲染，不维护第二份分类
逻辑。脚本不接受删除、移动或 Docker prune 参数。

## 测试 SQLite 产生方修复

四个校准测试模块目前使用 `sqlite:///./test_*.db`，工作目录不同就会在仓库根或
`api-service` 留下副本。改为 pytest 提供的临时目录：

- function scope 的 channel calibration 使用 `tmp_path` 创建每测试独立 DB；
- module scope 的三组 probe calibration 使用 `tmp_path_factory` 创建模块级 DB；
- engine、session factory 与依赖 override 全部绑定同一个临时 URL；
- teardown 仍 drop schema / dispose engine，但不依赖删除仓库文件。

不把数据库改成内存 SQLite：多连接的 TestClient / SQLAlchemy 路径需要共享同一文件，临时
文件能保留生产相近的连接语义，同时由 pytest 生命周期回收。

## 安全与失败方向

- 误保护开发残留：只多占空间，可在人工复核后处理；
- 误清现场/手工证据：证据不可恢复，可能使正式报告失去审计依据。

两者代价不对称，因此未知项一律保护。inventory 的任何探测失败都只降低到
`protect/unknown`，不得通过异常、命令缺失或空输出升级为清理候选。

## PR 后批准点与恢复方案

PR 合并后重新生成 manifest，并单独向用户展示：

1. 精确候选列表、总大小、mtime、是否打开；
2. SQLite 空 schema 与产生方证明；日志或 volume 若仍是 `review` 则不进入操作单；
3. 拟隔离目录（仓库外、带时间戳）及逐文件 SHA-256 manifest；
4. 活跃 Postgres 的 `pg_dump` 备份路径、校验和与恢复命令；
5. 隔离观察期和最终删除的第二次批准边界。

首轮操作只允许原子移动到隔离区或创建备份，不直接删除。用户确认隔离内容可弃后，才可按
隔离 manifest 精确删除并报告回收空间。

## 验证

- 临时仓库 fixture 覆盖：注册 worktree、dirty 状态、symlink 不跟随、日志、已知/未知
  SQLite、打开状态不可用、Docker 不可用与畸形输出；
- 变异候选判据：去掉“空 schema”或“精确路径”任一条件，测试必须红；
- 四组校准测试从受保护 cwd 运行，前后仓库 DB manifest 不变；
- 运行相关测试、完整 rule gates、全后端、`compileall` 与 `diff-check`。

## 非目标

- 不在本 PR 中执行清理、备份、移动、删除或 Docker prune；
- 不修改生产日志留存天数或仪器证据语义；
- 不删除旧 worktree，也不判断用户是否仍需要某条分支；
- 不清理测试冗余；测试保护矩阵与重复断言收敛属于后续 P3-22；
- 不按目录或文件名把厂商资料、现场证据、手工测试数据归类为开发沉积。

## 实施与 dry-run 证据（代码提交 `8484cbe`）

### 只读能力

- `scripts/dev_artifact_inventory.py` 只调用 Git、`lsof` 与 Docker 的只读查询；CLI 没有
  `execute` / `delete` / `move` / `prune` 选项。
- 文件扫描只覆盖注册 worktree 的 `api-service/logs`，以及 worktree 根、
  `api-service` 根和 `api-service/app` 根的 SQLite 后缀文件；不递归进入
  `Instrument_API_Doc` 或其他用户资料目录，也不跟随 symlink。
- SQLite 使用 header + `mode=ro` schema 检查；只有四个精确旧测试产生方、空 schema、
  ignored/untracked、且 `lsof` 明确 closed 时才成为 `quarantine_candidate`。
- macOS `lsof +D` 会在返回码 1 时仍给出有效 `n<path>` 记录；实现保留这种正面打开证据，
  真实运行识别到 10 个打开中的日志，而不是把它们误列为 closed。
- Docker 只读读取 volume inspect、容器反向引用与 `docker system df -v` 大小；mounted volume
  一律保护，unmounted anonymous 只进入 `review`，绝不成为自动候选。

### 真实 manifest（2026-08-22 00:17 +08:00）

运行命令：

```bash
cd api-service
.venv/bin/python scripts/dev_artifact_inventory.py --repo-root .. --format json \
  > /tmp/meta3d-p2-40-manifest.json
.venv/bin/python scripts/dev_artifact_inventory.py --repo-root .. --format markdown \
  > /tmp/meta3d-p2-40-manifest.md
```

结果：

| 范围 | disposition | 数量 | 字节 |
|---|---|---:|---:|
| filesystem | `protect` | 339 | 2,765,027,261 |
| filesystem | `review` | 24 | 251,514,300 |
| filesystem | `quarantine_candidate` | 20 | 21,299,200 |
| Docker volume | `protect` | 2 | 167,000,000 |
| Docker volume | `review` | 14 | 520,500,000 |

filesystem 共 383 项 / 3,037,840,761 字节。目录级 `lsof` 返回了 10 个确定仍被运行进程打开的
主工作区日志，但同时以非零状态结束；因此其余 328 个未命中日志一律保持 `unknown` 并进入
protect，而不是被猜成 closed。另有一个身份不足的空 `api-service/app/mimo_ota.db` 受保护。
24 个有完整 closed 证据的旧 worktree 日志仍只列 `review`，没有因关闭状态自动晋级。20 个
候选全部是四个已定位测试模块留下的空 schema SQLite：主工作区根和 `api-service` 各 4 份、
P1-59 worktree 4 份、P2-39 worktree 4 份、Claude `loving-torvalds-ae273b` worktree 4 份；
每一份均为 closed 且有独立 SHA-256 复核，但本轮没有移动或删除。

Docker 的两个 protect 是正在挂载的 `meta3d_postgres_data`（79.7 MB）与
`gaokao_postgres_data`（87.30 MB）。14 个 review 全是 2026-08-02 创建且当前未挂载的
anonymous volume：12 个约 43.33–43.51 MB、2 个 0 B；anonymous 标签不足以证明其中数据
属于 Meta-3D，因此不进入本次候选。

manifest 校验：

- JSON：`47255e0e29b06c2866ccf860b5862159259a8fad812509f7e20f88a75aeae85c`
  （273,978 bytes）；
- Markdown：`a993a155bf0f77e28275eca45e62b5b2943507616bc6689780330a7df9b7793a`
  （71,260 bytes）。

### 产生方收口

四个校准测试已改为 pytest 临时 SQLite：function scope 使用 `tmp_path`，三个 module scope
使用各自 `tmp_path_factory` 目录，并在 teardown dispose engine。子进程 RED 在受保护 cwd
留下 4 个 `test_*.db`；GREEN 后为 0。四个完整模块加 inventory 测试 **229 passed**。

最终验证：P2-40、四组校准与完整 rule gates **282 passed**；全后端
**4188 passed / 5 skipped**；`compileall`、`diff-check` 通过。fresh 内审最初的
2 P1 / 3 P2 已全部按 TDD 与单一真值源收口，复审 **P1/P2/P3=0**。

### 拟提交用户批准的可恢复操作（尚未执行）

外部隔离根拟定为：

`/Users/simon/Meta3D-Artifacts/quarantine/2026-08-22-p2-40/`

批准后首轮只做以下可恢复动作：

1. 重新生成 manifest，确认 20 个候选仍为 closed / empty schema，路径、size、mtime 未漂移；
2. 生成 `checksums.sha256` 与 `moves.json`，逐条记录 source、quarantine target、size、mtime、
   SHA-256；
3. 按 `moves.json` 原子移动这 20 个 SQLite 到隔离根，保留原 worktree 相对层级；恢复时按
   同一 manifest 反向移动，并复核 SHA-256；
4. 活跃 `meta3d_postgres_data` 在任何 DB 操作前先用 `pg_dump -Fc` 备份到
   `/Users/simon/Meta3D-Artifacts/backups/`，记录 dump SHA-256，并通过临时恢复库执行
   `pg_restore --list` / 恢复验证；
5. 所有日志和 14 个 anonymous volume 本轮继续原地保留，不纳入移动单。

隔离观察与最终删除是第二个独立批准点；本 PR、当前 dry-run 以及第一次批准都不直接删除。
