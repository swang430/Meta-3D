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
| 活跃 `meta3d_postgres_data` | Docker volume 约 79.65 MB，容器健康且正在挂载 | 正式开发库，必须备份并保护 |
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

每个条目至少包含：

- 绝对路径或 Docker volume id；
- `kind`、字节数、mtime；
- worktree path / branch / HEAD / dirty 状态；
- Git 状态（tracked / ignored / untracked / outside）；
- 身份证据数组，而不是单一推断标签；
- `disposition`：`protect` / `review` / `quarantine_candidate`；
- 裁决理由与恢复前置条件；
- 当前是否被进程或容器占用；无法检测时显式 `unknown`。

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
