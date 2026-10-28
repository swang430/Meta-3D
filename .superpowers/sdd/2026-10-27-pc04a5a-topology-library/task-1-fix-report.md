# PC04A5a Task1 P2 修复报告

## 范围与裁决

修复基线：`f64afffde50982675f1407fd3073f74b54ad7a3e`。
原独立审查唯一P2：历史probe节点是dict但缺少id，copy的统计先访问 `n['id']`，导致500而非明确的422。root已裁决在本片最小调整现有校验顺序；原三数组形态拒绝保留。

本增量仅换序：`db.add → db.flush → 既有完整Response校验 → update_statistics → db.commit`。flush提供UUID/时间/统计列默认值，仍未提交；图字段校验失败沿既有ValidationError→rollback→422。通过校验才计算依赖必填字段的统计，成功时commit自动flush最终统计。

不新增通用框架、不列缺id黑名单、不修源图、不补图默认值。原始深拷贝、两calibrated已有键置null、inactive/非default、name-only时间列自赋值和模板保护均未改。

## 安全与验证环境

- 已重新resolve/read PROJECT、handoff及task-1-review。沿用主claim，不release、不push、不派子代理。
- 以下两次app导入前均新建 `/tmp/pc04a5a-fix-*` SQLite，并显式设置 `USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`、隔离 `LOG_DIR`。
- pytest conftest还会将LOG_DIR换到它自己的新临时目录，这是额外隔离，不是继承用户日志。没有使用默认数据库或默认日志处理器。
- 本次不访问原CAICT、不调用用户服务、不停止/重启任何服务、不运行硬件；没有重复13模块或全后端。

## TDD RED

先仅新增 `test_probe_missing_id_is_422_before_statistics_and_keeps_source`：用现有内存ORM夹具，复制source.nodes并删除probe的id，通过ORM保存源；真实POST copy要求422，源raw JSON不变，拓扑行数不增加。

实际命令（api-service目录）：

```bash
pc04a5a_fix_dir=$(mktemp -d /tmp/pc04a5a-fix-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_fix_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_fix_dir/logs" .venv/bin/python -m pytest tests/test_pc04a5a_topology_library.py -k probe_missing_id -q -o log_cli=false > "$pc04a5a_fix_dir/red.log" 2>&1
```

原件：`/tmp/pc04a5a-fix-t3V7Ps/red.log`，exit1：

```text
FAILED ...::test_probe_missing_id_is_422_before_statistics_and_keeps_source - AssertionError: Internal Server Error
1 failed, 43 deselected, 40 warnings in 0.21s
```

该RED捕捉真实500，不是测试导入/夹具错误。

## 最小修复后 GREEN

实际命令（api-service目录；再次mktemp新目录）：

```bash
pc04a5a_fix_dir=$(mktemp -d /tmp/pc04a5a-fix-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_fix_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_fix_dir/logs" .venv/bin/python -m pytest tests/test_pc04a5a_topology_library.py tests/test_switch_topology_chamber_binding.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a4a_nominal_properties.py::test_checked_crud_and_schema_closure_match_live_contract -q -o log_cli=false > "$pc04a5a_fix_dir/green.log" 2>&1
```

原件：`/tmp/pc04a5a-fix-0EHE4U/green.log`，exit0：

```text
81 passed, 79 warnings in 4.16s
```

包含Task1全部44例、当前scope/chamber保护以及OpenAPI闭包。新反例422/原图不变/行数不增，原正常副本统计/JSON/owner/采用证书、name-only执行选图与导入保护断言均通过。warnings确实存在，不称无警告。

## 版本与自查

测试运行于上述BASE加本修复工作区，最终相关输入SHA256如下；不将BASE原实现称为GREEN：

```text
5bc023057a7f0fbe62cefecf73f62d6d4087a3aeebd596896e40973f7a3cacdf  api-service/app/api/switch_topology.py
30417da5865cb81cd7002ae5dbb4aab79e5579ad260485731e12bfd73d0f1702  api-service/tests/test_pc04a5a_topology_library.py
```

`git diff --check`无输出、exit0。生产仅4行diff（一次语句移动和注释），测试新增12行，其余仅本报告与原报告修复指针。自查未发现范围外改动、图数据规范化或执行绑定变化。尚须原独立reviewer增量确认；本报告不是独立审查PASS。

Task2/Task3仍未在本修复中执行；最终全后端唯一责任Task3不变，旧NULL topology_id证书和现有DELETE边界不变。
