# P2-30 实施计划

设计稿：`2026-08-21-p2-30-task-level-lease-design.md`（先读它）

## 步骤

1. **RED**：新建 `api-service/tests/test_p2_30_task_level_lease.py`，5 条行为
   测试（引用计数桩，断言「一次作业恰一次真 acquire/release」+「点级测量全部
   发生在租约持有期间」）。跑之，5 条全红（现状逐点取放 → acquires == 点数）。
2. **GREEN**：按设计稿在 5 个入口包外层租约：
   - `probe_calibration_service.py::_real_pattern_measurements`（无条件包双重循环）
   - `quiet_zone_validation_service.py::run_xpd_validation`（real else 块内包两次调用）
   - `path_loss_calibration_service.py::start_calibration`（`nullcontext` 条件包 probe 循环）
   - 同文件 `start_calibration_for_lab_profile`（条件包 chain 循环）
   - 同文件 `calibrate_frequency_sweep`（条件包 probe 循环，整个扫频作业一次；内层
     `_real_frequency_sweep_via_ce_sa` 不另包）
   跑新测试 5 条全绿。
3. **变异实跑**：M1–M5 分别摘掉一处外层租约 → 对应测试红。脚本化（内存快照
   写回还原，replace assert 命中，`--color=no` 数 FAILED/ERROR）。
4. **回归**：相关文件级 `pytest tests/test_instrument_test_lease.py
   tests/test_quiet_zone_validation.py tests/test_path_loss_calibration.py
   tests/test_path_loss_ce_sa.py tests/test_probe_calibration_service.py`；
   然后全量 `.venv/bin/python -m pytest -q --color=no -p no:cacheprovider`
   （零失败、无豁免 —— 原已知基线失败 test_p1_36 已由 P2-35 #357 治掉）。
5. **收尾**：③⁺ 文档镜像 grep（关键词 `acquire_sa_power_via_ce_tone` /
   `作业入口` / `逐点`）；commit（中文、`git commit -F`、trailer）；push 分支，
   不开 PR。

## 硬边界

- 不改 roadmap；不动 P2-32 触碰的校准服务区域以外的行；不加 alembic；
  diff 限定「入口包一圈」最小面。
