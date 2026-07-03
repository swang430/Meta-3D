#!/usr/bin/env bash
# 现场首测一键执行: 统一信道资产 (ChannelAsset) → MIMO_OTA 会话 → 4 方位吞吐 + 证据打印
#
# 为什么需要这个脚本 (2026-07-02 pre-departure 走查发现的两个缺口):
#   1. CreateSessionRequest / _request_overrides 没有 channel_asset_id 字段 —— 会话创建
#      API (路径 A) 带不进统一信道资产 (P2-16 S5 backlog);
#   2. 测试管理的计划步骤今天没有执行 runner (POST /test-plans/{id}/start 只转计划状态,
#      步骤停 pending) —— 步骤里配好的 channel_asset_id 无法经计划执行路消费。
# 现阶段唯一全公开 API 的可跑路 = 建会话 → PATCH 会话 TestCase 的
# configuration.channel_asset_id (合并, 不整体覆盖) → run-all。
#
# 用法:
#   ./scripts/onsite-run-channel-throughput.sh                 # 默认: F64 N78 资产 / 3.6GHz / 4 层
#   ASSET_ID=<uuid> FREQ_HZ=3600000000 LAYERS=4 DURATION_S=10 \
#     ./scripts/onsite-run-channel-throughput.sh
#
# 真硬件 (Real) 相关环境变量 (Codex #192 P1: 新会话没有本会话的 attach 记录, P1-9 门会拦):
#   DUT_IMSI=460xxxxxxxxxxxx   # 物理 attach 完成后传入 → 本会话记录 attach-dut (P1-9 门放行的正路)
#   DUT_MODEL="..."            # 可选, 随 attach 记录
#   STRICT_DUT=false           # bring-up 旁路 P1-9 DUT 门 (等价暗室首测页 Lab-smoke 开关)
#   STRICT_CAL=false           # bring-up 旁路 P1-8 校准门
#   mock 模式两门自动降级 (strict = flag AND hardware_real), 不需要以上任何变量。
#
# 前置 (现场):
#   - 仪器资源配置页驱动模式已切 Real + 重新加载驱动 (mock 彩排则保持 Mock);
#   - TestCase 频率必须与资产声明一致 (F64 N78 资产 = arfcn 640000 = 3600 MHz),
#     不一致 P2-11 频率一致性网在真硬件下 fail-loud。
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
ASSET_ID="${ASSET_ID:-b328d53a-edfa-40a0-81e1-5efc759bcc5a}"  # F64 N78 场景文件 (vendor_file)
FREQ_HZ="${FREQ_HZ:-3600000000}"
BW_MHZ="${BW_MHZ:-100}"
BAND="${BAND:-n78}"   # 2026-07-03 现场实证: 单载波自动构造 band=None → 驱动 set_cell_config
                      # None.upper() 崩且 ARFCN 不下发; 显式给 band 是零代码修法 (r5 验证)
LAYERS="${LAYERS:-4}"
DURATION_S="${DURATION_S:-10}"
RUN_TIMEOUT_S="${RUN_TIMEOUT_S:-1800}"

say() { printf '\n== %s ==\n' "$1"; }

say "1/6 校验信道资产 $ASSET_ID"
ASSET_JSON=$(curl -sf "$API/channel-assets/$ASSET_ID") || {
  echo "资产不存在或后端不可达 ($API)"; exit 1; }
# 按 source_type 推期望引擎, 最后取证时断言 (P2-16 resolver 映射)
EXPECTED_ENGINE=$(python3 - "$ASSET_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
print(f"  名称: {a.get('name')}  来源: {a.get('source_type')}", file=sys.stderr)
print(f"  文件: {a.get('associated_file_path')}", file=sys.stderr)
scd = (a.get('payload') or {}).get('scd_config') or {}
if scd.get('arfcn') is not None:
    print(f"  声明频率身份: arfcn={scd['arfcn']} bw={scd.get('bandwidth_mhz')}MHz  <- TestCase 频率须与此一致", file=sys.stderr)
print({'vendor_file': 'keysight_gcm', 'standard_3gpp': 'mimo_first_asc',
       'custom_static': 'mimo_first_asc', 'rt_dynamic': 'b2_parametric_tdl'
       }.get(a.get('source_type'), 'unknown'))
PY
)
echo "  期望 measure 引擎: $EXPECTED_ENGINE"

