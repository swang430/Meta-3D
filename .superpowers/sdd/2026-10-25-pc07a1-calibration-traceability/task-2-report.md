# PC07A1 Task 2：报告 JSON/PDF 与原执行关联可信门

## 结论与输入

- DONE；实现提交 `92dcbc712e10a9458600f557af83fda3f1d13009`，未 push。
- 基线 `cdb760611dc7e196acb3def449fc11f65d265790`，分支 `codex/pc-07a1-calibration-traceability`。
- 唯一需求输入为同目录 `task-2-brief.md`，未读取全计划。已读 AGENTS 审查规则、CLAUDE、TDD 与测试编写参考；PDF 文本提取与完成前验证按对应技能执行。
- 实现仅动报告 builder、report_service、api/report，新定点测试，以及主 agent 明确批准适配的 3 个既有测试文件。未改补偿计算、冻结、SCPI、硬件或当前数据库来源选择。
- 所有运行均在本工作树 `api-service`；全 Mock，显式临时 SQLite，默认 bootstrap 保持开启。真实来源 fixture 仅替换外部 transport 的合成脚本，不是现场硬件证据。

## 实现与范围自审

1. builder 从原 `execution.measurements.phases.measure.path_loss_application` 调用 Task 1 纯 helper，生成 `calibration_traceability`。PDF 短参数行与 JSON 使用同一投影。顶层 parser 状态不覆盖逐链 `application_state`。
2. 新字段列入 server-owned 集合，create/update 剥离客户端输入；generate 原执行全量重建路径保持不变并覆盖客户端 override。
3. 新字段存在时 `report_has_provenance_trust` 必须收到原 execution，否则拒绝。对比原执行重算追溯，并核对报告实际应用镜像；诊断场景保持既有应用降级 unknown，同时追溯不改写原来源事实。
4. API 既有唯一生产调用点解析单执行 ID 并读取原 execution。列表使用原安全重建提示；详情、下载、生成后响应沿既有门拒绝未关联或漂移。
5. 缺新字段的旧报告保持既有 provenance/lifecycle 门；安全重建写入新投影。原多执行拒绝规则未变。未查询当前采用、当前校准证书或采集记录补历史；测试同时禁止 `.query` 和 `.get` 读取这些当前来源。
6. 初次 PDF 试验将整个 snapshot 放入一行触发真实 LayoutError；最终改为短身份、应用、来源频率、前序和采集指针行，保留完整 JSON，不改 renderer。

所有改动文件归类为“修”。3 个旧测试改动是新关联契约必要 fixture 适配：使用其已经构造的原 execution；另明确断言新投影无原 execution 不可信，不伪造来源、不改业务预期。

## 全部 trust 调用点处理表

生产检索：`rg -n 'report_has_provenance_trust|_mimo_report_is_provenance_sanitized|_reject_untrusted_mimo_report' api-service/app`。

| 调用方/消费者 | 处理 |
| --- | --- |
| `api/report.py::_mimo_report_is_provenance_sanitized`，唯一直接生产调用方 | 新键存在时要求恰好一个有效关联 ID，取原 TestExecution，显式传 `execution=`；缺失 fail-closed |
| `api/report.py::_report_summary` → 列表 | 同一可信门；不匹配显示 requires_regeneration；仍使用既有安全重建资格判据 |
| `api/report.py::get_report` → 详情 | 同一 reject 门，篡改 409 |
| `api/report.py::download_report` → PDF下载 | 同一 reject 门，篡改 409，不能靠文件存在放行 |
| `api/report.py::generate_report` → 生成后响应 | service 原执行重建后同一 reject 门，HTTP 返回新冻结投影 |
| `tests/test_p1_81_diagnostic_report_trust.py`（4个参数用例） | 原单参 builder 信封断言新增投影后缺 execution；改为缺原执行拒绝 + 既有原 execution 关联成功 |
| `tests/test_p2_45_diagnostic_formal_consumers.py`（1个） | 同上，继续证明诊断正式指标全部隐藏 |
| `tests/test_p1_63_rf_kpi_provenance_truth.py`（1个） | 同上，继续证明 RF 快照不匹配安全降 unknown |
| `test_p1_54_kpi_valid_contract.py`、`test_p1_59_ca_throughput_truth.py`、`test_p1_64_quiet_zone_evidence_truth.py` 及 `test_p1_63_rf_kpi_provenance_truth.py` 其余手工旧信封断言 | 无新键，原规则继续；不改旧兼容测试 |

## TDD 与运行证据

每轮前缀（`task_tmp` 为对应阶段独立目录）：

```sh
task_tmp=$(mktemp -d /tmp/pc07a1-task2-<阶段>.XXXXXX)
USE_MOCK_INSTRUMENTS=true DATABASE_URL="sqlite:///$task_tmp/bootstrap.db" .venv/bin/python -m pytest <下列参数> > "$task_tmp/result.log" 2>&1
task_exit=$?
tail -8 "$task_tmp/result.log"
printf '\nEXIT=%s LOG=%s\n' "$task_exit" "$task_tmp/result.log"
```

