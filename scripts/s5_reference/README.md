# S5a 独立解析参考与 S5b 风险探针（只读离线）

脚本为 ce_probe.py、lr_probe.mjs。不是正式执行入口，不操作仪器，不构成 S5a 整体物理正确性验收。所有输出目录必须指向仓库外。原生程序另一次启动尝试因许可证到期退出，测试未运行，没有绕过许可证；本目录不包含原生程序调用。

实跑版本：ChannelEgine 9190f920ef7c9fb288ac8b9ed2f99c5a82b04489；Lauraycs 53ea4cf97842d8e9c18d97e07d081b2b98fbc316。Python 3.13.7、numpy 2.3.2、pydantic 2.11.7、pytest 8.4.1；Node v22.17.0、assemblyscript 0.28.20（与仓库 web/src/package.json 一致）、esbuild 0.25.12。本地原生二进制没有证据证明与源码提交同步，不称已核部署版本。

复算命令（先填写变量为实际位置；不要求脚本存放在 /tmp）：

```sh
CE_REPO=/absolute/path/to/ChannelEgine
LR_REPO=/absolute/path/to/Lauraycs-source
TIME_FILE=/absolute/path/to/adapted-final.json
PROBES=/absolute/path/to/probe-directory
RUN_DIR=$(mktemp -d /tmp/s5-reference.XXXXXX)
CE_PYTHON="$CE_REPO/.venv/bin/python"

npm install --prefix "$RUN_DIR" --cache "$RUN_DIR/npm-cache" --no-audit --no-fund assemblyscript@0.28.20 esbuild@0.25.12
mkdir -p "$RUN_DIR/assembly/generated" "$RUN_DIR/utils" "$RUN_DIR/results"
cp "$LR_REPO/web/src/assembly/asc.ts" "$RUN_DIR/assembly/asc.ts"
node "$RUN_DIR/node_modules/assemblyscript/bin/asc.js" "$RUN_DIR/assembly/asc.ts" --outFile "$RUN_DIR/assembly/generated/asc.wasm" --bindings raw --optimize --runtime incremental

PYTHONDONTWRITEBYTECODE=1 "$CE_PYTHON" "$PROBES/ce_probe.py" --ce-repo "$CE_REPO" --timeline "$TIME_FILE" --output "$RUN_DIR/results" > "$RUN_DIR/ce.log" 2>&1
node "$PROBES/lr_probe.mjs" --lauraycs-repo "$LR_REPO" --timeline "$TIME_FILE" --output "$RUN_DIR/results" --tool-root "$RUN_DIR" --wasm-dir "$RUN_DIR/assembly/generated" > "$RUN_DIR/lr.log" 2>&1

# 可选：已有测试。只在临时目录运行，禁用 Python 缓存写入。
cp "$LR_REPO/web/src/utils/asc-export.test.mjs" "$LR_REPO/web/src/utils/asc-timing.test.mjs" "$LR_REPO/web/src/utils/asc-timing.ts" "$RUN_DIR/utils/"
node --test "$RUN_DIR/utils/asc-export.test.mjs" "$RUN_DIR/utils/asc-timing.test.mjs"
cd "$RUN_DIR"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$CE_REPO" "$CE_PYTHON" -m pytest -q -p no:cacheprovider --confcutdir="$CE_REPO/tests" "$CE_REPO/tests/test_spatiotemporal_tracking.py" "$CE_REPO/tests/test_phase_continuous.py" "$CE_REPO/tests/test_doppler_native_mapping.py"
```

时间文件使用`scripts/inspect_mpdb.py`产生的`s5-raw-paths/1` JSON，也兼容含`time_s`列的CSV。本片探针仅接受从0秒起严格递增的有限时间网格；非零起点拒绝，不擅自平移。适配器本身仍能保存显式非零起点。脚本没有生成解析 ZIP 再读回；它们调用实际导出/时间演化/跨帧关联函数。时间文件只提供时间网格，已知轨迹坐标由解析式独立定义，不声称重建用户原始 MPDB 路径。固定的场景参数是参考定义，不是隐藏用户路径。输出 JSON 给出误差，不设置未经批准的“通过阈值”；进程退出成功仅表示计算完成。

参考模型：H(t)=Σ a_k exp(j phi_k+j2π f_k t)；几何轨迹 TX=(0,0,0)、RX=(5t,20,0)，L(t)=sqrt((5t)^2+20^2)，fD=-fc/c*dL/dt，H(t)=exp(-j2πfc*(L(t)-L(0))/c)，fc=2.4GHz、c=299792458m/s。幅度设为1以隔离相位/时延，未检验自由空间衰减。角度按到达方向由 RX 看向 TX 构造，不拿另一算法作真值。

本次固定版本结果在`docs/plans/s5a-reference-evidence/`；[核查报告](../../docs/plans/2026-11-11-s5a-reference-results.md)。使用其他版本或时间网格须另存结果，不能沿用这些数值。两份探针没有修改外部仓库。