say "2/6 快照现有 TestCase id 集 (用于精确绑定新会话的 case, Codex #192 P2)"
BEFORE_IDS=$(curl -sf "$API/test-plans/cases?page_size=20&sort=-created_at" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(','.join(c['id'] for c in (d.get('items') or [])))")

say "3/6 创建 MIMO_OTA 会话 (freq=${FREQ_HZ}Hz bw=${BW_MHZ}M layers=${LAYERS})"
EXTRA_FLAGS=""
[ "${STRICT_DUT:-}" = "false" ] && EXTRA_FLAGS+=', "precheck_strict_dut": false' && echo "  ⚠ bring-up 旁路: precheck_strict_dut=false"
[ "${STRICT_CAL:-}" = "false" ] && EXTRA_FLAGS+=', "precheck_strict_cal": false' && echo "  ⚠ bring-up 旁路: precheck_strict_cal=false"
SESSION_ID=$(curl -sf -X POST "$API/commissioning/sessions" -H "Content-Type: application/json" -d "{
  \"frequency_hz\": $FREQ_HZ,
  \"bandwidth_mhz\": $BW_MHZ,
  \"mimo_layers\": $LAYERS,
  \"azimuths_deg\": [0, 90, 180, 270],
  \"measurement_duration_s\": $DURATION_S$EXTRA_FLAGS
}" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "  session_id = $SESSION_ID"

say "4/6 绑定并注入 channel_asset_id (合并 configuration, 不覆盖)"
# 差集定位本会话新建的 TestCase: 恰好 1 个才继续, 0/多个都 fail-loud (并发窗口内有别人
# 建会话时, 全局最新一条可能属于别的会话 —— Codex #192 P2)。
TC_ID=$(curl -sf "$API/test-plans/cases?page_size=20&sort=-created_at" | python3 -c "
import sys, json
before = set('$BEFORE_IDS'.split(','))
d = json.load(sys.stdin)
new = [c for c in (d.get('items') or [])
       if c['id'] not in before and str(c.get('name', '')).startswith('MIMO_OTA Session')]
if len(new) != 1:
    print(f'预期恰好 1 个新建会话 TestCase, 实际 {len(new)} 个 — 疑并发创建, 请在无并发时重跑', file=sys.stderr)
    sys.exit(3)
print(new[0]['id'])")
curl -sf "$API/test-plans/cases/$TC_ID" | python3 -c "
import sys, json
c = json.load(sys.stdin)
cfg = c.get('configuration') or {}
cfg['channel_asset_id'] = '$ASSET_ID'
# band 显式进单载波 (否则 pcell.band=None → UXM set_cell_config None.upper() 崩, ARFCN 不下发)
cfg['component_carriers'] = [{'frequency_hz': float('$FREQ_HZ'), 'bandwidth_mhz': float('$BW_MHZ'),
                              'band': '$BAND', 'role': 'pcell'}]
json.dump({'configuration': cfg}, sys.stdout)" > /tmp/onsite_patch_$$.json
curl -sf -X PATCH "$API/test-plans/cases/$TC_ID" -H "Content-Type: application/json" \
  -d @/tmp/onsite_patch_$$.json > /dev/null
rm -f /tmp/onsite_patch_$$.json
echo "  test_case_id = $TC_ID  channel_asset_id 已注入"

# P1-9 DUT 门要求 attach 记录在**本会话的 TestExecution** 上 (session_id 即 execution_id) ——
# 早前会话/物理 attach 不算 (Codex #192 P1)。真硬件下: 物理 attach 后传 DUT_IMSI 走正路。
if [ -n "${DUT_IMSI:-}" ]; then
  say "4b/6 记录 DUT attach (imsi=${DUT_IMSI})"
  ATTACH_JSON=$(curl -sf -X POST "$API/test-executions/$SESSION_ID/attach-dut" \
    -H "Content-Type: application/json" \
    -d "{\"imsi\": \"$DUT_IMSI\", \"dut_model\": \"${DUT_MODEL:-}\"}")
  python3 - "$ATTACH_JSON" <<'PY'
import sys, json
a = json.loads(sys.argv[1])
print(f"  attach 记录: success={a.get('success')} rrc_connected={a.get('rrc_connected')}")
for w in a.get('warnings') or []:
    print(f"  ⚠ {w}")
PY
elif [ "${STRICT_DUT:-}" != "false" ]; then
  echo "  ℹ 未传 DUT_IMSI 且未旁路 P1-9 门: mock 模式自动降级可继续; Real 模式 precheck 会拦 ——"
  echo "    物理 attach 后加 DUT_IMSI=<imsi> 重跑 (正路), 或 bring-up 用 STRICT_DUT=false。"
fi

say "5/6 run-all (预估 ~1min/方位, 超时 ${RUN_TIMEOUT_S}s)"
curl -sf --max-time "$RUN_TIMEOUT_S" -X POST \
  "$API/commissioning/sessions/$SESSION_ID/run-all" > /dev/null

say "6/6 取证"
# 注意: 不能 `curl | python3 - <<PY` —— heredoc 和管道都抢 stdin, json.load 会拿到空。
RESULT_JSON=$(curl -sf "$API/commissioning/sessions/$SESSION_ID")
python3 - "$RESULT_JSON" "$EXPECTED_ENGINE" <<'PY'
import sys, json
d = json.loads(sys.argv[1])
expected_engine = sys.argv[2]
ok = all(v == 'completed' for v in d['phase_statuses'].values())
print('  相位:', d['phase_statuses'])
mt = d.get('mimo_test') or {}
engine = mt.get('engine_mode')
print(f"  engine_mode (measure 实际) = {engine}   <- 期望 {expected_engine}")
print(f"  emulation_file = {mt.get('emulation_file')}  (source={mt.get('emulation_file_source')})")
for r in mt.get('azimuth_results') or []:
    print(f"    方位 {r['azimuth_deg']:>5}°  吞吐 {r['throughput_mbps']:.1f} Mbps")
an = d.get('analysis') or {}
print(f"  analysis: avg={an.get('avg_throughput_mbps', 0):.1f} Mbps  ratio={an.get('throughput_ratio')}  pass={an.get('throughput_pass')}")
print(f"  报告 id: {d.get('report_id')}")
if expected_engine != 'unknown' and engine != expected_engine:
    print(f"  ✗ 引擎不符: 资产未被 measure 消费 (疑注入没生效)", file=sys.stderr)
    sys.exit(4)
sys.exit(0 if ok else 2)
PY