| 阶段/pytest 参数 | 实际输出与退出码 | 证据 |
| --- | --- | --- |
| RED：`tests/test_pc07a1_report_traceability.py -q` | `4 failed, 1 passed, 130 warnings in 13.52s`；包装命令退出1 | `/tmp/pc07a1-task2-red.* /result.log`：缺新键、自洽伪造未拒绝、客户端未剥离；首次包装误用 zsh 只读变量 `status`，pytest 已完成但包装取码失败，此条不冒称已独立取得 pytest 退出码 |
| 初轮 GREEN 尝试，同上 | `2 failed, 3 passed, 131 warnings in 15.26s`，退出1 | `/tmp/pc07a1-task2-green.* /result.log`；实际 PDF LayoutError，随后拆为短参数行 |
| GREEN2，同上 | `5 passed, 132 warnings in 16.73s`，退出0 | `/tmp/pc07a1-task2-green2.WRCqvs/result.log` |
| 反向篡改 RED：`tests/test_pc07a1_report_traceability.py -k internal_application -q` | `1 failed, 11 deselected, 58 warnings in 3.04s`，退出1 | `/tmp/pc07a1-task2-red2.cSf313/result.log`；追溯不改、只改应用镜像时旧实现仍放行 |
| 定点+brief指定3回归 | `97 passed, 305 warnings in 34.91s`，退出0 | `/tmp/pc07a1-task2-regression.NwvsnT/result.log` |
| 额外原 trust 调用方回归4文件 | `6 failed, 76 passed, 53 warnings in 0.39s`，退出1 | `/tmp/pc07a1-task2-caller-check.CfMM48/result.log`；上表3文件缺 execution，主 agent 批准最小适配，不放宽生产门 |
| 最终定点：`tests/test_pc07a1_report_traceability.py -q --basetemp="$task_tmp/pytest"` | `12 passed, 262 warnings in 34.14s`，退出0 | `/tmp/pc07a1-task2-final-target.OhEOHC/result.log` |
| 最终8文件相关合集（见下） | `179 passed, 318 warnings in 35.02s`，退出0 | `/tmp/pc07a1-task2-final-related.GkejM8/result.log` |

最终相关合集完整参数：

```sh
tests/test_pc07a1_report_traceability.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_p1_48_report_provenance.py tests/test_p1_61_report_final_state_truth.py tests/test_p1_81_diagnostic_report_trust.py tests/test_p2_45_diagnostic_formal_consumers.py tests/test_p1_63_rf_kpi_provenance_truth.py tests/test_p1_64_quiet_zone_evidence_truth.py -q --basetemp="$task_tmp/pytest"
```

最终合集运行于提交 `92dcbc712e10a9458600f557af83fda3f1d13009` 的精确代码/测试内容，运行后仅新增本报告。`git diff --check` 退出0。未跑全后端，由主 agent 统一安排。

## JSON/PDF 与可观察断言

- 最终 PDF：`/tmp/pc07a1-task2-final-related.GkejM8/pytest/test_builder_and_pdf_show_froz0/traceability.pdf`，8页，SHA256 `9845461f01eea162aacf5736dce03a8e6d47af4104f655de3ac133c287a9cfac`。
- 同一内容 JSON：同目录 `traceability.json`，SHA256 `0ea5f31b43efa6019fdb084ad37bbe74d5dad50b5b20069784e26130385dd94b`。
- `pdftotext -layout <上述PDF> -` 退出0；文本实见“执行频率: 2595.0 MHz”“认证资格: unknown”“原始读数未内嵌”“前序 ID”，逐链确认采用 ID、旧证书 ID、采集 run ID 与交换索引。未出现“认证通过”。JSON 同时包含 confirmed_route/legacy_certificate、逐链 applied、source_snapshot、certification_status unknown、raw_readings_embedded false。
- 先冻结旧执行，再真实确认新采用、改当前 TestCase 频率；初次生成与重建均保持原来源 ID/2595，客户端 generate override 无效。生成后真实 HTTP `GET /api/v1/reports/{id}` 返回200，其 `content_data.calibration_traceability` 与原冻结逐值一致；不是只验证临时文件存在。
- selected、模拟、缺失和关联损坏用例均不获得正式判定；selected 保持逐链 selected，损坏关联保持 unknown/source_snapshot null，顶层状态不改写逐链结论。
- 攻击者同时替换应用和追溯自洽：详情/下载409，列表安全重建状态；只改应用也拒绝。旧缺新键信封继续可读，安全重建新增追溯。

## 疑虑与边界

- 自审未发现本片遗留功能缺陷。保留旧无新键信封的兼容性是明确需求，不把全部旧报告禁用。
- 318 warnings 未宣称清零；全部相关测试实际通过。未进行真实仪器连接、现场认证或硬件验收。
- JSON保留历史快照；采集run/交换索引仍只是指针，不嵌入原始读数；历史路径不宣称当前文件存在。
- 未修改 api/test_execution.py；未扩展 Task 1 已说明“未复现”的详情差异。
- `.playwright-cli/`、`api-service/.venv`、`output/` 为既有非任务未跟踪内容，未提交、未清理。主认领保持，不释放、不代主写台账收口。
